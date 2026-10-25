"""FastAPI application package for AIKA.

Kept import-compatible with the former ``aika/api.py`` module so that
``uvicorn aika.api:app`` and ``from aika.api import app`` keep working, and so
that tests can keep overriding the same dependency callables they always used.
"""

from __future__ import annotations

from aika.api.app import app, create_app
from aika.api.deps import (
    get_agent_task_store,
    get_conversation_store,
    get_eval_run_store,
    get_feedback_store,
    get_knowledge_graph,
    get_qa_engine,
)

__all__ = [
    "app",
    "create_app",
    "get_agent_task_store",
    "get_conversation_store",
    "get_eval_run_store",
    "get_feedback_store",
    "get_knowledge_graph",
    "get_qa_engine",
]
