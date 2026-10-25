"""Reporting the verification outcome of a payload back to the caller."""

from __future__ import annotations

from typing import Any

from aika.aika_mcp.common import _jsonable


def _verify_result(
    *,
    report_markdown: str,
    evidence_cards: list[dict[str, Any]],
    require_citations: bool,
) -> dict[str, Any]:
    evidence_count = len(evidence_cards)
    cited_count = sum(1 for card in evidence_cards if card.get("citation_id"))
    uncited_count = sum(1 for card in evidence_cards if not card.get("citation_id"))
    checks = {
        "report_present": bool(report_markdown.strip()),
        "evidence_count": evidence_count,
        "cited_count": cited_count,
        "uncited_count": uncited_count,
        "require_citations": require_citations,
        "citation_coverage": round(cited_count / evidence_count, 4) if evidence_count else 0.0,
    }
    gaps: list[dict[str, str]] = []
    if not checks["report_present"]:
        gaps.append({"gap": "Research brief markdown is empty.", "priority": "high", "suggested_source": "Build a brief from retrieved evidence."})
    if require_citations and not evidence_count:
        gaps.append({"gap": "No evidence cards were retrieved.", "priority": "high", "suggested_source": "Initialize or rebuild the AIKA knowledge index."})
    if require_citations and uncited_count:
        gaps.append({"gap": "Some evidence cards are uncited.", "priority": "medium", "suggested_source": "Attach citation ids to all evidence cards."})
    if not checks["report_present"] or (require_citations and not evidence_count):
        status = "fail"
    elif gaps:
        status = "warning"
    else:
        status = "pass"
    return {"status": status, "checks": checks, "evidence_gaps": gaps}


def _trace_step(phase: str, status: str, observation: dict[str, Any]) -> dict[str, Any]:
    return {"phase": phase, "status": status, "observation": _jsonable(observation)}
