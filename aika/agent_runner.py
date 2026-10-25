"""Shared base class and helpers for the agent runners."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from aika.agent_tools import AgentToolCall, AgentTools
from aika.agents.coverage import CoverageReport
from aika.agents.planner import AgentTaskPlan, TaskPlanner
from aika.graphrag import GraphRagResult
from aika.professional_qa import EvidenceCard, legacy_evidence_rows
from aika.question_planner import QuestionPlan
from aika.rag_index import RagHit
from aika.research_claims import ResearchHit
from aika.semantic_index import SemanticHit


MAX_AGENT_STEPS = 4


@dataclass
class AgentTraceStep:
    step: int
    phase: str
    thought: str
    action: str
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    observation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "phase": self.phase,
            "thought": self.thought,
            "action": self.action,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "observation": self.observation,
        }


@dataclass
class AgentRetrievalState:
    graph_records: list[dict[str, Any]] = field(default_factory=list)
    rag_hits: list[RagHit] = field(default_factory=list)
    research_hits: list[ResearchHit] = field(default_factory=list)
    semantic_hits: list[SemanticHit] = field(default_factory=list)
    graphrag: GraphRagResult | None = None
    reranker: dict[str, Any] = field(default_factory=dict)
    generated: Any | None = None
    coverage_report: CoverageReport | None = None


class AgentRunner:
    def __init__(self, engine: Any, *, max_steps: int = MAX_AGENT_STEPS) -> None:
        self.engine = engine
        self.max_steps = max(1, min(int(max_steps or MAX_AGENT_STEPS), MAX_AGENT_STEPS))

    def _plan(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None,
        tools: AgentTools,
        timings_ms: dict[str, float],
    ) -> tuple[list[dict[str, str]], dict[str, Any], str, QuestionPlan, AgentTaskPlan, str, Any, Any, list[AgentTraceStep]]:
        from aika.qa_engine import describe_plan_progress

        trace: list[AgentTraceStep] = []
        stage_start = time.perf_counter()
        history, history_memory = self.engine._prepare_conversation_history(
            conversation_history,
            errors=tools.errors,
            llm_options=tools.llm_options,
            llm_client=tools.llm_client,
        )
        self._record_timing(timings_ms, "history", stage_start)

        stage_start = time.perf_counter()
        contextual_question, contextualize_call = tools.contextualize_question(question, history)
        self._record_timing(timings_ms, "contextualize", stage_start)

        stage_start = time.perf_counter()
        plan, planner_source, plan_call = tools.plan_question(contextual_question)
        self._record_timing(timings_ms, "plan", stage_start)

        stage_start = time.perf_counter()
        hyde_query, hyde_call = tools.build_hyde_query(contextual_question, plan)
        self._record_timing(timings_ms, "hyde", stage_start)

        stage_start = time.perf_counter()
        generated, cypher_call = tools.prepare_cypher(contextual_question, plan)
        self._record_timing(timings_ms, "cypher", stage_start)
        task_plan = TaskPlanner(max_steps=self.max_steps).plan(contextual_question, plan)

        trace.append(
            AgentTraceStep(
                step=1,
                phase="plan",
                thought="先把问题改写为可检索问题，并确定答案类型、公司、主题、HYDE 检索扩展和图谱查询。",
                action="contextualize_question -> plan_question -> build_hyde_query -> prepare_cypher",
                tool_calls=[contextualize_call, plan_call, hyde_call, cypher_call],
                observation=describe_plan_progress(plan),
            )
        )
        return history, history_memory, contextual_question, plan, task_plan, planner_source, generated, hyde_query, trace

    def _build_result(
        self,
        question: str,
        contextual_question: str,
        answer: str,
        reasoning_content: str,
        plan: QuestionPlan,
        task_plan: AgentTaskPlan,
        planner_source: str,
        generated: Any,
        state: AgentRetrievalState,
        evidence_cards: list[EvidenceCard],
        verification: dict[str, Any],
        hyde_query: Any,
        trace: list[AgentTraceStep],
        timings_ms: dict[str, float],
        errors: list[str],
        llm_client: Any | None,
        *,
        thinking_enabled: bool | None,
        reasoning_effort: str | None,
        total_start: float,
        history_count: int,
        history_memory: dict[str, Any],
    ) -> dict[str, Any]:
        from aika.qa_engine import answer_subgraph, hyde_diagnostics
        from aika.research_agent import build_research_outputs

        stage_start = time.perf_counter()
        evidence = legacy_evidence_rows(evidence_cards)
        rag_hit_rows = [hit.to_dict() for hit in state.rag_hits]
        research_hit_rows = [hit.to_dict() for hit in state.research_hits]
        evidence_card_rows = [card.to_dict() for card in evidence_cards]
        subgraph = answer_subgraph(state.graph_records, evidence_cards)
        if state.graphrag is not None:
            subgraph = merge_subgraph_edges(subgraph, state.graphrag.edges)
        checks = verification.get("checks", {}) if isinstance(verification, dict) else {}
        unsupported_terms = list(checks.get("unsupported_terms") or [])
        research_outputs = build_research_outputs(
            question=contextual_question,
            plan=plan,
            evidence_cards=evidence_cards,
            graph_records=state.graph_records,
            verification=verification,
        )
        if state.graphrag is not None:
            graphrag_payload = state.graphrag.to_dict()
            graphrag_payload["reranker"] = dict(state.reranker)
            research_outputs["graphrag"] = graphrag_payload
        self._record_timing(timings_ms, "render_payload", stage_start)

        graphrag_diagnostics = state.graphrag.diagnostics() if state.graphrag is not None else {}
        if graphrag_diagnostics:
            graphrag_diagnostics["reranker_source"] = state.reranker.get("source", graphrag_diagnostics.get("reranker_source", ""))
            graphrag_diagnostics["reranker_mode"] = state.reranker.get("mode", graphrag_diagnostics.get("reranker_mode", ""))
        diagnostics = {
            "graph_backend": self.engine.status.graph_backend,
            "graph_records": len(state.graph_records),
            "rag_hits": len(state.rag_hits),
            "research_hits": len(state.research_hits),
            "embedding_hits": len(state.semantic_hits),
            "embedding_enabled": bool(getattr(self.engine.status, "embedding_enabled", False)),
            "embedding_error": getattr(self.engine.status, "embedding_error", ""),
            "evidence_cards": len(evidence_cards),
            "rerank_top_n": self.engine.rerank_top_n,
            "history_messages": history_count,
            **history_memory,
            "contextualized": contextual_question != question,
            "contextualizer_mode": self.engine.contextualizer_mode,
            "planner_source": planner_source,
            "hyde": hyde_diagnostics(hyde_query),
            "enable_llm_cypher": self.engine.enable_llm_cypher,
            "enable_llm_planner": self.engine.enable_llm_planner,
            "thinking_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort or "",
            "graph_error": self.engine.status.graph_error,
            "rag_error": self.engine.status.rag_error,
            "research_error": self.engine.status.research_error,
            "llm_error": self.engine.status.llm_error,
            "unsupported_terms": unsupported_terms,
            "agent_enabled": True,
            "agent_max_steps": self.max_steps,
            "agent_steps": min(len(trace), self.max_steps),
            "agent_trace": [step.to_dict() for step in trace[: self.max_steps]],
            "agent_verification": verification,
            "agent_plan": task_plan.to_dict(),
            "agent_coverage": state.coverage_report.to_dict() if state.coverage_report else {},
            "agent_stop_reason": state.coverage_report.stop_reason if state.coverage_report else "",
            "agent_budget": task_plan.budgets.to_dict(),
            "graphrag": graphrag_diagnostics,
        }
        timings_ms["total"] = round((time.perf_counter() - total_start) * 1000, 2)
        diagnostics["timings_ms"] = timings_ms
        diagnostics["llm_calls"] = llm_client.calls if llm_client is not None else {"total": 0}

        return {
            "question": question,
            "contextual_question": contextual_question,
            "answer": answer,
            "reasoning_content": reasoning_content,
            "answer_type": plan.answer_type,
            "plan": plan.to_dict(),
            "cypher": generated.cypher,
            "cypher_params": generated.params,
            "cypher_source": generated.source,
            "graph_records": state.graph_records,
            "rag_hits": rag_hit_rows,
            "research_hits": research_hit_rows,
            "evidence_cards": evidence_card_rows,
            "evidence": evidence,
            "research_outputs": research_outputs,
            "verification": verification,
            "subgraph": subgraph,
            "diagnostics": diagnostics,
            "errors": errors,
        }

    @staticmethod
    def _record_timing(timings_ms: dict[str, float], name: str, started_at: float) -> None:
        timings_ms[name] = round((time.perf_counter() - started_at) * 1000, 2)


def coverage_tool_call(report: CoverageReport) -> AgentToolCall:
    return AgentToolCall(
        tool="detect_evidence_gaps",
        args={
            "required": report.required,
            "retrieval_round": report.retrieval_round,
            "max_retrieval_rounds": report.max_retrieval_rounds,
        },
        result_count=len(report.gaps),
        elapsed_ms=0.0,
        error="",
    )


def build_supplemental_question(contextual_question: str, gap: dict[str, Any]) -> str:
    companies = " ".join(str(company) for company in gap.get("companies") or [])
    query_suffix = str(gap.get("query_suffix") or "")
    return " ".join(part for part in (contextual_question, companies, query_suffix) if part).strip()


def should_refuse_metric_answer(report: CoverageReport | None) -> bool:
    if report is None:
        return False
    return "metric_evidence" in report.missing and report.stop_reason == "max_retrieval_rounds_reached"


def merge_graph_records(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = list(existing)
    seen = {
        (
            row.get("company", ""),
            row.get("relation", ""),
            row.get("target", ""),
            row.get("evidence", ""),
        )
        for row in output
    }
    for row in additions:
        key = (row.get("company", ""), row.get("relation", ""), row.get("target", ""), row.get("evidence", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def merge_rag_hits(existing: list[RagHit], additions: list[RagHit]) -> list[RagHit]:
    output = list(existing)
    seen = {hit.chunk_id or f"{hit.source_title}:{hit.page}:{hit.snippet[:80]}" for hit in output}
    for hit in additions:
        key = hit.chunk_id or f"{hit.source_title}:{hit.page}:{hit.snippet[:80]}"
        if key in seen:
            continue
        seen.add(key)
        output.append(hit)
    return output


def merge_research_hits(existing: list[ResearchHit], additions: list[ResearchHit]) -> list[ResearchHit]:
    output = list(existing)
    seen = {(hit.kind, hit.title, hit.company, hit.text[:120]) for hit in output}
    for hit in additions:
        key = (hit.kind, hit.title, hit.company, hit.text[:120])
        if key in seen:
            continue
        seen.add(key)
        output.append(hit)
    return output


def merge_semantic_hits(existing: list[SemanticHit], additions: list[SemanticHit]) -> list[SemanticHit]:
    output = list(existing)
    seen = {(hit.kind, hit.ref_id or hit.doc_id, hit.text[:120]) for hit in output}
    for hit in additions:
        key = (hit.kind, hit.ref_id or hit.doc_id, hit.text[:120])
        if key in seen:
            continue
        seen.add(key)
        output.append(hit)
    return output


def merge_subgraph_edges(existing: list[dict[str, str]], additions: list[dict[str, str]]) -> list[dict[str, str]]:
    output = list(existing)
    seen = {(edge.get("source", ""), edge.get("target", ""), edge.get("label", "")) for edge in output}
    for edge in additions:
        key = (edge.get("source", ""), edge.get("target", ""), edge.get("label", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(edge)
    return output[:120]
