"""The multi-step research task tool and its LLM counter audit."""

from __future__ import annotations

from typing import Any

from aika.aika_mcp.cards import (
    _cards_from_claims,
    _dedupe_cards,
    _evidence_ux_bundle,
    _normalize_cards,
    _prepend_evidence_ux,
    _renumber_cards,
)
from aika.aika_mcp.common import (
    DEPTH_LIMITS,
    BackendContext,
    _normalize_gaps,
    _require_backend_method,
    _subject,
    _success_envelope,
    _to_dict,
)
from aika.aika_mcp.markdown import _mcp_report_context
from aika.aika_mcp.queries import _collect_graph_edges
from aika.aika_mcp.schemas import RunResearchTaskRequest
from aika.aika_mcp.verify import _trace_step, _verify_result
from aika.report_type import report_title


def _run_research_task(request: RunResearchTaskRequest, context: BackendContext) -> dict[str, Any]:
    limits = DEPTH_LIMITS[request.depth]
    subject = _subject(request.topic, request.companies)
    filters = {"company": request.companies, "topic": request.topic}
    trace: list[dict[str, Any]] = []

    trace.append(_trace_step("Planner", "planned", {"topic": request.topic, "companies": request.companies, "depth": request.depth}))

    claims = context.backend.search_claims(subject, top_k=limits["claims"], **filters)
    trace.append(_trace_step("Claim Retrieval", "completed", {"result_count": len(claims)}))

    evidence_cards = context.backend.search_evidence(subject, top_k=limits["evidence"], **filters)
    trace.append(_trace_step("Evidence Retrieval", "completed", {"result_count": len(evidence_cards)}))

    graph_edges = _collect_graph_edges(context.backend, topic=request.topic, companies=request.companies, limit=limits["graph"])
    trace.append(_trace_step("Graph Retrieval", "completed", {"result_count": len(graph_edges)}))

    gaps = _require_backend_method(context.backend, "audit_evidence_gaps")(subject, companies=request.companies, topic=request.topic)
    trace.append(_trace_step("Risk/Gaps Audit", "completed", {"result_count": len(gaps)}))

    brief = _require_backend_method(context.backend, "build_research_brief")(subject, topic=request.topic)
    brief_payload = _to_dict(brief)
    trace.append(
        _trace_step(
            "Brief Builder",
            "completed",
            {
                "report_present": bool(brief_payload.get("markdown")),
                "evidence_count": len(brief_payload.get("evidence_cards", []) or []),
            },
        )
    )

    final_cards = _renumber_cards(
        _dedupe_cards(
            [
                *_normalize_cards(brief_payload.get("evidence_cards", [])),
                *_normalize_cards(evidence_cards),
                *_normalize_cards(_cards_from_claims(claims)),
            ]
        )
    )
    final_gaps = _normalize_gaps([*list(brief_payload.get("evidence_gaps", []) or []), *list(gaps or [])])
    ux = _evidence_ux_bundle(subject, context, evidence_cards=final_cards, claims=claims, gaps=final_gaps)
    coverage_context = _mcp_report_context(ux, gaps=final_gaps, companies=request.companies)
    report_markdown = _prepend_evidence_ux(str(brief_payload.get("markdown") or ""), ux, gaps=final_gaps, companies=request.companies)
    verification = _verify_result(
        report_markdown=report_markdown,
        evidence_cards=ux["evidence_cards"],
        require_citations=request.require_citations,
    )
    trace.append(_trace_step("Verification", verification["status"], verification["checks"]))

    return _success_envelope(
        "run_research_task",
        context,
        task_type=request.task_type,
        topic=request.topic,
        title=report_title(subject, coverage_context["report_type"]),
        report_type=coverage_context["report_type"],
        report_type_label=coverage_context["report_type_label"],
        coverage=coverage_context["coverage"],
        report_markdown=report_markdown,
        evidence_cards=ux["evidence_cards"],
        agent_trace=trace,
        verification=verification,
        evidence_gaps=final_gaps,
        graph_edges=[_to_dict(edge) for edge in graph_edges],
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )
