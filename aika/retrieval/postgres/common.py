"""Shared configuration, migrations and text helpers for the PostgreSQL layer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable
import psycopg
from pgvector.psycopg import register_vector
from aika.research_claims import claim_title, first_company, parse_companies


class PostgresRetrievalError(RuntimeError):
    """Raised when the PostgreSQL retrieval backend is unavailable or invalid."""

ROOT_DIR = Path(__file__).resolve().parents[3]

MIGRATIONS_DIR = ROOT_DIR / "db" / "migrations"

SCHEMA_VERSION = "001_postgres_retrieval"

EMBEDDING_DIMENSIONS = 2048


def require_database_url(value: str | None = None) -> str:
    database_url = str(value or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise PostgresRetrievalError("DATABASE_URL is required for PostgreSQL retrieval")
    return database_url


def migrate_database(database_url: str | None = None, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply versioned SQL migrations once, in filename order."""

    conninfo = require_database_url(database_url)
    migration_paths = sorted(migrations_dir.glob("*.sql"))
    if not migration_paths:
        raise PostgresRetrievalError(f"No SQL migrations found in {migrations_dir}")
    applied: list[str] = []
    with psycopg.connect(conninfo, autocommit=False) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS retrieval_schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        known = {
            str(row[0])
            for row in connection.execute("SELECT version FROM retrieval_schema_migrations").fetchall()
        }
        for path in migration_paths:
            version = path.stem
            if version in known:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO retrieval_schema_migrations(version) VALUES (%s)",
                (version,),
            )
            applied.append(version)
        connection.commit()
    return applied


def _configure_connection(connection: psycopg.Connection[Any]) -> None:
    register_vector(connection)


def stable_content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def corpus_hash(values: Iterable[str]) -> str:
    payload = "\n".join(sorted(str(value) for value in values if str(value)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def rag_search_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(key) or "")
        for key in ("company", "source_title", "source_type", "section", "text")
        if row.get(key)
    )


def rag_semantic_text(row: dict[str, Any]) -> str:
    return "\n".join(
        str(row.get(key) or "")
        for key in ("source_title", "company", "section", "source_type", "text")
        if row.get(key)
    )


def claim_semantic_text(row: dict[str, Any]) -> str:
    companies = parse_companies(row.get("companies", []))
    parts = [
        claim_title(row),
        str(row.get("topic") or ""),
        first_company(companies),
        str(row.get("claim_type") or ""),
        str(row.get("exposure_level") or ""),
        str(row.get("section") or ""),
        str(row.get("source_title") or ""),
        str(row.get("claim_text") or row.get("evidence_span") or ""),
    ]
    return "\n".join(part for part in parts if part)
