"""Small value helpers shared by the SQLite backend modules."""

from __future__ import annotations

from aika.aika_core.text import normalize_text as _normalize
import json
import re
from typing import Any, Iterable


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，;；|]", value) if item.strip()]
    if isinstance(value, Iterable):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = _normalize(text)
        if key and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _serialize_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return _text(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _floatish(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _limit(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
