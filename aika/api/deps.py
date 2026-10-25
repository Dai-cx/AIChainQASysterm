"""Environment driven settings and the cached engine / store / graph singletons.

Everything here used to live at the top of ``aika.api``.  The ``lru_cache`` singletons stay
module level so that the FastAPI dependency getters return the very same objects (and therefore
the same ``functools.lru_cache`` identity) that ``tests/test_api.py`` and the lifespan rely on.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from aika.agents.store import AgentTaskStore
from aika.aika_core.data_paths import has_graph, resolve_graph_dir
from aika.conversation_store import ConversationStore
from aika.eval.feedback import FeedbackStore
from aika.eval.store import EvalRunStore
from aika.frontend_data import LocalKnowledgeGraph
from aika.qa_engine import QAEngine, normalize_agent_max_steps

REASONING_EFFORTS = ["low", "medium", "high"]
EXAMPLE_QUESTIONS = [
    "液冷产业链有哪些上市公司，各自处于什么环节？",
    "中际旭创和新易盛在光模块业务上的差异是什么？",
    "继续说它们的主要风险",
    "英维克液冷业务进展和主要风险是什么？",
    "AI算力产业链当前最大的瓶颈是什么？",
]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() not in {"0", "false", "no", "off", "disabled"}


def default_thinking_enabled() -> bool:
    model_name = os.getenv("LLM_MODEL", "").casefold()
    thinking_default = "deepseek" in os.getenv("LLM_BASE_URL", "").casefold() and (
        "reasoner" in model_name or "v4-pro" in model_name
    )
    return env_bool("LLM_THINKING_ENABLED", thinking_default)


def default_reasoning_effort() -> str:
    effort = os.getenv("LLM_REASONING_EFFORT", "low").strip() or "low"
    return effort if effort in REASONING_EFFORTS else "low"


def default_agent_enabled() -> bool:
    return env_bool("QA_ENABLE_AGENT", True)


def default_agent_max_steps() -> int:
    return normalize_agent_max_steps(os.getenv("QA_AGENT_MAX_STEPS", "4"))


@lru_cache(maxsize=1)
def _cached_conversation_store() -> ConversationStore:
    return ConversationStore()


@lru_cache(maxsize=1)
def _cached_agent_task_store() -> AgentTaskStore:
    return AgentTaskStore(Path(os.getenv("AGENT_TASK_DIR", "data/agent_tasks")))


@lru_cache(maxsize=1)
def _cached_eval_run_store() -> EvalRunStore:
    return EvalRunStore(Path(os.getenv("EVAL_RUN_DIR", "data/eval_runs")))


@lru_cache(maxsize=1)
def _cached_feedback_store() -> FeedbackStore:
    return FeedbackStore(Path(os.getenv("FEEDBACK_DIR", "data/feedback")))


@lru_cache(maxsize=1)
def _cached_qa_engine() -> QAEngine:
    return QAEngine.from_env()


@lru_cache(maxsize=1)
def _cached_knowledge_graph() -> LocalKnowledgeGraph:
    data_dir = resolve_graph_dir(os.getenv("KG_DATA_DIR"))
    if not has_graph(data_dir):
        return LocalKnowledgeGraph.from_csvs()
    return LocalKnowledgeGraph.from_dir(data_dir)


async def get_conversation_store() -> ConversationStore:
    return _cached_conversation_store()


async def get_agent_task_store() -> AgentTaskStore:
    return _cached_agent_task_store()


async def get_eval_run_store() -> EvalRunStore:
    return _cached_eval_run_store()


async def get_feedback_store() -> FeedbackStore:
    return _cached_feedback_store()


async def get_qa_engine() -> QAEngine:
    return _cached_qa_engine()


async def get_knowledge_graph() -> LocalKnowledgeGraph:
    return _cached_knowledge_graph()
