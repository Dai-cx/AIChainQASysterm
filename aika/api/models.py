"""Pydantic request models for the public API."""

from __future__ import annotations

from pydantic import BaseModel


class ConversationCreateRequest(BaseModel):
    title: str = ""


class ConversationTitleRequest(BaseModel):
    title: str


class MessageCreateRequest(BaseModel):
    question: str
    thinking_enabled: bool | None = None
    reasoning_effort: str | None = None


class AgentTaskCreateRequest(BaseModel):
    task_type: str = "research_brief"
    goal: str
    thinking_enabled: bool | None = None
    reasoning_effort: str | None = None


class ClaimReviewRequest(BaseModel):
    claim_text: str | None = None
    claim_type: str | None = None
    topic: str | None = None
    companies: list[str] | str | None = None
    mechanism: str | None = None
    direction: str | None = None
    horizon: str | None = None
    metric: str | None = None
    value: str | None = None
    unit: str | None = None
    evidence_span: str | None = None
    confidence: str | None = None
    as_of_date: str | None = None
    exposure_level: str | None = None
    review_status: str | None = None
    reviewer_note: str | None = None
    quality_flags: str | None = None
    conflict_group_id: str | None = None


class FeedbackCreateRequest(BaseModel):
    conversation_id: str = ""
    turn_index: int = 0
    question: str
    answer_hash: str = ""
    helpful: bool | None = None
    evidence_supported: bool | None = None
    missing_answer: bool | None = None
    human_score: int | None = None
    note: str = ""
    citation_ids: list[str] = []
