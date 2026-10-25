"""pgvector semantic index backed by PostgreSQL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import psycopg

from aika.research_claims import claim_title, first_company
from aika.semantic_index import SemanticHit

if TYPE_CHECKING:  # pragma: no cover
    from .store import PostgresRetrievalStore

from .common import EMBEDDING_DIMENSIONS


class PostgresSemanticIndex:
    """Dense semantic retrieval adapter backed by pgvector HNSW indexes."""

    def __init__(
        self,
        store: PostgresRetrievalStore,
        *,
        embedding_client: Any,
    ) -> None:
        self.store = store
        self.embedding_client = embedding_client
        self.metadata = store.semantic_metadata()

    def search(
        self,
        question: str,
        *,
        top_k: int = 8,
        filters: dict[str, list[str]] | None = None,
    ) -> list[SemanticHit]:
        if top_k <= 0:
            return []
        vectors = self.embedding_client.embed_texts([question])
        if not vectors:
            return []
        vector = [float(value) for value in vectors[0]]
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"query embedding dimension mismatch: expected {EMBEDDING_DIMENSIONS}, got {len(vector)}"
            )
        selected_kinds = set((filters or {}).get("kinds") or ("rag", "claim", "dossier"))
        hits: list[SemanticHit] = []
        with self.store.pool.connection() as connection, connection.transaction():
            connection.execute(
                "SELECT set_config('hnsw.ef_search', %s, true)",
                (str(self.store.hnsw_ef_search),),
            )
            if "rag" in selected_kinds:
                hits.extend(self._search_rag(connection, vector, top_k, filters or {}))
            if "claim" in selected_kinds:
                hits.extend(self._search_claims(connection, vector, top_k, filters or {}))
            if "dossier" in selected_kinds:
                hits.extend(self._search_dossiers(connection, vector, top_k, filters or {}))
        hits.sort(key=lambda hit: (-hit.score, hit.kind, hit.topic, hit.company, hit.title))
        return hits[: max(0, top_k)]

    def _search_rag(
        self,
        connection: psycopg.Connection[Any],
        vector: list[float],
        top_k: int,
        filters: dict[str, list[str]],
    ) -> list[SemanticHit]:
        clauses = ["embedding_status = 'ready'", "embedding IS NOT NULL"]
        params: list[Any] = [vector]
        companies = filters.get("companies") or []
        if companies:
            clauses.append("company = ANY(%s::text[])")
            params.append(companies)
        params.extend([vector, max(top_k, 1)])
        rows = connection.execute(
            f"""
            SELECT chunk_id, source_title, text, page, section, company,
                   source_tier, source_type,
                   1 - (embedding::halfvec(2048) <=> %s::vector::halfvec(2048)) AS score
            FROM rag_chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY embedding::halfvec(2048) <=> %s::vector::halfvec(2048)
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [
            SemanticHit(
                doc_id=f"rag:{row['chunk_id']}",
                kind="rag",
                title=str(row["source_title"] or "RAG 原文片段"),
                text=str(row["text"] or ""),
                score=round(float(row["score"] or 0.0), 6),
                source=str(row["source_title"] or ""),
                page=str(row["page"] or ""),
                section=str(row["section"] or ""),
                company=str(row["company"] or ""),
                ref_id=str(row["chunk_id"] or ""),
                source_tier=str(row["source_tier"] or ""),
                source_type=str(row["source_type"] or ""),
            )
            for row in rows
        ]

    def _search_claims(
        self,
        connection: psycopg.Connection[Any],
        vector: list[float],
        top_k: int,
        filters: dict[str, list[str]],
    ) -> list[SemanticHit]:
        clauses = [
            "embedding_status = 'ready'",
            "embedding IS NOT NULL",
            "review_status <> 'rejected'",
        ]
        params: list[Any] = [vector]
        companies = filters.get("companies") or []
        topics = filters.get("topics") or []
        if companies:
            clauses.append("companies && %s::text[]")
            params.append(companies)
        if topics:
            clauses.append("topic = ANY(%s::text[])")
            params.append(topics)
        params.extend([vector, max(top_k, 1)])
        rows = connection.execute(
            f"""
            SELECT claim_id, claim_type, topic, claim_text, companies,
                   source_title, page, section, source_tier, exposure_level,
                   confidence, as_of_date,
                   1 - (embedding::halfvec(2048) <=> %s::vector::halfvec(2048)) AS score
            FROM research_claims
            WHERE {' AND '.join(clauses)}
            ORDER BY embedding::halfvec(2048) <=> %s::vector::halfvec(2048)
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [
            SemanticHit(
                doc_id=f"claim:{row['claim_id']}",
                kind="claim",
                title=claim_title(dict(row)),
                text=str(row["claim_text"] or ""),
                score=round(float(row["score"] or 0.0), 6),
                source=str(row["source_title"] or ""),
                page=str(row["page"] or ""),
                section=str(row["section"] or ""),
                topic=str(row["topic"] or ""),
                company=first_company(row["companies"] or []),
                claim_type=str(row["claim_type"] or ""),
                exposure_level=str(row["exposure_level"] or ""),
                ref_id=str(row["claim_id"] or ""),
                source_tier=str(row["source_tier"] or ""),
                confidence=str(row["confidence"] or ""),
                as_of_date=str(row["as_of_date"] or ""),
            )
            for row in rows
        ]

    def _search_dossiers(
        self,
        connection: psycopg.Connection[Any],
        vector: list[float],
        top_k: int,
        filters: dict[str, list[str]],
    ) -> list[SemanticHit]:
        clauses = ["embedding_status = 'ready'", "embedding IS NOT NULL"]
        params: list[Any] = [vector]
        topics = filters.get("topics") or []
        if topics:
            clauses.append("topic = ANY(%s::text[])")
            params.append(topics)
        params.extend([vector, max(top_k, 1)])
        rows = connection.execute(
            f"""
            SELECT topic, semantic_text,
                   1 - (embedding::halfvec(2048) <=> %s::vector::halfvec(2048)) AS score
            FROM segment_dossiers
            WHERE {' AND '.join(clauses)}
            ORDER BY embedding::halfvec(2048) <=> %s::vector::halfvec(2048)
            LIMIT %s
            """,
            params,
        ).fetchall()
        return [
            SemanticHit(
                doc_id=f"dossier:{row['topic']}",
                kind="dossier",
                title=f"{row['topic']} 产业链投研摘要",
                text=str(row["semantic_text"] or ""),
                score=round(float(row["score"] or 0.0), 6),
                topic=str(row["topic"] or ""),
                ref_id=str(row["topic"] or ""),
            )
            for row in rows
        ]

    def rag_chunk_ids(self) -> set[str]:
        return self.store.semantic_rag_chunk_ids()

    def metadata_dict(self) -> dict[str, Any]:
        return self.store.semantic_metadata().to_dict()
