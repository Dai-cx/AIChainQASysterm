"""Row-to-model conversion and the card shaping the backend presents."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from aika.aika_core.backends.sqlite.util import _floatish, _text
from aika.aika_core.models import ClaimRecord, EvidenceCard, EvidenceGap, GraphEdge
from aika.aika_core.text import normalize_text as _normalize
from aika.aika_core.text import shorten as _short_text


def _evidence_card_from_row(row: sqlite3.Row, *, citation_id: str) -> EvidenceCard:
    data = dict(row)
    return EvidenceCard(
        citation_id=citation_id,
        kind="evidence",
        title=_text(data.get("source_title") or data.get("topic")),
        evidence=_text(data.get("evidence")),
        claim_id=_text(data.get("claim_id")),
        source=_text(data.get("source_title")),
        page=_text(data.get("page")),
        section=_text(data.get("section")),
        company=_text(data.get("company")),
        source_tier=_text(data.get("source_tier")),
        score=_floatish(data.get("score")),
        reason="sqlite fts",
        topic=_text(data.get("topic")),
        claim_type=_text(data.get("claim_type")),
        exposure_level=_text(data.get("exposure_level")),
        confidence=_text(data.get("confidence")),
        as_of_date=_text(data.get("as_of_date")),
        evidence_span=_text(data.get("evidence")),
        raw=data,
    )


def _dossier_card_from_row(row: sqlite3.Row, *, citation_id: str) -> EvidenceCard:
    data = dict(row)
    return EvidenceCard(
        citation_id=citation_id,
        kind="dossier",
        title=_text(data.get("title")),
        evidence=_text(data.get("content")),
        score=_floatish(data.get("score")),
        reason="sqlite dossier fts",
        topic=_text(data.get("topic")),
        raw=data,
    )


def _graph_edge_from_row(row: sqlite3.Row) -> GraphEdge:
    data = dict(row)
    return GraphEdge(
        source=_text(data.get("head_name")),
        target=_text(data.get("tail_name")),
        relation=_text(data.get("relation")),
        label=_text(data.get("relation")),
        source_type=_text(data.get("head_type")),
        target_type=_text(data.get("tail_type")),
        evidence=_text(data.get("evidence")),
        source_title=_text(data.get("source_title")),
        page=_text(data.get("page")),
        section=_text(data.get("section")),
        source_tier=_text(data.get("source_tier")),
        report_id=_text(data.get("source_report_id")),
        raw=data,
    )


def _claim_cards_from_records(claims: Iterable[ClaimRecord], *, start_index: int = 1) -> list[EvidenceCard]:
    return [claim.to_evidence_card(citation_id=f"E{index}") for index, claim in enumerate(claims, start=start_index)]


def _ensure_citations(cards: Iterable[EvidenceCard]) -> list[EvidenceCard]:
    output: list[EvidenceCard] = []
    for index, card in enumerate(cards, start=1):
        if card.citation_id:
            output.append(card)
            continue
        data = card.to_dict()
        data["citation_id"] = f"E{index}"
        output.append(EvidenceCard.from_any(data))
    return output


def _dedupe_evidence_cards(cards: Iterable[EvidenceCard]) -> list[EvidenceCard]:
    output: list[EvidenceCard] = []
    seen: set[tuple[str, str, str, str]] = set()
    for card in cards:
        key = (
            card.claim_id,
            card.source,
            card.page,
            _short_text(card.evidence or card.evidence_span, 180),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(card)
    return output


def _dedupe_gaps(gaps: Iterable[EvidenceGap]) -> list[EvidenceGap]:
    output: list[EvidenceGap] = []
    seen: set[str] = set()
    for gap in gaps:
        key = _normalize(gap.gap)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(gap)
    return output


def _infer_chain_segment(edges: Iterable[GraphEdge]) -> str:
    for edge in edges:
        if edge.relation in {"HAS_PRODUCT", "PART_OF_CHAIN", "ENABLES", "SUPPLIES"} and edge.target:
            return edge.target
    for edge in edges:
        if edge.target:
            return edge.target
    return "当前证据不足"


def _strongest_exposure(cards: Iterable[EvidenceCard]) -> str:
    priority = {"core": 0, "direct": 1, "indirect": 2, "mentioned": 3, "": 9}
    labels = {
        "core": "核心敞口",
        "direct": "直接敞口",
        "indirect": "间接敞口",
        "mentioned": "仅提及",
        "": "未分级",
    }
    best = ""
    for card in cards:
        if priority.get(card.exposure_level, 9) < priority.get(best, 9):
            best = card.exposure_level
    return labels.get(best, best or "未分级")


def _summarize_cards(cards: Iterable[EvidenceCard], claim_types: set[str], *, limit: int = 2) -> str:
    lines: list[str] = []
    for card in cards:
        if card.claim_type not in claim_types:
            continue
        citation = f" [{card.citation_id}]" if card.citation_id else ""
        lines.append(f"{_short_text(card.evidence, 80)}{citation}")
        if len(lines) >= limit:
            break
    return "；".join(lines) if lines else "当前证据不足"


def _card_citations(cards: Iterable[EvidenceCard]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if card.citation_id and card.citation_id not in seen:
            seen.add(card.citation_id)
            output.append(card.citation_id)
    return output


def _dossier_content(dossier: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "summary",
        "technology_mechanism",
        "industry_chain",
        "bottlenecks",
        "leading_indicators",
        "risks",
        "policies",
        "gaps",
    ):
        value = dossier.get(key)
        if isinstance(value, list):
            parts.extend(_text(item) for item in value if _text(item))
        elif isinstance(value, dict):
            parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        elif _text(value):
            parts.append(_text(value))
    return "\n".join(part for part in parts if part)
