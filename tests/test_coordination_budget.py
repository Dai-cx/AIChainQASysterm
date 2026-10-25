"""Central LLM budget: retrieval planning must not starve answer generation."""

from __future__ import annotations

import pytest

from aika.agents.coordination.budget import CentralLLMBudget
from aika.agents.coordination.models import LLMBudgetExhausted


class _Client:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat_text(self, **_kwargs) -> str:
        self.calls.append("text")
        return "ok"

    def chat_json(self, **_kwargs) -> dict:
        self.calls.append("json")
        return {}


def test_planning_cannot_consume_the_generation_reserve():
    budget = CentralLLMBudget(_Client(), max_calls=4, generation_reserve=2)
    planning = budget.client("planning")

    planning.chat_json(prompt="a")
    planning.chat_json(prompt="b")
    with pytest.raises(LLMBudgetExhausted, match="reserved for answer generation"):
        planning.chat_json(prompt="c")

    answer = budget.client("answer")
    assert answer.chat_text(prompt="q") == "ok"
    assert answer.chat_text(prompt="q") == "ok"
    assert budget.calls["total"] == 4


def test_generation_role_may_use_the_whole_budget():
    budget = CentralLLMBudget(_Client(), max_calls=2, generation_reserve=2)
    answer = budget.client("answer")

    assert answer.chat_text(prompt="q") == "ok"
    assert answer.chat_text(prompt="q") == "ok"
    with pytest.raises(LLMBudgetExhausted):
        answer.chat_text(prompt="q")


def test_reserve_is_clamped_to_the_budget():
    budget = CentralLLMBudget(_Client(), max_calls=2, generation_reserve=9)
    assert budget.generation_reserve == 2
