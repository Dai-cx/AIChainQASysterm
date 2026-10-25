"""Compatibility shim.

The PostgreSQL retrieval layer now lives in :mod:`aika.retrieval.postgres`.
This module keeps the historical import path working.
"""

from __future__ import annotations

from aika.retrieval.postgres import (
    EMBEDDING_DIMENSIONS,
    MIGRATIONS_DIR,
    ROOT_DIR,
    SCHEMA_VERSION,
    PostgresRagIndex,
    PostgresResearchMemory,
    PostgresRetrievalError,
    PostgresRetrievalStore,
    PostgresSemanticIndex,
    claim_semantic_text,
    corpus_hash,
    migrate_database,
    rag_search_text,
    rag_semantic_text,
    require_database_url,
    stable_content_hash,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "MIGRATIONS_DIR",
    "PostgresRagIndex",
    "PostgresResearchMemory",
    "PostgresRetrievalError",
    "PostgresRetrievalStore",
    "PostgresSemanticIndex",
    "ROOT_DIR",
    "SCHEMA_VERSION",
    "claim_semantic_text",
    "corpus_hash",
    "migrate_database",
    "rag_search_text",
    "rag_semantic_text",
    "require_database_url",
    "stable_content_hash",
]
