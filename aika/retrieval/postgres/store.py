"""Session, readiness and metadata helpers for the retrieval store."""

from __future__ import annotations

import os
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .common import (
    EMBEDDING_DIMENSIONS,
    PostgresRetrievalError,
    _configure_connection,
    require_database_url,
)

from .rag_sync import RagSyncMixin
from .claim_sync import ClaimSyncMixin
from .embeddings import EmbeddingMixin


class PostgresRetrievalStore(RagSyncMixin, ClaimSyncMixin, EmbeddingMixin):
    def __init__(
        self,
        database_url: str | None = None,
        *,
        min_size: int | None = None,
        max_size: int | None = None,
        hnsw_ef_search: int | None = None,
    ) -> None:
        self.database_url = require_database_url(database_url)
        configured_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
        if configured_dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(f"EMBEDDING_DIMENSIONS must be {EMBEDDING_DIMENSIONS}")
        self.min_size = int(os.getenv("DB_POOL_MIN_SIZE", "1") if min_size is None else min_size)
        self.max_size = int(os.getenv("DB_POOL_MAX_SIZE", "8") if max_size is None else max_size)
        self.hnsw_ef_search = int(
            os.getenv("PG_HNSW_EF_SEARCH", "100") if hnsw_ef_search is None else hnsw_ef_search
        )
        if self.min_size < 0 or self.max_size < 1 or self.min_size > self.max_size:
            raise ValueError("invalid PostgreSQL pool size")
        if self.hnsw_ef_search <= 0:
            raise ValueError("PG_HNSW_EF_SEARCH must be positive")
        self.pool = ConnectionPool(
            conninfo=self.database_url,
            min_size=self.min_size,
            max_size=self.max_size,
            kwargs={"row_factory": dict_row},
            configure=_configure_connection,
            open=True,
        )

    @classmethod
    def from_env(cls) -> "PostgresRetrievalStore":
        return cls()

    def close(self) -> None:
        self.pool.close()

    def ensure_ready(self) -> None:
        try:
            with self.pool.connection() as connection:
                row = connection.execute(
                    """
                    SELECT
                        to_regclass('public.rag_chunks') IS NOT NULL AS has_rag,
                        to_regclass('public.research_claims') IS NOT NULL AS has_claims,
                        to_regclass('public.segment_dossiers') IS NOT NULL AS has_dossiers,
                        to_regclass('public.rag_chunks_bm25_idx') IS NOT NULL AS has_bm25,
                        to_regclass('public.rag_chunks_embedding_hnsw_idx') IS NOT NULL AS has_rag_hnsw,
                        to_regclass('public.research_claims_embedding_hnsw_idx') IS NOT NULL AS has_claim_hnsw,
                        to_regclass('public.segment_dossiers_embedding_hnsw_idx') IS NOT NULL AS has_dossier_hnsw,
                        EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS has_vector,
                        EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_search') AS has_search
                    """
                ).fetchone()
        except Exception as exc:
            raise PostgresRetrievalError(f"PostgreSQL retrieval backend unavailable: {exc}") from exc
        required = (
            "has_rag",
            "has_claims",
            "has_dossiers",
            "has_bm25",
            "has_rag_hnsw",
            "has_claim_hnsw",
            "has_dossier_hnsw",
            "has_vector",
            "has_search",
        )
        if not row or not all(bool(row[key]) for key in required):
            raise PostgresRetrievalError("PostgreSQL retrieval schema is not initialized; run migrate_postgres.py")

    def chunk_ids(self) -> set[str]:
        with self.pool.connection() as connection:
            return {str(row["chunk_id"]) for row in connection.execute("SELECT chunk_id FROM rag_chunks")}

    def semantic_rag_chunk_ids(self) -> set[str]:
        with self.pool.connection() as connection:
            return {
                str(row["chunk_id"])
                for row in connection.execute(
                    "SELECT chunk_id FROM rag_chunks WHERE embedding_status = 'ready' AND embedding IS NOT NULL"
                )
            }
