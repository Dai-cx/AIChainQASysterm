"""Normalising, de-duplicating and renumbering the evidence cards of a payload."""

from __future__ import annotations

from typing import Any

from aika.aika_core.evidence import build_evidence_ux_bundle, freshness_status
from aika.aika_core.models import ClaimRecord, EvidenceCard

from aika.aika_mcp.common import BackendContext, _llm_counter_audit, _to_dict
from aika.aika_mcp.markdown import _compose_research_markdown


def _cards_from_claims(claims: list[ClaimRecord]) -> list[EvidenceCard]:
    return [claim.to_evidence_card(citation_id=f"E{index}") for index, claim in enumerate(claims, start=1)]


def _normalize_cards(cards: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(list(cards or []), start=1):
        card = _to_dict(item)
        citation_id = str(card.get("citation_id") or "").strip()
        card["citation_status"] = "cited" if citation_id else "uncited"
        card["source_title"] = str(card.get("source_title") or card.get("source") or card.get("title") or "").strip()
        card["published_at"] = str(card.get("published_at") or card.get("as_of_date") or "").strip()
        card["freshness_status"] = str(card.get("freshness_status") or freshness_status(card["published_at"]))
        card["evidence_id"] = str(citation_id or card.get("claim_id") or f"UXE{index}").strip()
        card["counter_evidence_status"] = str(card.get("counter_evidence_status") or "none")
        card["counter_evidence_summary"] = str(card.get("counter_evidence_summary") or "当前样本未检出反证。")
        card["supported_conclusion_ids"] = list(card.get("supported_conclusion_ids") or [])
        card["contradicted_conclusion_ids"] = list(card.get("contradicted_conclusion_ids") or [])
        normalized.append(card)
    return normalized


def _dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for card in cards:
        key = (
            str(card.get("claim_id") or ""),
            str(card.get("source") or card.get("source_title") or ""),
            str(card.get("page") or ""),
            str(card.get("evidence") or card.get("evidence_span") or "")[:160],
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(card)
    return output


def _renumber_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, card in enumerate(cards, start=1):
        row = dict(card)
        if row.get("citation_status") != "uncited":
            row["citation_id"] = f"E{index}"
            row["evidence_id"] = row["citation_id"]
            row["citation_status"] = "cited"
        output.append(row)
    return output


def _claims_from_payload(payload: dict[str, Any]) -> list[ClaimRecord]:
    rows: list[Any] = []
    if isinstance(payload.get("claims"), list):
        rows.extend(payload.get("claims") or [])
    outputs = payload.get("research_outputs") or {}
    if isinstance(outputs, dict):
        for key in ("claims", "claim_records"):
            if isinstance(outputs.get(key), list):
                rows.extend(outputs.get(key) or [])
    claims: list[ClaimRecord] = []
    seen: set[str] = set()
    for row in rows:
        data = _to_dict(row)
        if not data:
            continue
        claim = ClaimRecord.from_row(data, score=float(data.get("score") or 0.0))
        key = claim.claim_id or claim.claim_text
        if key and key not in seen:
            seen.add(key)
            claims.append(claim)
    return claims


def _evidence_ux_bundle(
    subject: str,
    context: BackendContext,
    *,
    evidence_cards: list[dict[str, Any]],
    claims: list[ClaimRecord],
    gaps: list[Any] | None = None,
) -> dict[str, Any]:
    audit = _llm_counter_audit(context, subject=subject, evidence_cards=evidence_cards, claims=claims)
    return build_evidence_ux_bundle(
        subject,
        evidence_cards,
        claims=claims,
        gaps=gaps or [],
        llm_counter_audit=audit,
    )


def _prepend_evidence_ux(
    report_markdown: str,
    ux: dict[str, Any],
    gaps: list[Any] | None = None,
    companies: list[str] | None = None,
) -> str:
    return _compose_research_markdown(report_markdown, ux, gaps=gaps, companies=companies)
