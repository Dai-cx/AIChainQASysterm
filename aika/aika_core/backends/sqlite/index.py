"""Building, inspecting and loading the SQLite research index."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aika.aika_core.backends.sqlite.query import (
    _claim_filter_sql,
    _evidence_filter_sql,
    _like_search_sql,
    _score_rows,
    _topic_filter_sql,
)
from aika.aika_core.backends.sqlite.rows import _dossier_content
from aika.aika_core.backends.sqlite.schema import (
    CLAIM_COLUMNS,
    DOSSIER_COLUMNS,
    EVIDENCE_COLUMNS,
    RELATION_COLUMNS,
    SCHEMA_VERSION,
    _connect,
    _create_schema,
    _select_tokenizer,
    _write_metadata,
)
from aika.aika_core.backends.sqlite.util import _serialize_cell, _text
from aika.aika_core.data_paths import CLAIMS_FILE, EVIDENCE_SPANS_FILE, RELATIONS_FILE, SEGMENT_DOSSIERS_FILE
from aika.aika_core.models import ClaimRecord


def sqlite_fts_status() -> dict[str, Any]:
    """Return SQLite FTS5/trigram support details for doctor output."""
    status: dict[str, Any] = {
        "sqlite_version": sqlite3.sqlite_version,
        "fts5": False,
        "trigram": False,
        "tokenizer": "",
        "error": "",
    }
    try:
        with sqlite3.connect(":memory:") as connection:
            connection.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(x)")
            status["fts5"] = True
            try:
                connection.execute("CREATE VIRTUAL TABLE trigram_probe USING fts5(x, tokenize='trigram')")
                status["trigram"] = True
                status["tokenizer"] = "trigram"
            except sqlite3.OperationalError:
                status["tokenizer"] = "unicode61"
    except sqlite3.OperationalError as exc:
        status["error"] = str(exc)
    return status


def build_sqlite_index(knowledge_dir: str | Path, index_path: str | Path) -> dict[str, Any]:
    """Build a deterministic SQLite FTS5 index from local CSV/JSONL artifacts."""
    source_dir = Path(knowledge_dir).expanduser().resolve()
    target_path = Path(index_path).expanduser().resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_name(f".{target_path.name}.{os.getpid()}.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    counts = {"claims": 0, "evidence_spans": 0, "dossiers": 0, "relations": 0}
    try:
        # `with sqlite3.connect(...)` only wraps the *transaction*; it does not close the
        # file handle. On Windows an open handle makes both `os.replace` and `unlink` fail
        # with WinError 32, so the connection must be closed explicitly before the swap.
        connection = sqlite3.connect(tmp_path)
        try:
            connection.row_factory = sqlite3.Row
            tokenizer = _select_tokenizer(connection)
            _create_schema(connection, tokenizer=tokenizer)
            claim_lookup = _load_claims(connection, source_dir / CLAIMS_FILE)
            counts["claims"] = len(claim_lookup)
            counts["evidence_spans"] = _load_evidence_spans(
                connection,
                source_dir / EVIDENCE_SPANS_FILE,
                claim_lookup,
            )
            counts["dossiers"] = _load_dossiers(connection, source_dir / SEGMENT_DOSSIERS_FILE)
            counts["relations"] = _load_relations(connection, source_dir / RELATIONS_FILE)
            _write_metadata(
                connection,
                {
                    "schema_version": SCHEMA_VERSION,
                    "built_at": datetime.now(timezone.utc).isoformat(),
                    "source_dir": str(source_dir),
                    "tokenizer": tokenizer,
                    **{f"{key}_count": str(value) for key, value in counts.items()},
                },
            )
            connection.commit()
        finally:
            connection.close()
        tmp_path.replace(target_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return {"index_path": str(target_path), "knowledge_dir": str(source_dir), "counts": counts}


def inspect_sqlite_index(index_path: str | Path) -> dict[str, Any]:
    path = Path(index_path).expanduser().resolve()
    result: dict[str, Any] = {
        "exists": path.exists(),
        "path": str(path),
        "metadata": {},
        "counts": {},
        "error": "",
    }
    if not path.exists():
        return result
    try:
        with _connect(path) as connection:
            result["metadata"] = {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM metadata").fetchall()
            }
            for table in ("claims", "evidence_spans", "dossiers", "relations"):
                row = connection.execute(f"SELECT count(*) AS count FROM {table}").fetchone()
                result["counts"][table] = int(row["count"] or 0)
    except sqlite3.Error as exc:
        result["error"] = str(exc)
    return result


def _load_claims(connection: sqlite3.Connection, path: Path) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for index, row in enumerate(_read_csv_rows(path), start=1):
        normalized = {column: _text(row.get(column)) for column in CLAIM_COLUMNS}
        if not normalized["claim_id"]:
            normalized["claim_id"] = f"claim_row_{index}"
        record = ClaimRecord.from_row(normalized)
        normalized["companies"] = _serialize_cell(row.get("companies") or normalized["companies"])
        cursor = connection.execute(
            _insert_sql("claims", CLAIM_COLUMNS),
            [normalized[column] for column in CLAIM_COLUMNS],
        )
        rowid = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO claims_fts(rowid, claim_text, evidence_span, topic, companies) VALUES (?, ?, ?, ?, ?)",
            (
                rowid,
                normalized["claim_text"],
                normalized["evidence_span"],
                normalized["topic"],
                normalized["companies"],
            ),
        )
        lookup[normalized["claim_id"]] = {
            "company": record.companies[0] if record.companies else "",
            "topic": normalized["topic"],
            "claim_type": normalized["claim_type"],
            "confidence": normalized["confidence"],
            "exposure_level": normalized["exposure_level"],
        }
    return lookup


def _load_evidence_spans(connection: sqlite3.Connection, path: Path, claim_lookup: dict[str, dict[str, str]]) -> int:
    count = 0
    for index, row in enumerate(_read_csv_rows(path), start=1):
        claim_id = _text(row.get("claim_id"))
        claim = claim_lookup.get(claim_id, {})
        normalized = {
            "evidence_id": _text(row.get("evidence_id")) or f"evidence_row_{index}",
            "claim_id": claim_id,
            "evidence": _text(row.get("evidence") or row.get("text")),
            "source_report_id": _text(row.get("source_report_id")),
            "source_title": _text(row.get("source_title") or row.get("source")),
            "page": _text(row.get("page")),
            "section": _text(row.get("section")),
            "source_tier": _text(row.get("source_tier")),
            "as_of_date": _text(row.get("as_of_date")),
            "quality": _text(row.get("quality")),
            "company": _text(row.get("company") or claim.get("company")),
            "topic": _text(row.get("topic") or claim.get("topic")),
            "claim_type": _text(row.get("claim_type") or claim.get("claim_type")),
            "confidence": _text(row.get("confidence") or claim.get("confidence")),
            "exposure_level": _text(row.get("exposure_level") or claim.get("exposure_level")),
        }
        cursor = connection.execute(
            _insert_sql("evidence_spans", EVIDENCE_COLUMNS),
            [normalized[column] for column in EVIDENCE_COLUMNS],
        )
        rowid = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO evidence_fts(rowid, evidence, source_title, company, topic) VALUES (?, ?, ?, ?, ?)",
            (
                rowid,
                normalized["evidence"],
                normalized["source_title"],
                normalized["company"],
                normalized["topic"],
            ),
        )
        count += 1
    return count


def _load_dossiers(connection: sqlite3.Connection, path: Path) -> int:
    count = 0
    for index, dossier in enumerate(_read_jsonl_rows(path), start=1):
        topic = _text(dossier.get("topic"))
        title = _text(dossier.get("title")) or f"{topic} segment dossier".strip()
        content = _dossier_content(dossier)
        normalized = {
            "dossier_id": _text(dossier.get("dossier_id")) or f"dossier_{topic or index}",
            "topic": topic,
            "title": title,
            "content": content,
            "raw_json": json.dumps(dossier, ensure_ascii=False, sort_keys=True),
        }
        cursor = connection.execute(
            _insert_sql("dossiers", DOSSIER_COLUMNS),
            [normalized[column] for column in DOSSIER_COLUMNS],
        )
        rowid = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO dossiers_fts(rowid, title, content, topic) VALUES (?, ?, ?, ?)",
            (rowid, title, content, topic),
        )
        count += 1
    return count


def _load_relations(connection: sqlite3.Connection, path: Path) -> int:
    count = 0
    for index, row in enumerate(_read_csv_rows(path), start=1):
        normalized = {column: _text(row.get(column)) for column in RELATION_COLUMNS}
        if not normalized["relation_id"]:
            normalized["relation_id"] = f"relation_row_{index}"
        connection.execute(
            _insert_sql("relations", RELATION_COLUMNS),
            [normalized[column] for column in RELATION_COLUMNS],
        )
        count += 1
    return count


def _insert_sql(table: str, columns: list[str]) -> str:
    names = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO {table}({names}) VALUES ({placeholders})"


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        return [dict(row) for row in csv.DictReader(file)]


def _read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _fallback_claim_rows(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int,
    filters: dict[str, Any],
) -> list[sqlite3.Row]:
    filter_sql, filter_params = _claim_filter_sql(filters, alias="c")
    search_sql, search_params = _like_search_sql(
        query,
        alias="c",
        columns=("claim_text", "evidence_span", "topic", "companies", "source_title"),
    )
    rows = connection.execute(
        f"""
        SELECT c.*, 0.0 AS score
        FROM claims c
        WHERE 1=1
        {filter_sql}
        {search_sql}
        ORDER BY c.topic, c.claim_type, c.claim_id
        LIMIT ?
        """,
        [*filter_params, *search_params, limit],
    ).fetchall()
    return _score_rows(rows, query, fields=("claim_text", "evidence_span", "topic", "companies"))


def _fallback_evidence_rows(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int,
    filters: dict[str, Any],
) -> list[sqlite3.Row]:
    filter_sql, filter_params = _evidence_filter_sql(filters, alias="e")
    search_sql, search_params = _like_search_sql(
        query,
        alias="e",
        columns=("evidence", "source_title", "company", "topic"),
    )
    rows = connection.execute(
        f"""
        SELECT e.*, 0.0 AS score
        FROM evidence_spans e
        WHERE 1=1
        {filter_sql}
        {search_sql}
        ORDER BY e.topic, e.company, e.evidence_id
        LIMIT ?
        """,
        [*filter_params, *search_params, max(limit * 5, limit)],
    ).fetchall()
    return _score_rows(rows, query, fields=("evidence", "source_title", "company", "topic"))[:limit]


def _fallback_dossier_rows(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int,
    filters: dict[str, Any],
) -> list[sqlite3.Row]:
    filter_sql, filter_params = _topic_filter_sql(filters, alias="d")
    search_sql, search_params = _like_search_sql(query, alias="d", columns=("title", "content", "topic"))
    rows = connection.execute(
        f"""
        SELECT d.*, 0.0 AS score
        FROM dossiers d
        WHERE 1=1
        {filter_sql}
        {search_sql}
        ORDER BY d.topic
        LIMIT ?
        """,
        [*filter_params, *search_params, max(limit * 5, limit)],
    ).fetchall()
    return _score_rows(rows, query, fields=("title", "content", "topic"))[:limit]
