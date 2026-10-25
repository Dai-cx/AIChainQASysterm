"""Shared plumbing for the MCP tools: backend resolution and JSON envelopes."""

from __future__ import annotations

from aika.aika_core.text import shorten
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from aika.aika_core.backends.csv_backend import CSVResearchBackend
from aika.aika_core.backends.sqlite_backend import DEFAULT_PROFILE, SQLiteResearchBackend, profile_index_path, resolve_aika_home
from aika.aika_core.models import ClaimRecord, ResearchBackend
from aika.aika_mcp.schemas import AikaMcpRequest, FilteredSearchRequest


RequestT = TypeVar("RequestT", bound=AikaMcpRequest)


LLM_COUNTER_MODE_ENV = "AIKA_EVIDENCE_UX_LLM_MODE"


DEPTH_LIMITS = {
    "light": {"claims": 4, "evidence": 6, "graph": 20},
    "standard": {"claims": 8, "evidence": 12, "graph": 40},
    "deep": {"claims": 12, "evidence": 18, "graph": 80},
}


@dataclass(frozen=True)
class BackendContext:
    backend: ResearchBackend
    meta: dict[str, Any]
    warnings: list[str]


class AikaCounterAuditError(RuntimeError):
    """Raised when LLM counter-evidence audit is explicitly required."""


def resolve_backend(request: AikaMcpRequest) -> BackendContext:
    warnings: list[str] = []
    mode = request.backend or "auto"
    profile = request.profile or DEFAULT_PROFILE
    if mode in {"auto", "sqlite"}:
        home = resolve_aika_home(request.home)
        index_path = profile_index_path(home, profile=profile)
        if index_path.exists() or mode == "sqlite":
            if not index_path.exists():
                warnings.append(f"SQLite index not found: {index_path}")
            return BackendContext(
                backend=SQLiteResearchBackend(index_path),
                meta={
                    "backend": "sqlite",
                    "backend_mode": mode,
                    "home": str(home),
                    "profile": profile,
                    "index_path": str(index_path),
                    "index_exists": index_path.exists(),
                },
                warnings=warnings,
            )
        warnings.append(f"SQLite index not found, falling back to bundled CSV backend: {index_path}")

    backend = CSVResearchBackend.from_env()
    return BackendContext(
        backend=backend,
        meta={
            "backend": "csv",
            "backend_mode": mode,
            "data_dir": str(backend.config.data_dir),
            "graph_dir": str(backend.config.graph_dir),
            "research_dir": str(backend.config.research_dir),
            "profile": profile,
        },
        warnings=warnings,
    )


def _require_backend_method(backend: ResearchBackend, name: str) -> Callable[..., Any]:
    method = getattr(backend, name, None)
    if method is None or not callable(method):
        raise NotImplementedError(f"Backend does not expose {name}.")
    return method


def _success_envelope(tool: str, context: BackendContext, **fields: Any) -> dict[str, Any]:
    return {"status": "completed", "tool": tool, "meta": _meta(context), **_jsonable(fields)}


def _error_envelope(
    tool: str,
    *,
    meta: dict[str, Any],
    error_type: str,
    message: str,
    details: Any,
) -> dict[str, Any]:
    return {
        "status": "error",
        "tool": tool,
        "meta": _jsonable(meta),
        "error": {"type": error_type, "message": message, "details": _jsonable(details)},
    }


def _meta(context: BackendContext) -> dict[str, Any]:
    return {**context.meta, "warnings": list(context.warnings)}


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return dict(value.to_dict())
    return {}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value)]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    return str(value)


def _short_text(value: str, limit: int = 160) -> str:
    """Collapse whitespace and cut for display, using an ellipsis character."""
    return shorten(value, limit, marker="…", reserve=1, strip_tail=True)


def _subject(topic: str, companies: list[str]) -> str:
    if companies:
        return f"{topic} {' '.join(companies)}".strip()
    return topic


def _filters(request: FilteredSearchRequest) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if request.companies:
        filters["company"] = request.companies
    if request.topics:
        filters["topic"] = request.topics
    if request.claim_types:
        filters["claim_type"] = request.claim_types
    return filters


def _normalize_gaps(gaps: Any) -> list[dict[str, Any]]:
    return [_to_dict(gap) for gap in list(gaps or [])]


def _llm_counter_audit(
    context: BackendContext,
    *,
    subject: str,
    evidence_cards: list[dict[str, Any]],
    claims: list[ClaimRecord],
) -> dict[str, Any]:
    mode = os.getenv(LLM_COUNTER_MODE_ENV, "auto").strip().casefold() or "auto"
    if mode not in {"auto", "off", "required"}:
        context.warnings.append(f"{LLM_COUNTER_MODE_ENV}={mode!r} is invalid; using auto.")
        mode = "auto"
    if mode == "off" or not evidence_cards:
        return {"status": "disabled" if mode == "off" else "not_run", "source": "rules"}
    try:
        from aika.llm_client import OpenAICompatibleClient

        client = OpenAICompatibleClient()
        payload = {
            "subject": subject,
            "evidence_cards": [
                {
                    "evidence_id": card.get("evidence_id") or card.get("citation_id") or card.get("claim_id"),
                    "citation_id": card.get("citation_id"),
                    "claim_type": card.get("claim_type"),
                    "evidence": _short_text(str(card.get("evidence") or card.get("evidence_span") or ""), 260),
                    "source_title": card.get("source_title") or card.get("source"),
                    "published_at": card.get("published_at") or card.get("as_of_date"),
                }
                for card in evidence_cards[:12]
            ],
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "claim_type": claim.claim_type,
                    "claim_text": _short_text(claim.claim_text, 260),
                }
                for claim in claims[:12]
            ],
        }
        response = client.chat_json(
            system_prompt=(
                "You audit evidence for counter-evidence. Return JSON only with keys: "
                "status, summary, counter_evidence_ids. Use only provided evidence_id values. "
                "If no counter-evidence is visible, return an empty counter_evidence_ids list and say the sample did not reveal counter-evidence."
            ),
            user_prompt=json.dumps(payload, ensure_ascii=False),
            temperature=0.0,
            thinking_enabled=False,
        )
        response = dict(response)
        response.setdefault("status", "completed")
        response["source"] = "llm"
        return response
    except Exception as exc:
        if mode == "required":
            raise AikaCounterAuditError(f"LLM counter-evidence audit failed: {exc}") from exc
        context.warnings.append(f"LLM counter-evidence audit unavailable; used rule fallback: {exc}")
        return {"status": "fallback", "source": "rules", "error": str(exc)}
