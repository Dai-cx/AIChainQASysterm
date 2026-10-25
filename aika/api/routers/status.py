"""Status, example questions, eval runs and feedback endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from aika.api.deps import (
    EXAMPLE_QUESTIONS,
    REASONING_EFFORTS,
    default_agent_enabled,
    default_agent_max_steps,
    default_reasoning_effort,
    default_thinking_enabled,
    get_eval_run_store,
    get_feedback_store,
    get_knowledge_graph,
    get_qa_engine,
)
from aika.api.errors import http_error_from_eval_store, http_error_from_feedback_store
from aika.api.models import FeedbackCreateRequest
from aika.eval.feedback import FeedbackStore
from aika.eval.store import EvalRunStore
from aika.frontend_data import RELATION_LABELS, LocalKnowledgeGraph
from aika.qa_engine import QAEngine

router = APIRouter()


@router.get("/status")
async def api_status(
    engine: QAEngine = Depends(get_qa_engine),
    graph: LocalKnowledgeGraph = Depends(get_knowledge_graph),
) -> dict[str, Any]:
    entity_counts = graph.entity_counts()
    relation_counts = graph.relation_counts()
    research_stats: dict[str, Any] = {}
    research_memory = getattr(engine, "research_memory", None)
    if research_memory is not None and hasattr(research_memory, "claim_stats"):
        research_stats = research_memory.claim_stats()
    return {
        "graph_backend": engine.status.graph_backend,
        "neo4j_enabled": engine.status.neo4j_enabled,
        "rag_enabled": engine.status.rag_enabled,
        "research_enabled": getattr(engine.status, "research_enabled", False),
        "embedding_enabled": getattr(engine.status, "embedding_enabled", False),
        "llm_enabled": engine.status.llm_enabled,
        "csv_graph_enabled": engine.status.csv_graph_enabled,
        "graph_data_dir": engine.status.graph_data_dir,
        "errors": {
            "graph": engine.status.graph_error,
            "rag": engine.status.rag_error,
            "research": getattr(engine.status, "research_error", ""),
            "embedding": getattr(engine.status, "embedding_error", ""),
            "llm": engine.status.llm_error,
        },
        "stats": {
            "companies": entity_counts.get("Company", 0),
            "reports": graph.reports_count(),
            "entities": len(graph.entities),
            "relations": len(graph.relations),
            "entity_counts": dict(entity_counts),
            "relation_counts": {RELATION_LABELS.get(key, key): value for key, value in relation_counts.items()},
            "research": research_stats,
        },
        "settings": {
            "thinking_enabled": default_thinking_enabled(),
            "reasoning_effort": default_reasoning_effort(),
            "reasoning_efforts": REASONING_EFFORTS,
            "agent_enabled": getattr(engine, "enable_agent", default_agent_enabled()),
            "agent_max_steps": getattr(engine, "agent_max_steps", default_agent_max_steps()),
            "agent_runner": "langgraph" if getattr(engine, "enable_agent", default_agent_enabled()) else "workflow",
            "multi_agent_max_workers": getattr(engine, "multi_agent_max_workers", 5),
            "multi_agent_max_llm_calls": getattr(engine, "multi_agent_max_llm_calls", 12),
            "multi_agent_task_timeout_seconds": getattr(engine, "multi_agent_task_timeout_seconds", 90.0),
            "hyde_enabled": getattr(engine, "enable_hyde", True),
            "hyde_query_mode": getattr(engine, "hyde_query_mode", "hybrid"),
            "hyde_max_chars": getattr(engine, "hyde_max_chars", 700),
        },
    }


@router.get("/examples")
async def api_examples() -> dict[str, list[str]]:
    return {"examples": EXAMPLE_QUESTIONS}


@router.get("/eval/runs")
async def list_eval_runs(
    limit: int = Query(20, ge=1, le=200),
    store: EvalRunStore = Depends(get_eval_run_store),
) -> dict[str, Any]:
    return {"runs": store.list(limit=limit)}


@router.get("/eval/runs/{run_id}")
async def get_eval_run(
    run_id: str,
    store: EvalRunStore = Depends(get_eval_run_store),
) -> dict[str, Any]:
    try:
        return store.get(run_id)
    except Exception as exc:
        raise http_error_from_eval_store(exc) from exc


@router.get("/feedback")
async def list_feedback(
    limit: int = Query(100, ge=1, le=500),
    store: FeedbackStore = Depends(get_feedback_store),
) -> dict[str, Any]:
    return {"feedback": store.list(limit=limit)}


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    request: FeedbackCreateRequest,
    store: FeedbackStore = Depends(get_feedback_store),
) -> dict[str, Any]:
    try:
        feedback = store.save(request.model_dump())
    except Exception as exc:
        raise http_error_from_feedback_store(exc) from exc
    return {"feedback": feedback}
