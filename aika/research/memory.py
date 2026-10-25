"""ResearchMemory: the in-memory claim store the engines query."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
from aika.domain_lexicon import text_matches_terms
from aika.aika_core.io import read_jsonl_rows
from aika.extraction_schema import read_csv

from aika.research.constants import CLAIMS_FILE, DEFAULT_RESEARCH_DIR, SEGMENT_DOSSIERS_FILE
from aika.research.hits import ResearchHit, dedupe_research_hits, diversify_research_hits
from aika.research.claims import claim_title, first_company, normalize_claim_row, parse_companies
from aika.research.review import apply_claim_reviews, load_claim_reviews, normalize_claim_review
from aika.research.scoring import dossier_to_text, query_focus_terms, query_topics, score_claim, should_use_dossier, topic_match_score


class ResearchMemory:
    def __init__(self, claims: list[dict[str, Any]], dossiers: list[dict[str, Any]]) -> None:
        self.claims = [normalize_claim_row(row) for row in claims]
        self.dossiers = dossiers

    @classmethod
    def load(cls, data_dir: Path = DEFAULT_RESEARCH_DIR) -> "ResearchMemory":
        claims_path = data_dir / CLAIMS_FILE
        dossiers_path = data_dir / SEGMENT_DOSSIERS_FILE
        if not claims_path.exists() or not dossiers_path.exists():
            raise FileNotFoundError(f"Research artifacts not found in {data_dir}")
        claims = apply_claim_reviews(read_csv(claims_path), load_claim_reviews(data_dir))
        dossiers = read_jsonl_rows(dossiers_path)
        return cls(claims, dossiers)

    def review_claim(self, claim_id: str, updates: dict[str, Any], *, reviewer: str = "frontend") -> dict[str, Any]:
        review = normalize_claim_review(claim_id, updates, reviewer=reviewer)
        for index, claim in enumerate(self.claims):
            if str(claim.get("claim_id") or "") != review["claim_id"]:
                continue
            updated = apply_claim_reviews([claim], {review["claim_id"]: review})[0]
            self.claims[index] = normalize_claim_row(updated)
            return self.claims[index]
        raise KeyError(f"Claim not found: {claim_id}")

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        for claim in self.claims:
            if str(claim.get("claim_id") or "") == str(claim_id or ""):
                return claim
        raise KeyError(f"Claim not found: {claim_id}")

    def claim_stats(self) -> dict[str, Any]:
        reviewed = sum(1 for claim in self.claims if str(claim.get("review_status", "")) in {"approved", "revised", "rejected", "needs_review"})
        rejected = sum(1 for claim in self.claims if str(claim.get("review_status", "")) == "rejected")
        direct_companies = {
            company
            for claim in self.claims
            if claim.get("claim_type") == "company_exposure" and claim.get("exposure_level") in {"core", "direct"}
            for company in parse_companies(claim.get("companies", []))
        }
        by_type: dict[str, int] = defaultdict(int)
        for claim in self.claims:
            by_type[str(claim.get("claim_type", "") or "unknown")] += 1
        return {
            "claims": len(self.claims),
            "dossiers": len(self.dossiers),
            "reviewed_claims": reviewed,
            "rejected_claims": rejected,
            "direct_exposure_companies": len(direct_companies),
            "claim_type_counts": dict(by_type),
        }

    def search(self, question: str, plan: Any, *, limit: int = 8) -> list[ResearchHit]:
        topics = query_topics(question, getattr(plan, "topics", []), getattr(plan, "expanded_topics", []))
        hits: list[ResearchHit] = []
        if should_use_dossier(question, plan):
            hits.extend(self._search_dossiers(question, topics, plan))
        hits.extend(self._search_claims(question, topics, plan))
        hits.sort(key=lambda hit: (-hit.score, hit.kind, hit.topic, hit.company, hit.title))
        return diversify_research_hits(dedupe_research_hits(hits))[:limit]

    def search_global_dossiers(
        self,
        question: str,
        plan: Any,
        *,
        limit: int = 3,
        topics: list[str] | None = None,
    ) -> list[ResearchHit]:
        """Search topic-level dossiers for broad GraphRAG/global context."""
        selected_topics = topics or query_topics(question, getattr(plan, "topics", []), getattr(plan, "expanded_topics", []))
        hits = self._search_dossiers(question, selected_topics, plan)
        hits.sort(key=lambda hit: (-hit.score, hit.topic, hit.title))
        return dedupe_research_hits(hits)[: max(0, limit)]

    def search_local_claims(
        self,
        question: str,
        plan: Any,
        *,
        limit: int = 12,
        claim_types: list[str] | set[str] | tuple[str, ...] | None = None,
        companies: list[str] | set[str] | tuple[str, ...] | None = None,
        topics: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> list[ResearchHit]:
        """Search local claim bundles with optional company/type/topic filters."""
        selected_topics = list(topics or []) or query_topics(
            question,
            getattr(plan, "topics", []),
            getattr(plan, "expanded_topics", []),
        )
        claim_type_set = {str(item) for item in (claim_types or []) if str(item)}
        company_set = {str(item) for item in (companies or getattr(plan, "companies", []) or []) if str(item)}
        hits = []
        for hit in self._search_claims(question, selected_topics, plan):
            if claim_type_set and hit.claim_type not in claim_type_set:
                continue
            if company_set and hit.company and hit.company not in company_set:
                continue
            hits.append(hit)
        hits.sort(key=lambda hit: (-hit.score, hit.claim_type, hit.topic, hit.company, hit.title))
        return diversify_research_hits(dedupe_research_hits(hits))[: max(0, limit)]

    def _search_dossiers(self, question: str, topics: list[str], plan: Any) -> list[ResearchHit]:
        hits = []
        focus_terms = query_focus_terms(question)
        for dossier in self.dossiers:
            topic = str(dossier.get("topic", ""))
            if topics and topic not in topics and not text_matches_terms(topic, topics):
                continue
            score = 25.0 + topic_match_score(topic, question, topics)
            if topics and topic == topics[0]:
                score += 5.0
            if getattr(plan, "answer_type", "") in {"industry_bottleneck", "thematic_research"}:
                score += 2.0
            text = dossier_to_text(dossier)
            if focus_terms:
                if text_matches_terms(text, focus_terms):
                    score += 4.0
                else:
                    score -= 8.0
            hits.append(
                ResearchHit(
                    kind="dossier",
                    title=f"{topic} 产业链投研摘要",
                    text=text,
                    topic=topic,
                    score=round(score, 4),
                )
            )
        return hits

    def _search_claims(self, question: str, topics: list[str], plan: Any) -> list[ResearchHit]:
        hits = []
        for claim in self.claims:
            if str(claim.get("review_status", "")) == "rejected":
                continue
            topic = str(claim.get("topic", ""))
            if topics and topic not in topics and not text_matches_terms(topic, topics):
                continue
            score = score_claim(claim, question, topics, plan)
            if score <= 0:
                continue
            company = first_company(claim.get("companies", []))
            hits.append(
                ResearchHit(
                    kind="claim",
                    title=claim_title(claim),
                    text=str(claim.get("claim_text", "")),
                    topic=topic,
                    claim_id=str(claim.get("claim_id", "")),
                    source=str(claim.get("source_title", "")),
                    page=str(claim.get("page", "")),
                    section=str(claim.get("section", "")),
                    source_tier=str(claim.get("source_tier", "")),
                    company=company,
                    claim_type=str(claim.get("claim_type", "")),
                    exposure_level=str(claim.get("exposure_level", "")),
                    confidence=str(claim.get("confidence", "")),
                    as_of_date=str(claim.get("as_of_date", "")),
                    evidence_span=str(claim.get("evidence_span", "")),
                    review_status=str(claim.get("review_status", "")),
                    reviewer_note=str(claim.get("reviewer_note", "")),
                    score=round(score, 4),
                )
            )
        return hits
