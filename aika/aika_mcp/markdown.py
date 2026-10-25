"""Markdown assembly for the research brief and coverage audit payloads."""

from __future__ import annotations

from typing import Any
from aika.report_type import CoverageMetrics, aggregate_freshness_status, classify_report_type, report_type_label, report_usability

from aika.aika_mcp.common import _normalize_gaps, _short_text


def _compose_research_markdown(
    report_markdown: str,
    ux: dict[str, Any],
    *,
    gaps: list[Any] | None = None,
    companies: list[str] | None = None,
) -> str:
    conclusions = list(ux.get("conclusions") or [])
    evidence_cards = list(ux.get("evidence_cards") or [])
    cards = {str(card.get("evidence_id") or ""): card for card in evidence_cards}
    links = list(ux.get("evidence_links") or [])
    by_conclusion: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        if not isinstance(link, dict):
            continue
        conclusion_id = str(link.get("conclusion_id") or "")
        card = cards.get(str(link.get("evidence_id") or ""))
        if conclusion_id and card:
            by_conclusion.setdefault(conclusion_id, []).append(card)

    gap_rows = _dedupe_report_gaps(_normalize_gaps(gaps or []))
    supported = [row for row in conclusions if str(row.get("evidence_status") or "") == "supported"]
    unsupported = [row for row in conclusions if str(row.get("evidence_status") or "") != "supported"]
    meta = dict(ux.get("evidence_ux_meta") or {})
    coverage_context = _mcp_report_context(ux, gaps=gap_rows, companies=companies)
    coverage = coverage_context["coverage"]
    coverage_score = float(coverage.get("coverage_score") or 0.0)
    report_type = str(coverage_context["report_type"])
    usability = str(coverage_context["usability"])

    lines: list[str] = [
        "## 一页结论",
        "",
        "### 本次报告能回答什么",
    ]
    if supported:
        for conclusion in supported[:4]:
            citations = _conclusion_citations(str(conclusion.get("conclusion_id") or ""), by_conclusion)
            suffix = f"（支撑证据：{citations}）" if citations else "（支撑证据：当前证据不足）"
            lines.append(f"- {_short_text(str(conclusion.get('conclusion_text') or ''), 160)}{suffix}")
    else:
        lines.append("- 当前证据不足，无法形成可验证结论。")

    lines.extend(["", "### 本次报告不能回答什么"])
    if gap_rows:
        for gap in gap_rows[:5]:
            lines.append(f"- {_short_text(str(gap.get('gap') or gap.get('reason') or ''), 160)}")
    elif unsupported:
        for conclusion in unsupported[:3]:
            lines.append(f"- {_short_text(str(conclusion.get('conclusion_text') or '当前证据不足。'), 160)}")
    else:
        lines.append("- 当前未识别出明确证据缺口；仍需回到证据附录核验来源和适用边界。")

    lines.extend(
        [
            "",
            "### 当前报告适合的使用方式",
            f"- Report Type: `{report_type}`（{coverage_context['report_type_label']}）",
            f"- Direct Claim Ratio: {float(coverage.get('direct_claim_ratio') or 0.0):.0%}",
            f"- Conclusion Usability: {usability}",
            _mcp_usage_line(report_type),
            "",
            "## 证据覆盖评级",
            "",
            f"- Coverage: {coverage_score:.0%}",
            f"- Company Coverage: {float(coverage.get('company_coverage') or 0.0):.0%}",
            f"- Direct Claim Ratio: {float(coverage.get('direct_claim_ratio') or 0.0):.0%}",
            f"- Evidence Cards: {len(evidence_cards)}",
            f"- Supported Conclusions: {len(supported)}/{len(conclusions)}",
            f"- Unsupported Claims: {int(coverage.get('unsupported_claims') or 0)}",
            f"- Source Freshness: {coverage.get('freshness_status') or 'unknown'}",
            f"- Evidence Gaps: {len(gap_rows) if gap_rows else int(meta.get('gap_count') or 0)}",
            f"- Counter Evidence Flags: {int(meta.get('counter_evidence_count') or 0)}",
            "",
            "## 关键发现",
            "",
        ]
    )
    if report_type == "evidence_coverage_audit":
        lines.extend(["", "- 覆盖审计提醒：证据覆盖低或直接证据占比不足，系统已自动降级为覆盖审计报告。"])
    if conclusions:
        for conclusion in conclusions[:3]:
            status = str(conclusion.get("evidence_status") or "insufficient")
            citations = _conclusion_citations(str(conclusion.get("conclusion_id") or ""), by_conclusion)
            evidence_note = citations if citations else "当前证据不足"
            lines.append(
                f"- {_short_text(str(conclusion.get('conclusion_text') or '当前证据不足。'), 180)}"
                f"（证据状态：{status}；证据：{evidence_note}）"
            )
    else:
        lines.append("- 当前证据不足，无法生成关键发现。")

    body = _strip_composed_sections(str(report_markdown or "").strip())
    if body:
        lines.extend(["", "## 正文分析", "", body])

    lines.extend(["", "## Evidence Review"])
    if not conclusions:
        lines.append("当前证据不足。")
    for conclusion in conclusions[:6]:
        conclusion_id = str(conclusion.get("conclusion_id") or "")
        text = _short_text(str(conclusion.get("conclusion_text") or "当前证据不足。"), 180)
        status = str(conclusion.get("evidence_status") or "insufficient")
        lines.append(f"- 结论 {conclusion_id}: {text}（证据状态：{status}）")
        linked_cards = by_conclusion.get(conclusion_id, [])[:3]
        if not linked_cards:
            lines.append("  - 证据摘要：当前证据不足。")
            continue
        for card in linked_cards:
            lines.append("  - " + _evidence_summary_line(card))

    lines.extend(["", "## 证据附录"])
    if not evidence_cards:
        lines.append("当前证据不足。")
    for card in evidence_cards:
        lines.extend(["", *_evidence_appendix_lines(card)])

    return "\n".join(lines).strip()


