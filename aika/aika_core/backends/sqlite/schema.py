"""Table definitions and schema creation for the SQLite research index."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"


CLAIM_COLUMNS = [
    "claim_id",
    "claim_type",
    "topic",
    "claim_text",
    "companies",
    "mechanism",
    "direction",
    "horizon",
    "metric",
    "value",
    "unit",
    "source_report_id",
    "source_title",
    "page",
    "section",
    "source_tier",
    "evidence_span",
    "confidence",
    "as_of_date",
    "exposure_level",
    "review_status",
    "reviewer_note",
    "quality_flags",
    "conflict_group_id",
]


EVIDENCE_COLUMNS = [
    "evidence_id",
    "claim_id",
    "evidence",
    "source_report_id",
    "source_title",
    "page",
    "section",
    "source_tier",
    "as_of_date",
    "quality",
    "company",
    "topic",
    "claim_type",
    "confidence",
    "exposure_level",
]


DOSSIER_COLUMNS = ["dossier_id", "topic", "title", "content", "raw_json"]


RELATION_COLUMNS = [
    "relation_id",
    "head_type",
    "head_name",
    "relation",
    "tail_type",
    "tail_name",
    "evidence",
    "source_report_id",
    "source_title",
    "page",
    "section",
    "source_tier",
    "confidence",
    "review_status",
]


def _connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path))
    connection.row_factory = sqlite3.Row
    return connection


def _select_tokenizer(connection: sqlite3.Connection) -> str:
    try:
        connection.execute("CREATE VIRTUAL TABLE tokenizer_probe USING fts5(x, tokenize='trigram')")
        connection.execute("DROP TABLE tokenizer_probe")
        return "trigram"
    except sqlite3.OperationalError:
        connection.execute("CREATE VIRTUAL TABLE tokenizer_probe USING fts5(x, tokenize='unicode61')")
        connection.execute("DROP TABLE tokenizer_probe")
        return "unicode61"


def _create_schema(connection: sqlite3.Connection, *, tokenizer: str) -> None:
    claim_definitions = ",\n                ".join(f"{column} TEXT" for column in CLAIM_COLUMNS)
    evidence_definitions = ",\n                ".join(f"{column} TEXT" for column in EVIDENCE_COLUMNS)
    dossier_definitions = ",\n                ".join(f"{column} TEXT" for column in DOSSIER_COLUMNS)
    relation_definitions = ",\n                ".join(f"{column} TEXT" for column in RELATION_COLUMNS)
    connection.executescript(
        f"""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE claims (
            id INTEGER PRIMARY KEY,
            {claim_definitions}
        );

        CREATE TABLE evidence_spans (
            id INTEGER PRIMARY KEY,
            {evidence_definitions}
        );

        CREATE TABLE dossiers (
            id INTEGER PRIMARY KEY,
            {dossier_definitions}
        );

        CREATE TABLE relations (
            id INTEGER PRIMARY KEY,
            {relation_definitions}
        );

        CREATE VIRTUAL TABLE claims_fts USING fts5(
            claim_text,
            evidence_span,
            topic,
            companies,
            tokenize='{tokenizer}'
        );

        CREATE VIRTUAL TABLE evidence_fts USING fts5(
            evidence,
            source_title,
            company,
            topic,
            tokenize='{tokenizer}'
        );

        CREATE VIRTUAL TABLE dossiers_fts USING fts5(
            title,
            content,
            topic,
            tokenize='{tokenizer}'
        );

        CREATE INDEX claims_topic_idx ON claims(topic);
        CREATE INDEX claims_type_idx ON claims(claim_type);
        CREATE INDEX claims_id_idx ON claims(claim_id);
        CREATE INDEX evidence_claim_idx ON evidence_spans(claim_id);
        CREATE INDEX evidence_topic_idx ON evidence_spans(topic);
        CREATE INDEX evidence_company_idx ON evidence_spans(company);
        CREATE INDEX relations_head_idx ON relations(head_name);
        CREATE INDEX relations_tail_idx ON relations(tail_name);
        """
    )


def _write_metadata(connection: sqlite3.Connection, values: dict[str, Any]) -> None:
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [(str(key), str(value)) for key, value in sorted(values.items())],
    )
