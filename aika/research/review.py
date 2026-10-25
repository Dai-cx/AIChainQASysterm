"""Reviewing claims: loading, normalising and applying reviewer edits."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aika.research.constants import CLAIM_REVIEWS_FILE, CLAIM_REVIEW_STATUSES, DEFAULT_RESEARCH_DIR, REVIEWABLE_CLAIM_FIELDS
from aika.research.claims import parse_companies


def load_claim_reviews(data_dir: Path = DEFAULT_RESEARCH_DIR) -> dict[str, dict[str, Any]]:
    reviews_path = data_dir / CLAIM_REVIEWS_FILE
    reviews: dict[str, dict[str, Any]] = {}
    if not reviews_path.exists():
        return reviews
    with reviews_path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                review = json.loads(line)
            except json.JSONDecodeError:
                continue
            claim_id = str(review.get("claim_id") or "").strip()
            if claim_id:
                reviews[claim_id] = normalize_claim_review(claim_id, review)
    return reviews


def write_claim_review(
    data_dir: Path,
    claim_id: str,
    updates: dict[str, Any],
    *,
    reviewer: str = "frontend",
) -> dict[str, Any]:
    data_dir.mkdir(parents=True, exist_ok=True)
    review = normalize_claim_review(claim_id, updates, reviewer=reviewer)
    reviews_path = data_dir / CLAIM_REVIEWS_FILE
    with reviews_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(review, ensure_ascii=False, sort_keys=True) + "\n")
    return review


def normalize_claim_review(
    claim_id: str,
    updates: dict[str, Any],
    *,
    reviewer: str = "",
) -> dict[str, Any]:
    claim_id = str(claim_id or updates.get("claim_id") or "").strip()
    if not claim_id:
        raise ValueError("claim_id is required")
    review: dict[str, Any] = {
        "claim_id": claim_id,
        "updated_at": str(updates.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        "reviewer": str(updates.get("reviewer") or reviewer or "frontend"),
    }
    for field in REVIEWABLE_CLAIM_FIELDS:
        if field not in updates:
            continue
        value = updates.get(field)
        if field == "companies":
            value = parse_companies(value)
        elif isinstance(value, list):
            value = [str(item).strip() for item in value if str(item).strip()]
        else:
            value = str(value or "").strip()
        if field == "review_status" and value and value not in CLAIM_REVIEW_STATUSES:
            value = "needs_review"
        review[field] = value
    if "review_status" not in review:
        review["review_status"] = "revised"
    return review


def apply_claim_reviews(claims: list[dict[str, Any]], reviews: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not reviews:
        return claims
    output: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = str(claim.get("claim_id") or "")
        review = reviews.get(claim_id)
        if not review:
            output.append(claim)
            continue
        updated = dict(claim)
        for field in REVIEWABLE_CLAIM_FIELDS:
            if field in review:
                updated[field] = review[field]
        updated["reviewed_at"] = review.get("updated_at", "")
        updated["reviewer"] = review.get("reviewer", "")
        output.append(updated)
    return output
