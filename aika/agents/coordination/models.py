"""Value objects shared by the centralized coordinator."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from aika.aika_core.text import shorten
from aika.agent_tools import AgentToolCall
from aika.agents.coverage import CoverageReport
from aika.graphrag import GraphRagResult
from aika.professional_qa import EvidenceCard, card_identity

class LLMBudgetExhausted(RuntimeError):
    pass

@dataclass(frozen=True)
class AgentAssignment:
    assignment_id: str
    agent_type: str
    query: str
    filters: dict[str, Any] = field(default_factory=dict)
    coverage_goals: list[str] = field(default_factory=list)
    round_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class AgentResult:
    assignment: AgentAssignment
    status: str
    output: Any = None
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    elapsed_ms: float = 0.0
    error: str = ""
    degraded: bool = False
    timed_out: bool = False

    def diagnostic(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment.assignment_id,
            "agent_type": self.assignment.agent_type,
            "status": self.status,
            "result_count": result_count(self.output),
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "degraded": self.degraded,
            "timed_out": self.timed_out,
        }

@dataclass(frozen=True)
class EvidenceCandidate:
    candidate_id: str
    card: EvidenceCard
    retrieval_agent: str

    def prompt_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.card.kind,
            "title": self.card.title,
            "evidence": shorten(self.card.evidence, 500),
            "source": self.card.source,
            "page": self.card.page,
            "company": self.card.company,
            "topic": self.card.topic,
            "claim_type": self.card.claim_type,
            "relation": self.card.relation,
            "score": self.card.score,
            "retrieval_agent": self.retrieval_agent,
        }

@dataclass(frozen=True)
class ReviewReport:
    accepted_ids: list[str]
    rejected_ids: list[str]
    conflicts: list[dict[str, Any]]
    coverage: CoverageReport
    source: str
    degraded: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted_ids": list(self.accepted_ids),
            "rejected_ids": list(self.rejected_ids),
            "conflicts": list(self.conflicts),
            "coverage": self.coverage.to_dict(),
            "source": self.source,
            "degraded": self.degraded,
            "error": self.error,
        }

@dataclass(frozen=True)
class EvidenceCardDraft:
    candidate_ids: list[str]
    title: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

AGENT_TYPES = ("graph", "rag", "research", "semantic", "graphrag")

LLM_METHODS = {
    "chat_json",
    "chat_text",
    "chat_text_with_metadata",
    "chat_messages",
    "stream_chat_messages",
}

def candidate_id(card: EvidenceCard) -> str:
    identity = "\x1f".join(card_identity(card))
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10].upper()
    return f"C{digest}"

def clean_ids(value: Any, allowed: set[str]) -> list[str]:
    return [item for item in clean_strings(value) if item in allowed]

def clean_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = []
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in output:
            output.append(text)
    return output

def result_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, GraphRagResult):
        return len(result.global_hits) + len(result.local_hits) + len(result.paths)
    if isinstance(result, dict):
        if "records" in result:
            return len(result.get("records") or [])
        return len(result)
    if isinstance(result, (list, tuple, set)):
        return len(result)
    return 1
