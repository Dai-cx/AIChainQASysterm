"""The single implementation of "run one conversation turn".

Both conversation routes use this module: the JSON route calls :func:`run_turn`, the SSE route
calls :func:`prepare_turn` and then :func:`stream_turn`.  That seam is deliberate and behaviour
preserving: request validation and history loading have to happen *before* a streaming response
starts, so a blank question or an unknown conversation still answers with a plain JSON 4xx instead
of an SSE ``error`` event, and the engine's ``progress`` / ``answer_delta`` events must be forwarded
as they are produced instead of being buffered.  Everything else -- option resolution, diagnostics
annotation, turn assembly, persistence and the final payload -- is shared here, so the two routes
can no longer drift apart.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from aika.api.deps import REASONING_EFFORTS, default_reasoning_effort, default_thinking_enabled
from aika.api.errors import http_error_from_store
from aika.api.models import MessageCreateRequest
from aika.conversation_store import ConversationStore, now_iso
from aika.qa_engine import QAEngine


@dataclass(frozen=True)
class PreparedTurn:
    """Everything the engine needs, resolved and validated once per request."""

    question: str
    thinking_enabled: bool
    reasoning_effort: str
    history: list[dict[str, str]]


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def public_stream_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event)
    payload.pop("type", None)
    return payload


def resolve_request_options(request: MessageCreateRequest) -> tuple[bool, str]:
    thinking_enabled = default_thinking_enabled() if request.thinking_enabled is None else request.thinking_enabled
    reasoning_effort = request.reasoning_effort or (default_reasoning_effort() if thinking_enabled else "")
    return thinking_enabled, reasoning_effort


def prepare_turn(store: ConversationStore, conversation_id: str, request: MessageCreateRequest) -> PreparedTurn:
    """Validate the request and load conversation history (HTTP 4xx on failure)."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")
    if request.reasoning_effort and request.reasoning_effort not in REASONING_EFFORTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reasoning effort")
    try:
        history = store.history_messages(conversation_id)
    except Exception as exc:
        raise http_error_from_store(exc) from exc
    thinking_enabled, reasoning_effort = resolve_request_options(request)
    return PreparedTurn(
        question=question,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
        history=history,
    )


def complete_turn(
    store: ConversationStore,
    conversation_id: str,
    prepared: PreparedTurn,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Annotate the engine result, build the turn, persist it and return the public payload."""
    diagnostics = result.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
        result["diagnostics"] = diagnostics
    diagnostics["thinking_enabled"] = prepared.thinking_enabled
    diagnostics["reasoning_effort"] = prepared.reasoning_effort
    turn = {
        "created_at": now_iso(),
        "question": prepared.question,
        "answer": result["answer"],
        "thinking_enabled": prepared.thinking_enabled,
        "reasoning_effort": prepared.reasoning_effort,
        "result": result,
    }
    conversation = store.append_turn(conversation_id, turn)
    return {"conversation": conversation, "turn": turn}


def run_turn(
    store: ConversationStore,
    conversation_id: str,
    request: MessageCreateRequest,
    engine: QAEngine,
) -> dict[str, Any]:
    """Run one blocking turn and return ``{"conversation": ..., "turn": ...}``."""
    prepared = prepare_turn(store, conversation_id, request)
    result = engine.answer_question(
        prepared.question,
        conversation_history=prepared.history,
        thinking_enabled=prepared.thinking_enabled,
        reasoning_effort=prepared.reasoning_effort or None,
    )
    try:
        return complete_turn(store, conversation_id, prepared, result)
    except Exception as exc:
        raise http_error_from_store(exc) from exc


def stream_turn(
    store: ConversationStore,
    conversation_id: str,
    prepared: PreparedTurn,
    engine: QAEngine,
) -> Iterator[str]:
    """Yield the SSE frames for one turn, ending with ``final`` or ``error``."""
    result: dict[str, Any] | None = None
    try:
        if hasattr(engine, "answer_question_stream"):
            for event in engine.answer_question_stream(
                prepared.question,
                conversation_history=prepared.history,
                thinking_enabled=prepared.thinking_enabled,
                reasoning_effort=prepared.reasoning_effort or None,
            ):
                event_type = str(event.get("type") or "message")
                if event_type == "final":
                    result = dict(event.get("result") or {})
                    continue
                if event_type in {"progress", "answer_delta"}:
                    yield sse_event(event_type, public_stream_payload(event))
        else:
            result = engine.answer_question(
                prepared.question,
                conversation_history=prepared.history,
                thinking_enabled=prepared.thinking_enabled,
                reasoning_effort=prepared.reasoning_effort or None,
            )
            yield sse_event("answer_delta", {"content": result.get("answer", "")})

        if result is None:
            raise RuntimeError("No answer result was generated")
        yield sse_event("final", complete_turn(store, conversation_id, prepared, result))
    except Exception as exc:
        yield sse_event("error", {"message": str(exc) or "生成失败"})
