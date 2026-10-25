"""Human review of research claims (``/research/claims/{claim_id}/review``)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from aika.api.deps import get_qa_engine
from aika.api.models import ClaimReviewRequest
from aika.qa_engine import QAEngine
from aika.research_claims import normalize_claim_review

router = APIRouter()


@router.post("/research/claims/{claim_id}/review")
async def review_claim(
    claim_id: str,
    request: ClaimReviewRequest,
    engine: QAEngine = Depends(get_qa_engine),
) -> dict[str, Any]:
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No claim updates provided")
    research_memory = getattr(engine, "research_memory", None)
    if research_memory is None or not hasattr(research_memory, "get_claim"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Research memory is not available")
    try:
        research_memory.get_claim(claim_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found") from exc

    review = normalize_claim_review(claim_id, updates, reviewer="frontend")
    try:
        claim = research_memory.review_claim(claim_id, review)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found") from exc
    return {"claim": claim, "review": review}
