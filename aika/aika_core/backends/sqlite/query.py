"""SQL predicate builders, query expansion and row scoring."""

from __future__ import annotations

from aika.aika_core.text import normalize_text as _normalize
import re
import sqlite3
from typing import Any, Iterable

from aika.aika_core.backends.sqlite.util import _dedupe, _text, _values


def _claim_filter_sql(filters: dict[str, Any], *, alias: str) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    companies = _values(filters.get("company") or filters.get("companies"))
    if companies:
        parts = []
        for company in companies:
            parts.append(f"({alias}.companies LIKE ? OR {alias}.claim_text LIKE ? OR {alias}.evidence_span LIKE ?)")
            params.extend([f"%{company}%", f"%{company}%", f"%{company}%"])
        clauses.append(f"({' OR '.join(parts)})")
    topics = _values(filters.get("topic") or filters.get("topics"))
    if topics:
        parts = [f"{alias}.topic LIKE ?" for _ in topics]
        clauses.append(f"({' OR '.join(parts)})")
        params.extend(f"%{topic}%" for topic in topics)
    claim_types = _values(filters.get("claim_type") or filters.get("claim_types"))
    if claim_types:
        placeholders = ", ".join("?" for _ in claim_types)
        clauses.append(f"{alias}.claim_type IN ({placeholders})")
        params.extend(claim_types)
    return _where_suffix(clauses), params


def _evidence_filter_sql(filters: dict[str, Any], *, alias: str) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    companies = _values(filters.get("company") or filters.get("companies"))
    if companies:
        parts = []
        for company in companies:
            parts.append(f"({alias}.company LIKE ? OR {alias}.evidence LIKE ?)")
            params.extend([f"%{company}%", f"%{company}%"])
        clauses.append(f"({' OR '.join(parts)})")
    topics = _values(filters.get("topic") or filters.get("topics"))
    if topics:
        parts = [f"{alias}.topic LIKE ?" for _ in topics]
        clauses.append(f"({' OR '.join(parts)})")
        params.extend(f"%{topic}%" for topic in topics)
    claim_types = _values(filters.get("claim_type") or filters.get("claim_types"))
    if claim_types:
        placeholders = ", ".join("?" for _ in claim_types)
        clauses.append(f"{alias}.claim_type IN ({placeholders})")
        params.extend(claim_types)
    return _where_suffix(clauses), params


def _topic_filter_sql(filters: dict[str, Any], *, alias: str) -> tuple[str, list[Any]]:
    topics = _values(filters.get("topic") or filters.get("topics"))
    if not topics:
        return "", []
    parts = [f"{alias}.topic LIKE ?" for _ in topics]
    return f"AND ({' OR '.join(parts)})", [f"%{topic}%" for topic in topics]


def _where_suffix(clauses: list[str]) -> str:
    return f"AND {' AND '.join(clauses)}" if clauses else ""


def _like_search_sql(query: str, *, alias: str, columns: Iterable[str]) -> tuple[str, list[Any]]:
    terms = _query_terms(query)
    if not terms:
        return "", []
    clauses: list[str] = []
    params: list[Any] = []
    for term in terms:
        parts = [f"{alias}.{column} LIKE ?" for column in columns]
        clauses.append(f"({' OR '.join(parts)})")
        params.extend(f"%{term}%" for _ in columns)
    return f"AND ({' OR '.join(clauses)})", params


def _fts_query(query: str) -> str:
    terms = _query_terms(query)
    if not terms:
        return ""
    return " OR ".join(f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms)


def _query_terms(query: str) -> list[str]:
    text = _text(query)
    if not text:
        return []
    terms: list[str] = []
    for term in re.split(r"[\s,，;；]+", text):
        if not term.strip():
            continue
        terms.extend(_expand_query_term(term.strip()))
    return _dedupe(terms)


def _expand_query_term(term: str) -> list[str]:
    terms = [term]
    for suffix in ("产业链", "行业", "领域", "公司", "业务"):
        if term.endswith(suffix) and len(term) > len(suffix):
            stem = term[: -len(suffix)].strip()
            if stem:
                terms.append(stem)
            terms.append(suffix)
    return terms


def _score_rows(rows: list[sqlite3.Row], query: str, *, fields: tuple[str, ...]) -> list[sqlite3.Row]:
    if not query.strip():
        return rows
    scored = [(float(_text_score(" ".join(_text(row[field]) for field in fields), query)), row) for row in rows]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: -item[0])
    return [_row_with_score(row, score) for score, row in scored]


def _dedupe_rows(rows: Iterable[sqlite3.Row]) -> list[sqlite3.Row]:
    output: list[sqlite3.Row] = []
    seen: set[Any] = set()
    for row in rows:
        key = row["id"] if "id" in row.keys() else tuple(sorted(dict(row).items()))
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _row_with_score(row: sqlite3.Row, score: float) -> sqlite3.Row:
    data = dict(row)
    data["score"] = round(score, 4)
    return _MappingRow(data)


class _MappingRow(dict):
    def keys(self) -> Any:
        return super().keys()


def _text_score(text: str, query: str) -> float:
    normalized = _normalize(text)
    score = 0.0
    full = _normalize(query)
    if full and full in normalized:
        score += 12.0
    for term in _query_terms(query):
        value = _normalize(term)
        if value and value in normalized:
            if value in {"产业链", "行业", "领域", "公司", "业务"}:
                score += 1.0
            else:
                score += 5.0 if len(value) >= 2 else 1.0
    return score
