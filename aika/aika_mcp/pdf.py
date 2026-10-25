"""The PDF tool: building the report spec and rendering it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aika.aika_core.backends.sqlite_backend import resolve_aika_home
from aika.aika_mcp.schemas import RenderReportPdfRequest
from aika.report import PdfRenderError, ReportSpec, render_html, render_report_pdf as export_report_pdf

from aika.aika_mcp.common import BackendContext, _error_envelope, _meta, _require_backend_method, _success_envelope, _to_dict


def _render_report_pdf(request: RenderReportPdfRequest, context: BackendContext) -> dict[str, Any]:
    try:
        spec = _report_spec_for_pdf(request, context)
        html = render_html(spec)
        output_dir = Path(request.output_dir).expanduser() if request.output_dir else resolve_aika_home(request.home) / "reports"
        paths = export_report_pdf(spec, output_dir=output_dir, html=html)
    except PdfRenderError as exc:
        return _error_envelope(
            "render_report_pdf",
            meta=_meta(context),
            error_type="pdf_render_error",
            message=str(exc),
            details={"fix": exc.fix},
        )
    return _success_envelope(
        "render_report_pdf",
        context,
        title=spec.title,
        report_type=spec.report_type,
        report_type_label=spec.report_type_label,
        coverage=spec.coverage.model_dump(),
        charts_present=_charts_present(spec),
        html_path=paths["html_path"],
        pdf_path=paths["pdf_path"],
    )


def _report_spec_for_pdf(request: RenderReportPdfRequest, context: BackendContext) -> ReportSpec:
    if request.report_spec:
        return ReportSpec.model_validate(request.report_spec)
    query = request.query or f"{request.topic}投研简报"
    brief = _require_backend_method(context.backend, "build_research_brief")(query, topic=request.topic)
    payload = _to_dict(brief)
    report = (payload.get("research_outputs") or {}).get("report") if isinstance(payload.get("research_outputs"), dict) else {}
    spec_data = report.get("spec") if isinstance(report, dict) else None
    if not spec_data:
        raise ValueError("Backend research brief did not include report.spec.")
    return ReportSpec.model_validate(spec_data)


def _charts_present(spec: ReportSpec) -> dict[str, bool]:
    charts = spec.charts
    return {
        "evidence_strength_bar": any(charts.evidence_strength_bar.counts.values()),
        "source_freshness_timeline": bool(charts.source_freshness_timeline.items),
        "company_coverage_heatmap": bool(charts.company_coverage_heatmap.cells),
        "flow_map": bool(charts.flow_map.links),
    }
