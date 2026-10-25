"""Validation and merge helpers for centralized coordination."""

from __future__ import annotations

from typing import Any

from aika.aika_core.text import shorten
from aika.agents.coverage import CoverageReport, EvidenceGap
from aika.agents.planner import query_suffix_for_coverage
from aika.graphrag import GraphRagResult, dedupe_hits
from aika.question_planner import QuestionPlan

from .models import AGENT_TYPES, AgentAssignment, EvidenceCardDraft, clean_ids, clean_strings

def validate_assignments(
    payload: Any,
    *,
    available: list[str],
    question: str,
    round_index: int,
    max_assignments: int,
) -> list[AgentAssignment]:
    if not isinstance(payload, dict) or not isinstance(payload.get("assignments"), list):
        return []
    output: list[AgentAssignment] = []
    seen: set[str] = set()
    for item in payload["assignments"]:
        if not isinstance(item, dict):
            continue
        agent_type = str(item.get("agent_type") or "").strip().casefold()
        if agent_type not in AGENT_TYPES or agent_type not in available or agent_type in seen:
            continue
        query = " ".join(str(item.get("query") or question).split())[:600]
        if not query:
            continue
        filters = item.get("filters")
        goals = clean_strings(item.get("coverage_goals"))
        output.append(
            AgentAssignment(
                assignment_id=f"r{round_index}-{agent_type}",
                agent_type=agent_type,
                query=query,
                filters=dict(filters) if isinstance(filters, dict) else {},
                coverage_goals=goals,
                round_index=round_index,
            )
        )
        seen.add(agent_type)
        if len(output) >= max_assignments:
            break
    return output

def merge_graphrag_results(
    existing: GraphRagResult | None,
    additions: list[GraphRagResult],
) -> GraphRagResult:
    results = ([existing] if existing is not None else []) + list(additions)
    latest = results[-1]
    global_hits = dedupe_hits([hit for result in results for hit in result.global_hits])
    local_hits = dedupe_hits([hit for result in results for hit in result.local_hits])
    subquestions = []
    seen_subquestions: set[str] = set()
    for result in results:
        for subquestion in result.subquestions:
            if subquestion.question in seen_subquestions:
                continue
            seen_subquestions.add(subquestion.question)
            subquestions.append(subquestion)
    return GraphRagResult(
        route=latest.route,
        subquestions=subquestions,
        global_hits=global_hits,
        local_hits=local_hits,
        paths=[],
        company_rankings=[],
        edges=[],
    )

def merge_review_coverage(
    deterministic: CoverageReport,
    llm_missing: list[str],
    plan: QuestionPlan,
) -> CoverageReport:
    missing = list(deterministic.missing)
    for coverage in llm_missing:
        if coverage not in missing:
            missing.append(coverage)
    if missing == deterministic.missing:
        return deterministic
    satisfied = [coverage for coverage in deterministic.required if coverage not in missing]
    gaps_by_coverage = {gap.coverage: gap for gap in deterministic.gaps}
    gaps = []
    for coverage in missing:
        gap = gaps_by_coverage.get(coverage)
        if gap is None:
            gap = EvidenceGap(
                coverage=coverage,
                reason=f"审核 Agent 判断 {coverage} 证据仍不充分。",
                query_suffix=query_suffix_for_coverage(coverage),
                companies=list(plan.companies) if coverage == "company_coverage" else [],
            )
        gaps.append(gap)
    if deterministic.retrieval_round >= deterministic.max_retrieval_rounds:
        status = "fail" if "metric_evidence" in missing else "warn"
        stop_reason = "max_retrieval_rounds_reached"
    else:
        status = "warn"
        stop_reason = "needs_supplement"
    return CoverageReport(
        status=status,
        required=list(deterministic.required),
        satisfied=satisfied,
        missing=missing,
        gaps=gaps,
        stop_reason=stop_reason,
        retrieval_round=deterministic.retrieval_round,
        max_retrieval_rounds=deterministic.max_retrieval_rounds,
    )

def validate_drafts(payload: Any, allowed_ids: set[str]) -> list[EvidenceCardDraft]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        return []
    drafts: list[EvidenceCardDraft] = []
    seen: set[str] = set()
    for item in payload["cards"]:
        if not isinstance(item, dict):
            continue
        ids = clean_ids(item.get("candidate_ids"), allowed_ids)
        if not ids or ids[0] in seen:
            continue
        seen.add(ids[0])
        drafts.append(
            EvidenceCardDraft(
                candidate_ids=ids,
                title=str(item.get("title") or ""),
                reason=str(item.get("reason") or ""),
            )
        )
    return drafts

def validate_conflicts(value: Any, allowed_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ids = clean_ids(item.get("candidate_ids"), allowed_ids)
        if len(ids) < 2:
            continue
        output.append({"candidate_ids": ids, "reason": shorten(str(item.get("reason") or ""), 240)})
    return output
