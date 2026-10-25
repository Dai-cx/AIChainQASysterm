"""The public MCP tool surface."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from aika.aika_mcp.common import BackendContext, RequestT, _error_envelope, _jsonable, _meta, resolve_backend
from aika.aika_mcp.pdf import _render_report_pdf
from aika.aika_mcp.queries import (
    _audit_evidence_gaps,
    _build_research_brief,
    _compare_companies,
    _get_company_profile,
    _query_industry_graph,
    _search_claims,
    _search_evidence,
)
from aika.aika_mcp.research_task import _run_research_task
from aika.aika_mcp.schemas import (
    AuditEvidenceGapsRequest,
    BuildResearchBriefRequest,
    CompanyProfileRequest,
    CompareCompaniesRequest,
    QueryIndustryGraphRequest,
    RenderReportPdfRequest,
    RunResearchTaskRequest,
    SearchClaimsRequest,
    SearchEvidenceRequest,
)


def search_evidence(payload: Mapping[str, Any] | SearchEvidenceRequest | None = None, **kwargs: Any) -> dict[str, Any]:
    return _run_tool("search_evidence", SearchEvidenceRequest, payload, kwargs, _search_evidence)


def search_claims(payload: Mapping[str, Any] | SearchClaimsRequest | None = None, **kwargs: Any) -> dict[str, Any]:
    return _run_tool("search_claims", SearchClaimsRequest, payload, kwargs, _search_claims)


def get_company_profile(
    payload: Mapping[str, Any] | CompanyProfileRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("get_company_profile", CompanyProfileRequest, payload, kwargs, _get_company_profile)


def compare_companies(
    payload: Mapping[str, Any] | CompareCompaniesRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("compare_companies", CompareCompaniesRequest, payload, kwargs, _compare_companies)


def query_industry_graph(
    payload: Mapping[str, Any] | QueryIndustryGraphRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("query_industry_graph", QueryIndustryGraphRequest, payload, kwargs, _query_industry_graph)


def build_research_brief(
    payload: Mapping[str, Any] | BuildResearchBriefRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("build_research_brief", BuildResearchBriefRequest, payload, kwargs, _build_research_brief)


def audit_evidence_gaps(
    payload: Mapping[str, Any] | AuditEvidenceGapsRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("audit_evidence_gaps", AuditEvidenceGapsRequest, payload, kwargs, _audit_evidence_gaps)


def run_research_task(
    payload: Mapping[str, Any] | RunResearchTaskRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("run_research_task", RunResearchTaskRequest, payload, kwargs, _run_research_task)


def render_report_pdf(
    payload: Mapping[str, Any] | RenderReportPdfRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    return _run_tool("render_report_pdf", RenderReportPdfRequest, payload, kwargs, _render_report_pdf)


def tool_names() -> list[str]:
    return [
        "search_evidence",
        "search_claims",
        "get_company_profile",
        "compare_companies",
        "query_industry_graph",
        "build_research_brief",
        "audit_evidence_gaps",
        "run_research_task",
        "render_report_pdf",
    ]


def _run_tool(
    tool: str,
    model: type[RequestT],
    payload: Mapping[str, Any] | RequestT | None,
    kwargs: dict[str, Any],
    handler: Callable[[RequestT, BackendContext], dict[str, Any]],
) -> dict[str, Any]:
    try:
        request = _parse_request(model, payload, kwargs)
    except ValidationError as exc:
        return _error_envelope(
            tool,
            meta={"backend": "unresolved", "warnings": []},
            error_type="validation_error",
            message="Invalid MCP tool arguments.",
            details=_jsonable(exc.errors()),
        )
    except ValueError as exc:
        return _error_envelope(
            tool,
            meta={"backend": "unresolved", "warnings": []},
            error_type="validation_error",
            message=str(exc),
            details={},
        )

    context: BackendContext | None = None
    try:
        context = resolve_backend(request)
        return handler(request, context)
    except Exception as exc:  # pragma: no cover - defensive MCP boundary.
        meta = _meta(context) if context is not None else {"backend": "unresolved", "warnings": []}
        return _error_envelope(tool, meta=meta, error_type=exc.__class__.__name__, message=str(exc), details={})


def _parse_request(
    model: type[RequestT],
    payload: Mapping[str, Any] | RequestT | None,
    kwargs: dict[str, Any],
) -> RequestT:
    if isinstance(payload, model):
        data = payload.model_dump()
    elif payload is None:
        data = {}
    elif isinstance(payload, Mapping):
        data = dict(payload)
    else:
        raise ValueError(f"payload must be a mapping or {model.__name__}")
    data.update(kwargs)
    return model.model_validate(data)


# The handlers moved into sibling modules; re-export them so `tools.<name>` keeps working
# for the server, the tests and anything that reached into this module before the split.
from aika.aika_mcp.cards import (  # noqa: F401,E402
    _cards_from_claims,
    _claims_from_payload,
    _dedupe_cards,
    _evidence_ux_bundle,
    _normalize_cards,
    _prepend_evidence_ux,
    _renumber_cards,
)
from aika.aika_mcp.common import _llm_counter_audit, _normalize_gaps  # noqa: F401,E402
from aika.aika_mcp.markdown import (  # noqa: F401,E402
    _compose_research_markdown,
    _conclusion_citations,
    _coverage_score,
    _dedupe_report_gaps,
    _evidence_appendix_lines,
    _evidence_summary_line,
    _is_direct_card,
    _mcp_company_coverage,
    _mcp_report_context,
    _mcp_usage_line,
    _strip_composed_sections,
)
from aika.aika_mcp.pdf import (  # noqa: F401,E402
    _charts_present,
    _report_spec_for_pdf,
)
from aika.aika_mcp.queries import (  # noqa: F401,E402
    _collect_graph_edges,
)
from aika.aika_mcp.verify import _trace_step, _verify_result  # noqa: F401,E402
