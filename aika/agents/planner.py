"""Dynamic planning primitives for evidence-driven QA agent runs."""

from __future__ import annotations

from aika.aika_core.domain import required_coverage

from dataclasses import asdict, dataclass, field
from typing import Any

from aika.question_planner import QuestionPlan


DEFAULT_MAX_RETRIEVAL_ROUNDS = 3


@dataclass(frozen=True)
class AgentBudget:
    max_steps: int = 4
    max_llm_calls: int = 4
    max_retrieval_rounds: int = DEFAULT_MAX_RETRIEVAL_ROUNDS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentSubtask:
    id: str
    type: str
    query_suffix: str
    required_tools: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentTaskPlan:
    task_type: str
    goal: str
    required_coverage: list[str]
    subtasks: list[AgentSubtask]
    budgets: AgentBudget

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "goal": self.goal,
            "required_coverage": list(self.required_coverage),
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
            "budgets": self.budgets.to_dict(),
        }


class TaskPlanner:
    """Turns a question plan into deterministic retrieval requirements."""

    def __init__(
        self,
        *,
        max_steps: int = 4,
        max_llm_calls: int = 4,
        max_retrieval_rounds: int = DEFAULT_MAX_RETRIEVAL_ROUNDS,
    ) -> None:
        self.budget = AgentBudget(
            max_steps=max(1, int(max_steps or 4)),
            max_llm_calls=max(0, int(max_llm_calls or 0)),
            max_retrieval_rounds=max(1, int(max_retrieval_rounds or DEFAULT_MAX_RETRIEVAL_ROUNDS)),
        )

    def plan(self, question: str, question_plan: QuestionPlan) -> AgentTaskPlan:
        required = required_coverage_for_plan(question_plan)
        subtasks = [
            AgentSubtask(
                id=f"s{index}",
                type=coverage,
                query_suffix=query_suffix_for_coverage(coverage),
                required_tools=tools_for_coverage(coverage),
                success_criteria=[coverage],
            )
            for index, coverage in enumerate(required, start=1)
        ]
        return AgentTaskPlan(
            task_type=question_plan.answer_type,
            goal=question.strip() or question_plan.question,
            required_coverage=required,
            subtasks=subtasks,
            budgets=self.budget,
        )


def required_coverage_for_plan(plan: QuestionPlan) -> list[str]:
    return required_coverage(
        plan.answer_type,
        needs_comparison=plan.needs_comparison,
        needs_risk=plan.needs_risk,
        needs_metrics=plan.needs_metrics,
        relations=plan.relations,
    )


def query_suffix_for_coverage(coverage: str) -> str:
    return {
        "company_coverage": "业务 差异 指标 风险",
        "risk_evidence": "风险 反证 不确定性 年报风险披露",
        "metric_evidence": "指标 订单 收入 毛利率 产能 客户导入 渗透率",
        "company_exposure": "公司敞口 受益 上市公司 核心敞口 直接敞口",
        "mechanism_evidence": "技术机理 瓶颈 产业传导 领先指标",
    }.get(coverage, "")


def tools_for_coverage(coverage: str) -> list[str]:
    if coverage == "company_coverage":
        return ["prepare_cypher", "query_graph", "search_research_claims", "search_rag", "search_semantic_index"]
    if coverage in {"risk_evidence", "metric_evidence", "company_exposure", "mechanism_evidence"}:
        return ["query_graph", "search_research_claims", "search_rag", "search_semantic_index"]
    return ["search_research_claims", "search_rag"]


def unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
