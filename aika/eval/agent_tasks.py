"""The multi-task ResearchAgent evaluation set and its scoring rule.

The cases live in the package rather than under ``scripts/`` so that ``aika eval --suite agent``
works from an installed wheel, where ``scripts/`` does not exist.
"""

from __future__ import annotations

from typing import Any

AGENT_EVAL_CASES: list[tuple[str, str]] = [
    ("research_brief", "液冷产业链"),
    ("research_brief", "光模块产业链"),
    ("research_brief", "国产算力产业链"),
    ("company_compare", "中际旭创和新易盛在光模块业务上的差异"),
    ("company_compare", "英维克和申菱环境液冷业务对比"),
    ("company_compare", "浪潮信息和工业富联AI服务器业务对比"),
    ("company_profile", "英维克液冷业务画像"),
    ("company_profile", "中际旭创光模块业务画像"),
    ("company_profile", "浪潮信息AI服务器业务画像"),
    ("risk_review", "英维克液冷业务主要风险"),
    ("risk_review", "AI服务器产业链风险审查"),
    ("risk_review", "光模块需求波动风险"),
    ("evidence_gap_audit", "液冷产业链证据缺口"),
    ("evidence_gap_audit", "国产算力指标证据缺口"),
    ("evidence_gap_audit", "光模块公司风险证据缺口"),
]


def score_task(task: dict[str, Any]) -> tuple[int, list[str]]:
    """Score one finished task: 2 = fully formed, 1 = minor gaps, 0 = unusable."""
    failures: list[str] = []
    final_outputs = task.get("final_outputs", {})
    research_outputs = task.get("research_outputs", {})
    evidence_cards = task.get("evidence_cards", [])
    gaps = research_outputs.get("evidence_gaps", []) if isinstance(research_outputs, dict) else []
    if task.get("status") != "completed":
        failures.append("not_completed")
    if not final_outputs.get("report_title"):
        failures.append("missing_report_title")
    if not final_outputs.get("report_markdown"):
        failures.append("missing_report_markdown")
    if not research_outputs:
        failures.append("missing_research_outputs")
    task_outputs = research_outputs.get("task_outputs") if isinstance(research_outputs, dict) else {}
    if not isinstance(task_outputs, dict) or task_outputs.get("schema_type") != task.get("task_type"):
        failures.append("missing_task_outputs")
    if not evidence_cards and not gaps:
        failures.append("missing_evidence_or_gap")
    if not failures:
        return 2, failures
    if len(failures) <= 2:
        return 1, failures
    return 0, failures
