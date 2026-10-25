"""Small value objects shared by the QA helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HydeQuery:
    """HYDE 生成结果和最终用于文本检索的 query。"""

    enabled: bool
    source: str
    query_mode: str
    hypothetical_answer: str = ""
    retrieval_query: str = ""
    error: str = ""