def _coverage_score(conclusions: list[dict[str, Any]], gaps: list[dict[str, Any]], evidence_cards: list[dict[str, Any]]) -> float:
    if not evidence_cards:
        return 0.0
    supported = sum(1 for conclusion in conclusions if str(conclusion.get("evidence_status") or "") == "supported")
    denominator = max(len(conclusions) + len(gaps), 1)
    return max(0.0, min(1.0, supported / denominator))


def _mcp_report_context(
    ux: dict[str, Any],
    *,
    gaps: list[Any] | None = None,
    companies: list[str] | None = None,
) -> dict[str, Any]:
    conclusions = list(ux.get("conclusions") or [])
    evidence_cards = list(ux.get("evidence_cards") or [])
    gap_rows = _dedupe_report_gaps(_normalize_gaps(gaps or []))
    coverage_score = _coverage_score(conclusions, gap_rows, evidence_cards)
    direct_count = sum(1 for card in evidence_cards if _is_direct_card(card))
    direct_claim_ratio = direct_count / max(len(evidence_cards), 1) if evidence_cards else 0.0
    company_coverage = _mcp_company_coverage(evidence_cards, companies or [])
    unsupported = [row for row in conclusions if str(row.get("evidence_status") or "") != "supported"]
    freshness = aggregate_freshness_status(
        [
            str(card.get("freshness_status") or card.get("published_at") or card.get("as_of_date") or "")
            for card in evidence_cards
            if isinstance(card, dict)
        ]
    )
    metrics = CoverageMetrics(
        coverage_score=coverage_score,
        company_coverage=company_coverage,
        direct_claim_ratio=direct_claim_ratio,
        unsupported_claims=len(gap_rows) + len(unsupported),
        freshness_status=freshness,
    )
    report_type = classify_report_type(metrics.coverage_score, metrics.company_coverage, metrics.direct_claim_ratio)
    return {
        "coverage": metrics.to_dict(),
        "report_type": report_type,
        "report_type_label": report_type_label(report_type),
        "usability": report_usability(report_type),
    }


def _is_direct_card(card: dict[str, Any]) -> bool:
    return (
        str(card.get("claim_type") or "") == "company_exposure"
        and str(card.get("exposure_level") or "") in {"core", "direct"}
    )


