"""The read-only query tools: evidence, claims, profiles, comparison, graph, brief, gaps."""

from __future__ import annotations

from typing import Any
from aika.aika_core.evidence import build_evidence_ux_bundle
from aika.aika_core.models import ResearchBackend
from aika.aika_mcp.schemas import AuditEvidenceGapsRequest, BuildResearchBriefRequest, CompareCompaniesRequest, CompanyProfileRequest, QueryIndustryGraphRequest, SearchClaimsRequest, SearchEvidenceRequest
from aika.report_type import report_title

from aika.aika_mcp.common import BackendContext, _filters, _normalize_gaps, _require_backend_method, _subject, _success_envelope, _to_dict
from aika.aika_mcp.cards import _cards_from_claims, _claims_from_payload, _evidence_ux_bundle, _normalize_cards, _prepend_evidence_ux
from aika.aika_mcp.markdown import _mcp_report_context


def _search_evidence(request: SearchEvidenceRequest, context: BackendContext) -> dict[str, Any]:
    cards = context.backend.search_evidence(request.query, top_k=request.top_k, **_filters(request))
    evidence_cards = _normalize_cards(cards)
    ux = _evidence_ux_bundle(request.query, context, evidence_cards=evidence_cards, claims=[])
    return _success_envelope(
        "search_evidence",
        context,
        query=request.query,
        evidence_cards=ux["evidence_cards"],
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )


def _search_claims(request: SearchClaimsRequest, context: BackendContext) -> dict[str, Any]:
    claims = context.backend.search_claims(request.query, top_k=request.top_k, **_filters(request))
    evidence_cards = _normalize_cards(_cards_from_claims(claims))
    ux = _evidence_ux_bundle(request.query, context, evidence_cards=evidence_cards, claims=claims)
    return _success_envelope(
        "search_claims",
        context,
        query=request.query,
        claims=[_to_dict(claim) for claim in claims],
        evidence_cards=ux["evidence_cards"],
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )


def _get_company_profile(request: CompanyProfileRequest, context: BackendContext) -> dict[str, Any]:
    profile = context.backend.get_company_profile(request.company, topic=request.topic)
    payload = _to_dict(profile)
    evidence_cards = _normalize_cards(payload.get("evidence_cards", []))
    claims = _claims_from_payload(payload)
    subject = _subject(request.topic or request.company, [request.company])
    ux = _evidence_ux_bundle(
        subject,
        context,
        evidence_cards=evidence_cards,
        claims=claims,
        gaps=payload.get("evidence_gaps", []),
    )
    return _success_envelope(
        "get_company_profile",
        context,
        company_profile=payload,
        evidence_cards=ux["evidence_cards"],
        evidence_gaps=_normalize_gaps(payload.get("evidence_gaps", [])),
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )


def _compare_companies(request: CompareCompaniesRequest, context: BackendContext) -> dict[str, Any]:
    comparison = _require_backend_method(context.backend, "compare_companies")(request.companies, topic=request.topic)
    payload = _to_dict(comparison)
    evidence_cards = _normalize_cards(payload.get("evidence_cards", []))
    ux = _evidence_ux_bundle(
        _subject(request.topic, request.companies),
        context,
        evidence_cards=evidence_cards,
        claims=_claims_from_payload(payload),
        gaps=payload.get("evidence_gaps", []),
    )
    return _success_envelope(
        "compare_companies",
        context,
        comparison=payload,
        evidence_cards=ux["evidence_cards"],
        evidence_gaps=_normalize_gaps(payload.get("evidence_gaps", [])),
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )


def _query_industry_graph(request: QueryIndustryGraphRequest, context: BackendContext) -> dict[str, Any]:
    edges = context.backend.query_graph(
        company=request.company,
        technology=request.technology,
        relation_type=request.relation_type,
        limit=request.limit,
    )
    return _success_envelope(
        "query_industry_graph",
        context,
        graph_edges=[_to_dict(edge) for edge in edges],
        conclusions=[],
        evidence_links=[],
        counter_evidence=[],
    )


def _build_research_brief(request: BuildResearchBriefRequest, context: BackendContext) -> dict[str, Any]:
    query = request.query or f"{request.topic}投研简报"
    brief = _require_backend_method(context.backend, "build_research_brief")(query, topic=request.topic)
    payload = _to_dict(brief)
    evidence_cards = _normalize_cards(payload.get("evidence_cards", []))
    claims = _claims_from_payload(payload)
    gaps = _normalize_gaps(payload.get("evidence_gaps", []))
    ux = _evidence_ux_bundle(query, context, evidence_cards=evidence_cards, claims=claims, gaps=gaps)
    coverage_context = _mcp_report_context(ux, gaps=gaps)
    report_markdown = _prepend_evidence_ux(str(payload.get("markdown") or ""), ux, gaps=gaps)
    return _success_envelope(
        "build_research_brief",
        context,
        title=report_title(request.topic or query, coverage_context["report_type"]),
        report_type=coverage_context["report_type"],
        report_type_label=coverage_context["report_type_label"],
        coverage=coverage_context["coverage"],
        report_markdown=report_markdown,
        sections=payload.get("sections", []),
        evidence_cards=ux["evidence_cards"],
        evidence_gaps=gaps,
        research_outputs=payload.get("research_outputs", {}),
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )


def _audit_evidence_gaps(request: AuditEvidenceGapsRequest, context: BackendContext) -> dict[str, Any]:
    gaps = _require_backend_method(context.backend, "audit_evidence_gaps")(
        request.query,
        companies=request.companies,
        topic=request.topic,
    )
    ux = build_evidence_ux_bundle(
        request.query or _subject(request.topic, request.companies),
        [],
        claims=[],
        gaps=gaps,
    )
    return _success_envelope(
        "audit_evidence_gaps",
        context,
        evidence_gaps=_normalize_gaps(gaps),
        conclusions=ux["conclusions"],
        evidence_links=ux["evidence_links"],
        counter_evidence=ux["counter_evidence"],
        evidence_ux_meta=ux["evidence_ux_meta"],
    )


def _collect_graph_edges(
    backend: ResearchBackend,
    *,
    topic: str,
    companies: list[str],
    limit: int,
) -> list[Any]:
    edges: list[Any] = []
    if companies:
        per_company = max(1, limit // max(len(companies), 1))
        for company in companies:
            edges.extend(backend.query_graph(company=company, technology=topic, limit=per_company))
    else:
        edges.extend(backend.query_graph(technology=topic, limit=limit))
    return edges[:limit]
