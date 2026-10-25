"""Markdown / JSON rendering and response-header helpers for the export endpoints."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote


def attachment_headers(ascii_fallback: str, filename: str) -> dict[str, str]:
    """Build the same ``Content-Disposition`` header the export routes have always sent."""
    return {"Content-Disposition": f"attachment; filename={ascii_fallback}; filename*=UTF-8''{quote(filename)}"}


def agent_task_json(task: dict[str, Any]) -> str:
    return json.dumps(task, ensure_ascii=False, indent=2)


def agent_task_markdown(task: dict[str, Any]) -> str:
    final_outputs = task.get("final_outputs") if isinstance(task.get("final_outputs"), dict) else {}
    research_outputs = task.get("research_outputs") if isinstance(task.get("research_outputs"), dict) else {}
    report = research_outputs.get("report") if isinstance(research_outputs, dict) else {}
    if not isinstance(report, dict):
        report = {}
    title = str(final_outputs.get("report_title") or report.get("title") or task.get("title") or "Agent 研究任务")
    report_markdown = str(final_outputs.get("report_markdown") or report.get("markdown") or final_outputs.get("qa_answer") or "")
    task_type = str(final_outputs.get("task_type") or task.get("task_type") or "")
    task_label = str(final_outputs.get("task_label") or task_type or "Agent 任务")
    lines = [
        f"# {title}",
        "",
        f"- 任务 ID：{task.get('task_id', '')}",
        f"- 任务类型：{task_label}（{task_type}）",
        f"- 状态：{task.get('status', '')}",
        f"- 用户目标：{task.get('goal', '')}",
        f"- 更新时间：{task.get('updated_at', '')}",
        "",
    ]
    task_outputs = research_outputs.get("task_outputs") if isinstance(research_outputs, dict) else {}
    task_output_markdown = agent_task_outputs_markdown(task_outputs if isinstance(task_outputs, dict) else {})
    if task_output_markdown:
        lines.extend([task_output_markdown, ""])
    if report_markdown:
        lines.extend([report_markdown, ""])
    gaps = research_outputs.get("evidence_gaps") if isinstance(research_outputs, dict) else []
    if isinstance(gaps, list) and gaps:
        lines.extend(["## 证据缺口", ""])
        for gap in gaps:
            if isinstance(gap, dict):
                lines.append(f"- {gap.get('gap', '')}（{gap.get('priority', '')}）")
        lines.append("")
    return "\n".join(lines)


def agent_task_outputs_markdown(task_outputs: dict[str, Any]) -> str:
    if not task_outputs:
        return ""
    schema_type = str(task_outputs.get("schema_type") or "")
    lines = ["## 任务结构化输出", "", f"- Schema：{schema_type or 'unknown'}", ""]
    title_map = {
        "compare_table": "公司对比表",
        "common_drivers": "共同驱动",
        "differences": "差异点",
        "risk_differences": "风险差异",
        "profile": "公司画像",
        "business_position": "业务卡位",
        "technology_products": "产品/技术",
        "indicators": "指标证据",
        "risks": "风险",
        "risk_checklist": "风险清单",
        "counter_evidence": "反证/边界",
        "follow_up_indicators": "跟踪指标",
        "evidence_gaps": "证据缺口",
        "missing_companies": "缺失公司证据",
        "missing_metrics": "缺失指标证据",
        "missing_risks": "缺失风险证据",
        "suggested_sources": "建议补充来源",
        "evidence_index": "证据索引",
    }
    for key, title in title_map.items():
        value = task_outputs.get(key)
        block = markdown_value_preview(value)
        if block:
            lines.extend([f"### {title}", "", block, ""])
    return "\n".join(lines).strip()


def markdown_value_preview(value: Any) -> str:
    if isinstance(value, dict):
        rows = value.get("rows")
        if isinstance(rows, list):
            return markdown_value_preview(rows)
        items = [(str(key), str(item)) for key, item in value.items() if item not in (None, "", [], {})]
        return "\n".join(f"- {key}：{item}" for key, item in items[:8])
    if isinstance(value, list):
        lines: list[str] = []
        for item in value[:8]:
            if isinstance(item, dict):
                text = str(
                    item.get("gap")
                    or item.get("risk")
                    or item.get("risks")
                    or item.get("evidence")
                    or item.get("indicator")
                    or item.get("business_position")
                    or item.get("suggested_source")
                    or item.get("company")
                    or item.get("scope")
                    or item
                )
                extra = str(item.get("citation_id") or item.get("priority") or "")
                lines.append(f"- {text}" + (f"（{extra}）" if extra else ""))
            elif item:
                lines.append(f"- {item}")
        return "\n".join(lines)
    if isinstance(value, str):
        return value
    return ""
