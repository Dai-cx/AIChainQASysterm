"""Mixin part of the PostgreSQL retrieval store: 'embeddings'."""

from __future__ import annotations

from typing import Any
from aika.semantic_index import SemanticIndexMetadata

from .common import EMBEDDING_DIMENSIONS, SCHEMA_VERSION, corpus_hash


class EmbeddingMixin:
    def pending_embeddings(self, *, force: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
        status_clause = "" if force else "WHERE embedding_status IN ('missing', 'stale', 'failed') OR embedding IS NULL"
        sql = f"""
            SELECT 'rag' AS kind, chunk_id AS ref_id, semantic_text, content_hash
            FROM rag_chunks
            {status_clause}
            UNION ALL
            SELECT 'claim' AS kind, claim_id AS ref_id, semantic_text, content_hash
            FROM research_claims
            {status_clause}
            UNION ALL
            SELECT 'dossier' AS kind, topic AS ref_id, semantic_text, content_hash
            FROM segment_dossiers
            {status_clause}
            ORDER BY kind, ref_id
        """
        params: tuple[Any, ...] = ()
        if limit is not None and limit >= 0:
            sql += " LIMIT %s"
            params = (limit,)
        with self.pool.connection() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def update_embeddings(
        self,
        rows: list[dict[str, Any]],
        vectors: list[list[float]],
        *,
        model: str,
    ) -> None:
        if len(rows) != len(vectors):
            raise ValueError("embedding row/vector count mismatch")
        table_map = {
            "rag": ("rag_chunks", "chunk_id"),
            "claim": ("research_claims", "claim_id"),
            "dossier": ("segment_dossiers", "topic"),
        }
        with self.pool.connection() as connection, connection.transaction():
            for row, vector in zip(rows, vectors):
                if len(vector) != EMBEDDING_DIMENSIONS:
                    raise ValueError(
                        f"embedding dimension mismatch: expected {EMBEDDING_DIMENSIONS}, got {len(vector)}"
                    )
                table, key = table_map[str(row["kind"])]
                connection.execute(
                    f"""
                    UPDATE {table}
                    SET embedding = %s,
                        embedding_status = 'ready',
                        embedding_model = %s,
                        embedded_at = now(),
                        updated_at = now()
                    WHERE {key} = %s AND content_hash = %s
                    """,
                    (vector, model, str(row["ref_id"]), str(row["content_hash"])),
                )

    def mark_embedding_failed(self, row: dict[str, Any]) -> None:
        table_map = {
            "rag": ("rag_chunks", "chunk_id"),
            "claim": ("research_claims", "claim_id"),
            "dossier": ("segment_dossiers", "topic"),
        }
        table, key = table_map[str(row["kind"])]
        with self.pool.connection() as connection:
            connection.execute(
                f"""
                UPDATE {table}
                SET embedding_status = 'failed', updated_at = now()
                WHERE {key} = %s AND content_hash = %s
                """,
                (str(row["ref_id"]), str(row["content_hash"])),
            )
            connection.commit()

    def record_embedding_build(self, *, model: str, count: int, status: str = "completed") -> None:
        with self.pool.connection() as connection:
            content_rows = connection.execute(
                """
                SELECT content_hash FROM rag_chunks
                UNION ALL SELECT content_hash FROM research_claims
                UNION ALL SELECT content_hash FROM segment_dossiers
                """
            ).fetchall()
            digest = corpus_hash(str(row["content_hash"]) for row in content_rows)
            connection.execute(
                """
                INSERT INTO retrieval_builds(
                    build_kind, corpus_hash, record_count, embedding_model,
                    embedding_dimensions, status, schema_version, completed_at
                ) VALUES ('embedding', %s, %s, %s, %s, %s, %s, now())
                """,
                (
                    digest,
                    count,
                    model,
                    EMBEDDING_DIMENSIONS,
                    status,
                    SCHEMA_VERSION,
                ),
            )
            connection.commit()

    def corpus_metadata(self, kind: str) -> dict[str, Any]:
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT build_kind, corpus_hash, record_count, embedding_model,
                       embedding_dimensions, status, created_at, completed_at,
                       details, schema_version
                FROM retrieval_builds
                WHERE build_kind = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (kind,),
            ).fetchone()
        return dict(row) if row else {}

    def semantic_metadata(self) -> SemanticIndexMetadata:
        with self.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM rag_chunks
                     WHERE embedding_status = 'ready' AND embedding IS NOT NULL) +
                    (SELECT count(*) FROM research_claims
                     WHERE embedding_status = 'ready' AND embedding IS NOT NULL) +
                    (SELECT count(*) FROM segment_dossiers
                     WHERE embedding_status = 'ready' AND embedding IS NOT NULL) AS vector_count,
                    (SELECT count(*) FROM rag_chunks) +
                    (SELECT count(*) FROM research_claims) +
                    (SELECT count(*) FROM segment_dossiers) AS document_count,
                    COALESCE((
                        SELECT embedding_model FROM retrieval_builds
                        WHERE build_kind = 'embedding' ORDER BY id DESC LIMIT 1
                    ), '') AS embedding_model,
                    COALESCE((
                        SELECT completed_at FROM retrieval_builds
                        WHERE build_kind = 'embedding' ORDER BY id DESC LIMIT 1
                    ), now()) AS built_at
                """
            ).fetchone()
        assert row is not None
        return SemanticIndexMetadata(
            index_version="postgres-pgvector-v1",
            built_at=str(row["built_at"]),
            document_count=int(row["document_count"] or 0),
            vector_count=int(row["vector_count"] or 0),
            dimension=EMBEDDING_DIMENSIONS,
            embedding_model=str(row["embedding_model"] or ""),
            rag_dir="postgresql",
            research_dir="postgresql",
            index_dir="postgresql",
        )
