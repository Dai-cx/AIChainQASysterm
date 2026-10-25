"""Text helpers shared by every layer.

Truncation was reimplemented thirteen times with three subtly different policies, so the
same value could come out three different lengths depending on which module formatted it:

* most call sites cut to ``limit - 3`` and append ``"..."``   -> result is ``limit`` chars
* five call sites cut to ``limit - 1`` and append ``"..."``    -> result is ``limit + 2``
* the MCP tool layer cut to ``limit - 1``, stripped, appended ``"…"``

``shorten`` keeps all three reachable through explicit keywords, so converting a call
site is a rename rather than a behaviour change.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_WHITESPACE = re.compile(r"\s+")


def collapse(value: Any) -> str:
    """Collapse every whitespace run to a single space and trim the ends."""
    return _WHITESPACE.sub(" ", str(value or "")).strip()


def shorten(
    value: Any,
    limit: int,
    *,
    marker: str = "...",
    reserve: int | None = None,
    strip_tail: bool = False,
) -> str:
    """Collapse whitespace and cut to at most ``limit`` characters.

    ``reserve`` is how many characters of the budget the marker may consume. It defaults
    to ``len(marker)``, i.e. the result fits inside ``limit``. Pass ``reserve=1`` for the
    legacy policy whose result could overflow by ``len(marker) - 1``.
    """
    text = collapse(value)
    budget = limit - (len(marker) if reserve is None else reserve)
    if len(text) <= limit or budget <= 0:
        return text
    head = text[:budget]
    if strip_tail:
        head = head.rstrip()
    return head + marker


def normalize_text(value: Any) -> str:
    """Fold text for matching: drop every whitespace run, then casefold.

    Three retrievers had their own copy of this (claims, the SQLite backend and the RAG
    index, with the Postgres retrieval importing the RAG one), so the same query could in
    principle normalise differently depending on which path scored it.
    """
    return _WHITESPACE.sub("", str(value or "")).casefold()


def dedupe_strings(values: Iterable[Any]) -> list[str]:
    """Drop empty values and duplicates while preserving the original order."""
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
