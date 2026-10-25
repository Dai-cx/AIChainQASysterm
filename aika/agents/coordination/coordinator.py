"""The centralized coordinator: one LLM supervisor over parallel agents."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

from aika.question_planner import QuestionPlan

from .budget import CentralLLMBudget
from .models import AgentAssignment, AgentResult
from .planning import PlanningMixin
from .synthesis import SynthesisMixin


class CentralizedCoordinator(PlanningMixin, SynthesisMixin):
    def __init__(
        self,
        engine: Any,
        *,
        llm_budget: CentralLLMBudget,
        llm_options: dict[str, Any],
    ) -> None:
        self.engine = engine
        self.llm_budget = llm_budget
        self.llm_options = dict(llm_options)
        self.max_workers = max(1, int(getattr(engine, "multi_agent_max_workers", 5) or 5))
        self.timeout_seconds = max(
            1.0,
            float(getattr(engine, "multi_agent_task_timeout_seconds", 90.0) or 90.0),
        )
        self._runtime_lock = threading.Lock()
        self._active_workers = 0
        self._peak_concurrency = 0
        self._timeouts = 0
        self._rounds: list[dict[str, Any]] = []

    def execute_wave(
        self,
        assignments: list[AgentAssignment],
        *,
        plan: QuestionPlan,
        hyde_query: Any | None = None,
    ) -> list[AgentResult]:
        if not assignments:
            return []
        started_at = time.perf_counter()
        executor = ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(assignments)),
            thread_name_prefix="qa-query-agent",
        )
        futures: dict[Future[AgentResult], AgentAssignment] = {
            executor.submit(self._run_assignment_with_metrics, assignment, plan, hyde_query): assignment
            for assignment in assignments
        }
        done, pending = wait(futures, timeout=self.timeout_seconds)
        by_id: dict[str, AgentResult] = {}
        for future in done:
            assignment = futures[future]
            try:
                by_id[assignment.assignment_id] = future.result()
            except Exception as exc:
                by_id[assignment.assignment_id] = AgentResult(
                    assignment=assignment,
                    status="error",
                    error=str(exc),
                )
        for future in pending:
            assignment = futures[future]
            future.cancel()
            with self._runtime_lock:
                self._timeouts += 1
            by_id[assignment.assignment_id] = AgentResult(
                assignment=assignment,
                status="timeout",
                elapsed_ms=round(self.timeout_seconds * 1000, 2),
                error=f"query agent timed out after {self.timeout_seconds:g}s",
                degraded=True,
                timed_out=True,
            )
        executor.shutdown(wait=False, cancel_futures=True)
        results = [
            by_id.get(
                assignment.assignment_id,
                AgentResult(assignment=assignment, status="error", error="missing agent result"),
            )
            for assignment in assignments
        ]
        with self._runtime_lock:
            self._rounds.append(
                {
                    "round": assignments[0].round_index,
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "assignments": [assignment.to_dict() for assignment in assignments],
                    "results": [result.diagnostic() for result in results],
                }
            )
        return results

    def diagnostics(self) -> dict[str, Any]:
        with self._runtime_lock:
            return {
                "mode": "centralized",
                "max_workers": self.max_workers,
                "peak_concurrency": self._peak_concurrency,
                "task_timeout_seconds": self.timeout_seconds,
                "timeout_count": self._timeouts,
                "rounds": list(self._rounds),
                "llm": self.llm_budget.diagnostics(),
            }
