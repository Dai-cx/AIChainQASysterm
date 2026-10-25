"""The research hit type plus the ordering and de-duplication rules."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from aika.domain_lexicon import normalize_topic
from aika.research.claims import safe_float
from aika.research.constants import EXPOSURE_ORDER


@dataclass(frozen=True)
class ResearchHit:
    kind: str
    title: str
    text: str
    topic: str
    claim_id: str = ""
    source: str = ""
    page: str = ""
    section: str = ""
    source_tier: str = ""
    company: str = ""
    claim_type: str = ""
    exposure_level: str = ""
    confidence: str = ""
    as_of_date: str = ""
    evidence_span: str = ""
    review_status: str = ""
    reviewer_note: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "topic": self.topic,
            "claim_id": self.claim_id,
            "source": self.source,
            "page": self.page,
            "section": self.section,
            "source_tier": self.source_tier,
            "company": self.company,
            "claim_type": self.claim_type,
            "exposure_level": self.exposure_level,
            "confidence": self.confidence,
            "as_of_date": self.as_of_date,
            "evidence_span": self.evidence_span,
            "review_status": self.review_status,
            "reviewer_note": self.reviewer_note,
            "score": self.score,
        }


def dedupe_research_hits(hits: list[ResearchHit]) -> list[ResearchHit]:
    output = []
    seen = set()
    for hit in hits:
        key = (hit.kind, hit.topic, hit.company, normalize_topic(hit.text)[:120])
        if key in seen:
            continue
        seen.add(key)
        output.append(hit)
    return output


def diversify_research_hits(hits: list[ResearchHit]) -> list[ResearchHit]:
    output = []
    exposure_seen: set[tuple[str, str, str]] = set()
    bucket_counts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for hit in hits:
        if hit.claim_type == "company_exposure" and hit.company:
            exposure_key = (hit.topic, hit.company, hit.exposure_level)
            if exposure_key in exposure_seen:
                continue
            exposure_seen.add(exposure_key)
        bucket_key = (hit.kind, hit.topic, hit.company, hit.claim_type)
        if bucket_counts[bucket_key] >= (1 if hit.claim_type == "company_exposure" else 2):
            continue
        bucket_counts[bucket_key] += 1
        output.append(hit)
    return output


def sorted_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(claim: dict[str, Any]) -> tuple[float, int, str]:
        confidence = safe_float(claim.get("confidence"), 0.7)
        tier_bonus = 0.2 if claim.get("source_tier") == "1" else 0.0
        exposure_rank = EXPOSURE_ORDER.get(str(claim.get("exposure_level", "")), 4)
        return (-(confidence + tier_bonus), exposure_rank, str(claim.get("claim_text", "")))

    return sorted(claims, key=key)


def top_claim_texts(claims: list[dict[str, Any]], claim_types: set[str], limit: int) -> list[str]:
    return [claim["claim_text"] for claim in sorted_claims(claims) if claim.get("claim_type") in claim_types][:limit]
