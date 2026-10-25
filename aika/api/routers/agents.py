"""Research agent task endpoints (``/agent/tasks``)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from aika.agents.research_agent import ResearchAgent
from aika.agents.store import AgentTaskStore
from aika.api.deps import (
    REASONING_EFFORTS,
    default_reasoning_effort,
    default_thinking_enabled,
    get_agent_task_store,
    get_qa_engine,
)
from aika.api.errors import http_error_from_agent_store
from aika.api.models import AgentTaskCreateRequest
from aika.api.services.export import agent_task_json, agent_task_markdown, attachment_headers
from aika.qa_engine import QAEngine

router = APIRouter()


@router.get("/agent/tasks")
async def list_agent_tasks(
    limit: int = Query(50, ge=1, le=200),
    store: AgentTaskStore = Depends(get_agent_task_store),
) -> dict[str, Any]:
    return {"tasks": store.list(limit=limit)}


@router.post("/agent/tasks", status_code=status.HTTP_201_CREATED)
async def create_agent_task(
    request: AgentTaskCreateRequest,
    store: AgentTaskStore = Depends(get_agent_task_store),
    engine: QAEngine = Depends(get_qa_engine),
) -> dict[str, Any]:
    goal = request.goal.strip()
    if not goal:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent task goal cannot be empty")
    if request.reasoning_effort and request.reasoning_effort not in REASONING_EFFORTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reasoning effort")

    thinking_enabled = default_thinking_enabled() if request.thinking_enabled is None else request.thinking_enabled
    reasoning_effort = request.reasoning_effort or (default_reasoning_effort() if thinking_enabled else "")
    try:
        task = ResearchAgent(engine, store).run(
            task_type=request.task_type,
            goal=goal,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort or None,
        )
    except Exception as exc:
        raise http_error_from_agent_store(exc) from exc
    return {"task": task}


@router.get("/agent/tasks/{task_id}")
async def get_agent_task(
    task_id: str,
    store: AgentTaskStore = Depends(get_agent_task_store),
) -> dict[str, Any]:
    try:
        return store.get(task_id)
    except Exception as exc:
        raise http_error_from_agent_store(exc) from exc


@router.get("/agent/tasks/{task_id}/export")
async def export_agent_task(
    task_id: str,
    format: str = Query("md", pattern="^(md|json)$"),
    store: AgentTaskStore = Depends(get_agent_task_store),
) -> Response:
    try:
        task = store.get(task_id)
    except Exception as exc:
        raise http_error_from_agent_store(exc) from exc
    fmt = format.casefold()
    safe_title = str(task.get("title") or task_id).strip() or task_id
    safe_title = "".join(char if char.isalnum() or char in "._-\u4e00-\u9fff" else "_" for char in safe_title).strip("_")
    safe_title = safe_title or task_id
    if fmt == "json":
        content = agent_task_json(task)
        filename = f"{safe_title}.json"
        media_type = "application/json; charset=utf-8"
    else:
        content = agent_task_markdown(task)
        filename = f"{safe_title}.md"
        media_type = "text/markdown; charset=utf-8"
    ascii_fallback = "agent_task.md" if fmt == "md" else "agent_task.json"
    return Response(
        content=content,
        media_type=media_type,
        headers=attachment_headers(ascii_fallback, filename),
    )
