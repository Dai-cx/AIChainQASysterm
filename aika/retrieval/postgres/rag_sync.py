"""Mixin part of the PostgreSQL retrieval store: 'rag_sync'."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable
from psycopg.types.json import Jsonb
from aika.rag_index import RagDocument
from aika.research_claims import normalize_claim_review

from .common import (
    SCHEMA_VERSION,
    corpus_hash,
    rag_search_text,
    rag_semantic_text,
    stable_content_hash,
)


class RagSyncMixin:
    def sync_rag_documents(self, documents: Iterable[RagDocument | dict[str, Any]]) -> dict[str, Any]:
        rows = [asdict(item) if isinstance(item, RagDocument) else dict(item) for item in documents]
        now = datetime.now(timezone.utc)
        values = []
        for row in rows:
            chunk_id = str(row.get("chunk_id") or "").strip()
            if not chunk_id:
                raise ValueError("RAG chunk_id is required")
            search_text = rag_search_text(row)
            semantic_text = rag_semantic_text(row)
            digest = stable_content_hash(
                {
                    key: row.get(key)
                    for key in (
                        "report_id",
                        "kind",
                        "company",
                        "source_title",
                        "source_url",
                        "source_tier",
                        "source_type",
                        "page",
                        "section",
                        "content_type",
                        "table_id",
                        "text",
                    )
                }
            )
            values.append(
                (
                    chunk_id,
                    str(row.get("report_id") or ""),
                    str(row.get("kind") or ""),
                    str(row.get("company") or ""),
                    str(row.get("source_title") or ""),
                    str(row.get("source_url") or ""),
                    str(row.get("source_tier") or ""),
                    str(row.get("source_type") or ""),
                    str(row.get("page") or ""),
                    str(row.get("section") or ""),
                    str(row.get("content_type") or "text"),
                    str(row.get("table_id") or ""),
                    str(row.get("text") or ""),
                    search_text,
                    semantic_text,
                    Jsonb(dict(row.get("token_counts") or {})),
                    int(row.get("token_count") or 0),
                    digest,
                    now,
                )
            )
        with self.pool.connection() as connection, connection.transaction():
            connection.execute("CREATE TEMP TABLE stage_rag_ids(chunk_id text PRIMARY KEY) ON COMMIT DROP")
            if values:
                connection.cursor().executemany(
                    """
                    INSERT INTO rag_chunks (
                        chunk_id, report_id, kind, company, source_title, source_url,
                        source_tier, source_type, page, section, content_type, table_id,
                        text, search_text, semantic_text, token_counts, token_count,
                        content_hash, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        report_id = EXCLUDED.report_id,
                        kind = EXCLUDED.kind,
                        company = EXCLUDED.company,
                        source_title = EXCLUDED.source_title,
                        source_url = EXCLUDED.source_url,
                        source_tier = EXCLUDED.source_tier,
                        source_type = EXCLUDED.source_type,
                        page = EXCLUDED.page,
                        section = EXCLUDED.section,
                        content_type = EXCLUDED.content_type,
                        table_id = EXCLUDED.table_id,
                        text = EXCLUDED.text,
                        search_text = EXCLUDED.search_text,
                        semantic_text = EXCLUDED.semantic_text,
                        token_counts = EXCLUDED.token_counts,
                        token_count = EXCLUDED.token_count,
                        embedding = CASE
                            WHEN rag_chunks.content_hash = EXCLUDED.content_hash THEN rag_chunks.embedding
                            ELSE NULL
                        END,
                        embedding_status = CASE
                            WHEN rag_chunks.content_hash = EXCLUDED.content_hash THEN rag_chunks.embedding_status
                            ELSE 'stale'
                        END,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = EXCLUDED.updated_at
                    """,
                    values,
                )
                connection.cursor().executemany(
                    "INSERT INTO stage_rag_ids(chunk_id) VALUES (%s)",
                    [(value[0],) for value in values],
                )
            deleted = connection.execute(
                "DELETE FROM rag_chunks WHERE NOT EXISTS (SELECT 1 FROM stage_rag_ids s WHERE s.chunk_id = rag_chunks.chunk_id)"
            ).rowcount
            digest = corpus_hash(value[0] for value in values)
            connection.execute(
                """
                INSERT INTO retrieval_builds(
                    build_kind, corpus_hash, record_count, status, details,
                    schema_version, completed_at
                ) VALUES ('rag', %s, %s, 'completed', %s, %s, now())
                """,
                (digest, len(values), Jsonb({"deleted": deleted}), SCHEMA_VERSION),
            )
        return {"record_count": len(values), "deleted": deleted, "corpus_hash": digest}

    def latest_claim_reviews(self) -> dict[str, dict[str, Any]]:
        with self.pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (claim_id) claim_id, updates
                FROM claim_reviews
                ORDER BY claim_id, created_at DESC, id DESC
                """
            ).fetchall()
        return {str(row["claim_id"]): dict(row["updates"] or {}) for row in rows}

    def import_claim_reviews(self, reviews: Iterable[dict[str, Any]]) -> int:
        values = []
        for source in reviews:
            claim_id = str(source.get("claim_id") or "").strip()
            if not claim_id:
                continue
            review = normalize_claim_review(claim_id, dict(source))
            values.append(
                (
                    claim_id,
                    Jsonb(review),
                    stable_content_hash(review),
                    str(review["reviewer"]),
                    review["updated_at"],
                )
            )
        if not values:
            return 0
        with self.pool.connection() as connection, connection.transaction():
            before = int(connection.execute("SELECT count(*) AS count FROM claim_reviews").fetchone()["count"])
            connection.cursor().executemany(
                """
                INSERT INTO claim_reviews(claim_id, updates, review_hash, reviewer, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (review_hash) DO NOTHING
                """,
                values,
            )
            after = int(connection.execute("SELECT count(*) AS count FROM claim_reviews").fetchone()["count"])
        return after - before
