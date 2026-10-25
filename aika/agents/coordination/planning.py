"""Assignment planning: who runs what, and how a single agent runs it."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any

from aika.agent_tools import AgentToolCall, AgentTools
from aika.agents.coverage import EvidenceGap
from aika.agents.planner import AgentTaskPlan
from aika.extraction_schema import parse_json_object
from aika.graphrag import retrieve_graphrag
from aika.question_planner import QuestionPlan

from .models import AgentAssignment, AgentResult, clean_strings, result_count
from .support import validate_assignments


class PlanningMixin:

    def available_agents(self) -> list[str]:
        agents: list[str] = []
        if getattr(self.engine, "graph_client", None) is not None or getattr(self.engine, "csv_graph", None) is not None:
            agents.append("graph")
        if getattr(self.engine, "rag_index", None) is not None:
            agents.append("rag")
        if getattr(self.engine, "research_memory", None) is not None:
            agents.extend(["research", "graphrag"])
        if getattr(self.engine, "semantic_index", None) is not None:
            agents.append("semantic")
        return agents

    def dispatch(
        self,
        *,
        question: str,
        plan: QuestionPlan,
        task_plan: AgentTaskPlan,
        round_index: int,
        gaps: list[EvidenceGap] | None = None,
    ) -> list[AgentAssignment]:
        available = self.available_agents()
        fallback = self._fallback_assignments(
            question=question,
            task_plan=task_plan,
            round_index=round_index,
            available=available,
            gaps=gaps or [],
        )
        if not available:
            return []
        payload = self._safe_json(
            role="supervisor",
            system_prompt=(
                "你是中心调度 Agent。只输出严格 JSON，负责选择检索 Agent 和改写各路查询。"
                "只能使用给定 agent_type，不回答用户问题。"
            ),
            user_prompt=json.dumps(
                {
                    "question": question,
                    "question_plan": plan.to_dict(),
                    "required_coverage": task_plan.required_coverage,
                    "review_gaps": [gap.to_dict() for gap in gaps or []],
                    "available_agents": available,
                    "schema": {
                        "assignments": [
                            {
                                "agent_type": "graph|rag|research|semantic|graphrag",
                                "query": "string",
                                "filters": {},
                                "coverage_goals": ["string"],
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
        )
        assignments = validate_assignments(
            payload,
            available=available,
            question=question,
            round_index=round_index,
            max_assignments=self.max_workers,
        )
        if assignments:
            return assignments
        self.llm_budget.note_fallback("supervisor", "invalid or empty dispatch payload")
        return fallback

    def _fallback_assignments(
        self,
        *,
        question: str,
        task_plan: AgentTaskPlan,
        round_index: int,
        available: list[str],
        gaps: list[EvidenceGap],
    ) -> list[AgentAssignment]:
        coverage = [gap.coverage for gap in gaps] or list(task_plan.required_coverage)
        return [
            AgentAssignment(
                assignment_id=f"r{round_index}-{agent_type}",
                agent_type=agent_type,
                query=question,
                coverage_goals=coverage,
                round_index=round_index,
            )
            for agent_type in available[: self.max_workers]
        ]

    def _run_assignment_with_metrics(
        self,
        assignment: AgentAssignment,
        plan: QuestionPlan,
        hyde_query: Any | None = None,
    ) -> AgentResult:
        with self._runtime_lock:
            self._active_workers += 1
            self._peak_concurrency = max(self._peak_concurrency, self._active_workers)
        try:
            return self._run_assignment(assignment, plan, hyde_query)
        finally:
            with self._runtime_lock:
                self._active_workers -= 1

    def _run_assignment(
        self,
        assignment: AgentAssignment,
        plan: QuestionPlan,
        hyde_query: Any | None = None,
    ) -> AgentResult:
        started_at = time.perf_counter()
        local_errors: list[str] = []
        role = f"query_{assignment.agent_type}"
        client = self.llm_budget.client(role)
        query, filters, degraded = self._rewrite_query(assignment, plan)
        companies = clean_strings(filters.get("companies"))
        if not companies and filters.get("company"):
            companies = [str(filters["company"])]
        scoped_plan = replace(
            plan,
            question=query,
            companies=companies or plan.companies,
        )
        retrieval_query = (
            query
            if assignment.agent_type == "graph"
            else self.engine._hyde_retrieval_query(query, hyde_query)
        )
        tools = AgentTools(
            self.engine,
            errors=local_errors,
            llm_options=self.llm_options,
            llm_client=client,
        )
        tool_calls: list[AgentToolCall] = []
        output: Any = None
        try:
            if assignment.agent_type == "graph":
                generated, prepare_call = tools.prepare_cypher(query, scoped_plan)
                records, query_call = tools.query_graph(generated, scoped_plan)
                tool_calls.extend([prepare_call, query_call])
                output = {"generated": generated, "records": records or []}
            elif assignment.agent_type == "rag":
                output, call = tools.search_rag(retrieval_query, scoped_plan)
                tool_calls.append(call)
            elif assignment.agent_type == "research":
                output, call = tools.search_research(retrieval_query, scoped_plan)
                tool_calls.append(call)
            elif assignment.agent_type == "semantic":
                output, call = tools.search_semantic(retrieval_query, scoped_plan)
                tool_calls.append(call)
            elif assignment.agent_type == "graphrag":
                call_started = time.perf_counter()
                output = retrieve_graphrag(
                    question=retrieval_query,
                    plan=scoped_plan,
                    research_memory=getattr(self.engine, "research_memory", None),
                    max_subquestions=int(getattr(self.engine, "drift_max_subquestions", 6)),
                    global_top_k=int(getattr(self.engine, "global_dossier_top_k", 3)),
                    local_top_k=int(getattr(self.engine, "local_claim_top_k", 12)),
                    path_top_k=int(getattr(self.engine, "graph_path_top_k", 6)),
                )
                tool_calls.append(
                    AgentToolCall(
                        tool="graphrag_retrieve",
                        args={"question": retrieval_query[:160], "answer_type": scoped_plan.answer_type},
                        result_count=len(output.global_hits) + len(output.local_hits),
                        elapsed_ms=round((time.perf_counter() - call_started) * 1000, 2),
                    )
                )
            else:
                raise ValueError(f"unsupported query agent: {assignment.agent_type}")
        except Exception as exc:
            local_errors.append(str(exc))
        error = "; ".join(error for error in local_errors if error)
        return AgentResult(
            assignment=replace(assignment, query=query, filters=filters),
            status="error" if error and result_count(output) == 0 else "completed",
            output=output,
            tool_calls=tool_calls,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error=error,
            degraded=degraded or bool(error),
        )

    def _rewrite_query(
        self,
        assignment: AgentAssignment,
        plan: QuestionPlan,
    ) -> tuple[str, dict[str, Any], bool]:
        payload = self._safe_json(
            role=f"query_{assignment.agent_type}",
            system_prompt=(
                f"你是 {assignment.agent_type} 查询 Agent。"
                "只改写适合本数据源的检索查询和过滤条件，只输出严格 JSON，不回答问题。"
            ),
            user_prompt=json.dumps(
                {
                    "question": assignment.query,
                    "question_plan": plan.to_dict(),
                    "coverage_goals": assignment.coverage_goals,
                    "schema": {"query": "string", "filters": {"companies": ["string"]}},
                },
                ensure_ascii=False,
            ),
        )
        if isinstance(payload, dict):
            query = " ".join(str(payload.get("query") or "").split())[:600]
            filters = payload.get("filters")
            if query and isinstance(filters, dict):
                return query, dict(filters), False
        self.llm_budget.note_fallback(f"query_{assignment.agent_type}", "invalid query rewrite payload")
        return assignment.query, dict(assignment.filters), True

    def _safe_json(self, *, role: str, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        client = self.llm_budget.client(role)
        if client is None:
            return None
        kwargs = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": 0.0,
            **self.llm_options,
        }
        try:
            if hasattr(client, "chat_json"):
                payload = client.chat_json(**kwargs)
                return payload if isinstance(payload, dict) else None
            if hasattr(client, "chat_text"):
                return parse_json_object(str(client.chat_text(**kwargs)))
        except Exception as exc:
            self.llm_budget.note_fallback(role, str(exc))
        return None
