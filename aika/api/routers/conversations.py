"""Conversation CRUD, the JSON/SSE message turn and the conversation export."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse

from aika.api.deps import get_conversation_store, get_qa_engine
from aika.api.errors import http_error_from_store
from aika.api.models import ConversationCreateRequest, ConversationTitleRequest, MessageCreateRequest
from aika.api.services import chat_turn
from aika.api.services.export import attachment_headers
from aika.conversation_store import ConversationStore
from aika.qa_engine import QAEngine

router = APIRouter()


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    store: ConversationStore = Depends(get_conversation_store),
) -> dict[str, Any]:
    return {"conversations": store.list(limit=limit)}


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreateRequest,
    store: ConversationStore = Depends(get_conversation_store),
) -> dict[str, Any]:
    return store.create(title=request.title)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    store: ConversationStore = Depends(get_conversation_store),
) -> dict[str, Any]:
    try:
        return store.get(conversation_id)
    except Exception as exc:
        raise http_error_from_store(exc) from exc


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: ConversationTitleRequest,
    store: ConversationStore = Depends(get_conversation_store),
) -> dict[str, Any]:
    try:
        return store.update_title(conversation_id, request.title)
    except Exception as exc:
        raise http_error_from_store(exc) from exc


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    store: ConversationStore = Depends(get_conversation_store),
) -> Response:
    try:
        store.delete(conversation_id)
    except Exception as exc:
        raise http_error_from_store(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/messages")
async def append_message(
    conversation_id: str,
    request: MessageCreateRequest,
    store: ConversationStore = Depends(get_conversation_store),
    engine: QAEngine = Depends(get_qa_engine),
) -> dict[str, Any]:
    return chat_turn.run_turn(store, conversation_id, request, engine)


@router.post("/conversations/{conversation_id}/messages/stream")
async def append_message_stream(
    conversation_id: str,
    request: MessageCreateRequest,
    store: ConversationStore = Depends(get_conversation_store),
    engine: QAEngine = Depends(get_qa_engine),
) -> StreamingResponse:
    prepared = chat_turn.prepare_turn(store, conversation_id, request)
    return StreamingResponse(
        chat_turn.stream_turn(store, conversation_id, prepared, engine),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    format: str = Query("md", pattern="^(md|json)$"),
    store: ConversationStore = Depends(get_conversation_store),
) -> Response:
    try:
        content, filename, media_type = store.export(conversation_id, format)
    except Exception as exc:
        raise http_error_from_store(exc) from exc
    ascii_fallback = "conversation.md" if format == "md" else "conversation.json"
    return Response(
        content=content,
        media_type=media_type,
        headers=attachment_headers(ascii_fallback, filename),
    )