def _mcp_company_coverage(evidence_cards: list[dict[str, Any]], companies: list[str]) -> float:
    targets = [str(company).strip() for company in companies if str(company).strip()]
    if not targets:
        return 1.0
    covered = {str(card.get("company") or "").strip() for card in evidence_cards if str(card.get("company") or "").strip()}
    return max(0.0, min(1.0, len([company for company in targets if company in covered]) / max(len(targets), 1)))


def _mcp_usage_line(report_type: str) -> str:
    if report_type == "evidence_coverage_audit":
        return "- 覆盖审计提醒：当前证据覆盖不足，本报告只适合识别证据边界和补数方向，不应当作为完整深度结论使用。"
    if report_type == "preliminary_research_brief":
        return "- 适合作为初步研究简报使用；需要完整投研结论时，应补充缺口证据后再升级报告类型。"
    if report_type == "industry_research_report":
        return "- 适合作为带证据边界的产业分析报告使用；关键投资判断仍需回到证据附录核验。"
    return "- 适合作为深度研究报告使用；仍需保留证据附录用于审计和复核。"


def _dedupe_report_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for gap in gaps:
        text = " ".join(str(gap.get("gap") or gap.get("reason") or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(gap)
    return output


def _strip_composed_sections(markdown: str) -> str:
    if not markdown:
        return ""
    drop_titles = {"一页结论", "证据覆盖审计", "证据摘要", "证据附录"}
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []
    preface: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current_title:
                sections.append((current_title, current_lines))
            elif current_lines:
                preface.extend(current_lines)
            current_title = line[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_title:
        sections.append((current_title, current_lines))
    elif current_lines:
        preface.extend(current_lines)

    kept: list[str] = [line for line in preface if line.strip()]
    for title, lines in sections:
        if title in drop_titles:
            continue
        kept.extend(lines)
    return "\n".join(kept).strip()


def _conclusion_citations(conclusion_id: str, by_conclusion: dict[str, list[dict[str, Any]]]) -> str:
    citations = []
    for card in by_conclusion.get(conclusion_id, []):
        citation = str(card.get("citation_id") or card.get("evidence_id") or "").strip()
        if citation and citation not in citations:
            citations.append(f"[{citation}]")
    return " ".join(citations[:5])


def _evidence_summary_line(card: dict[str, Any]) -> str:
    citation = str(card.get("citation_id") or card.get("evidence_id") or "未编号")
    page_or_section = str(card.get("page") or card.get("section") or card.get("paragraph_id") or "未标注")
    return (
        f"[{citation}] 来源：{card.get('source_title') or card.get('source') or '未标注'}；"
        f"日期：{card.get('published_at') or 'unknown'}；"
        f"页码/段落：{page_or_section}；"
        f"claim 类型：{card.get('claim_type') or 'unknown'}；"
        f"置信度：{card.get('confidence') or 'unknown'}；"
        f"时效：{card.get('freshness_status') or 'unknown'}；"
        f"反证：{card.get('counter_evidence_status') or 'none'}"
    )


def _evidence_appendix_lines(card: dict[str, Any]) -> list[str]:
    citation = str(card.get("citation_id") or card.get("evidence_id") or "未编号")
    source = str(card.get("source_title") or card.get("source") or card.get("title") or "未标注")
    page_or_section = str(card.get("page") or card.get("section") or card.get("paragraph_id") or "未标注")
    evidence_text = _short_text(str(card.get("evidence") or card.get("evidence_span") or ""), 420) or "未提供。"
    return [
        f"### [{citation}] {source}",
        f"- 来源：{source}",
        f"- 日期：{card.get('published_at') or 'unknown'}",
        f"- 页码/段落：{page_or_section}",
        f"- Claim 类型：{card.get('claim_type') or 'unknown'}",
        f"- 置信度：{card.get('confidence') or 'unknown'}",
        f"- 时效：{card.get('freshness_status') or 'unknown'}",
        f"- 反证状态：{card.get('counter_evidence_status') or 'none'}",
        f"- 证据原文：{evidence_text}",
    ]
