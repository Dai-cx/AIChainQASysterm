"""Thread-safe LLM budget accounting for centralized agents."""

from __future__ import annotations

import threading
from typing import Any

from .models import LLM_METHODS, LLMBudgetExhausted

# Roles that produce the user-visible answer. They may dip into the reserve so that
# retrieval planning can never starve answer generation.
GENERATION_ROLES = frozenset({"answer", "summarizer", "summarize"})


class CentralLLMBudget:
    """Thread-safe call budget shared by all centralized agents."""

    def __init__(self, client: Any | None, *, max_calls: int, generation_reserve: int = 2) -> None:
        self._client = client
        self.max_calls = max(0, int(max_calls or 0))
        self.generation_reserve = max(0, min(int(generation_reserve or 0), self.max_calls))
        self._lock = threading.Lock()
        self._used = 0
        self._method_calls: dict[str, int] = {}
        self._role_calls: dict[str, int] = {}
        self._fallbacks: dict[str, int] = {}
        self._errors: list[str] = []

    def client(self, role: str) -> "RoleLLMClient | None":
        if self._client is None:
            return None
        return RoleLLMClient(self, role)

    def reserve(self, role: str, method: str) -> Any:
        with self._lock:
            if self._client is None:
                raise LLMBudgetExhausted("LLM is not configured")
            limit = self.max_calls
            if role not in GENERATION_ROLES:
                limit = max(0, self.max_calls - self.generation_reserve)
            if self._used >= limit:
                reason = "LLM call budget exhausted" if limit == self.max_calls else (
                    "LLM call budget exhausted (reserved for answer generation)"
                )
                raise LLMBudgetExhausted(f"{reason} ({self.max_calls})")
            self._used += 1
            self._method_calls[method] = self._method_calls.get(method, 0) + 1
            self._role_calls[role] = self._role_calls.get(role, 0) + 1
            return getattr(self._client, method)

    def note_fallback(self, role: str, error: str = "") -> None:
        with self._lock:
            self._fallbacks[role] = self._fallbacks.get(role, 0) + 1
            if error:
                self._errors.append(f"{role}: {error}")

    @property
    def calls(self) -> dict[str, int]:
        with self._lock:
            return {"total": self._used, **dict(self._method_calls)}

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "max_calls": self.max_calls,
                "used_calls": self._used,
                "remaining_calls": max(0, self.max_calls - self._used),
                "calls_by_role": dict(self._role_calls),
                "fallbacks_by_role": dict(self._fallbacks),
                "fallback_count": sum(self._fallbacks.values()),
                "errors": list(self._errors),
            }

class RoleLLMClient:
    def __init__(self, budget: CentralLLMBudget, role: str) -> None:
        self._budget = budget
        self._role = role

    @property
    def calls(self) -> dict[str, int]:
        return self._budget.calls

    def __getattr__(self, name: str) -> Any:
        underlying = self._budget._client
        if underlying is None:
            raise AttributeError(name)
        attr = getattr(underlying, name)
        if name not in LLM_METHODS or not callable(attr):
            return attr

        def budgeted(*args: Any, **kwargs: Any) -> Any:
            method = self._budget.reserve(self._role, name)
            return method(*args, **kwargs)

        return budgeted
