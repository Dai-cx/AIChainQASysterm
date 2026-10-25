"""PostgreSQL retrieval layer: RAG index, claim memory and semantic index."""

from __future__ import annotations

from .common import (
    EMBEDDING_DIMENSIONS,
    MIGRATIONS_DIR,
    ROOT_DIR,
    SCHEMA_VERSION,
    PostgresRetrievalError,
    claim_semantic_text,
    corpus_hash,
    migrate_database,
    rag_search_text,
    rag_semantic_text,
    require_database_url,
    stable_content_hash,
)
from .memory import (
    PostgresResearchMemory,
)
from .rag import (
    PostgresRagIndex,
)
from .semantic import (
    PostgresSemanticIndex,
)
from .store import (
    PostgresRetrievalStore,
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
