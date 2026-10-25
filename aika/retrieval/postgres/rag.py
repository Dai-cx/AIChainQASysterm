"""BM25 / full text RAG index backed by PostgreSQL."""

from __future__ import annotations

from typing import Any
from aika.aika_core.text import normalize_text
from aika.rag_index import (
    RagHit,
    dedupe_hits,
    expand_query,
    is_low_value_hit,
    is_technical_question,
    make_snippet,
    source_priority,
    tokenize,
)

from .common import corpus_hash


class PostgresRagIndex:
    """BM25 RAG adapter backed by a ParadeDB index."""

    def __init__(self, store: PostgresRetrievalStore) -> None:
        self.store = store

    def search(
        self,
        question: str,
        *,
        top_k: int = 6,
        filters: dict[str, str] | None = None,
    ) -> list[RagHit]:
        filters = dict(filters or {})
        expanded = expand_query(question)
        tokens = tokenize(expanded)
        if not tokens or top_k <= 0:
            return []
        clauses = ["search_text ||| %s"]
        params: list[Any] = [expanded]
        for field in ("company", "source_type", "source_tier", "kind", "content_type"):
            value = str(filters.get(field) or "")
            if value:
                clauses.append(f"{field} = %s")
                params.append(value)
        candidate_k = max(top_k * 8, 40)
        params.append(candidate_k)
        with self.store.pool.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT chunk_id, report_id, source_title, source_tier, source_type,
                       page, section, content_type, table_id, company, text,
                       pdb.score(id) AS bm25_score
                FROM rag_chunks
                WHERE {' AND '.join(clauses)}
                ORDER BY pdb.score(id) DESC, chunk_id
                LIMIT %s
                """,
                params,
            ).fetchall()
        hits = [self._hit_from_row(dict(row), question, tokens) for row in rows]
        hits = [hit for hit in hits if not is_low_value_hit(hit)]
        hits.sort(key=lambda hit: (-hit.score, source_priority(hit), hit.source_title, hit.page, hit.chunk_id))
        return dedupe_hits(hits)[: max(0, top_k)]

    @staticmethod
    def _hit_from_row(row: dict[str, Any], question: str, tokens: list[str]) -> RagHit:
        score = float(row.get("bm25_score") or 0.0)
        question_norm = normalize_text(question)
        searchable = normalize_text(
            "\n".join(
                str(row.get(key) or "")
                for key in ("company", "source_title", "section", "text")
            )
        )
        if question_norm and question_norm in searchable:
            score += 3.0
        for field in ("company", "section", "source_title"):
            value = str(row.get(field) or "")
            if value and normalize_text(value) in question_norm:
                score += 0.8
        if str(row.get("source_tier") or "") == "1":
            score += 0.6
        if str(row.get("source_type") or "") == "authority_whitepaper":
            score += 0.8
        if is_technical_question(question) and str(row.get("source_type") or "") in {
            "technical_roadmap",
            "open_specification",
            "manual_open_specification",
            "benchmark_methodology",
            "technical_paper",
            "model_technical_report",
            "authority_whitepaper",
        }:
            score += 0.9
        text = str(row.get("text") or "")
        return RagHit(
            chunk_id=str(row.get("chunk_id") or ""),
            report_id=str(row.get("report_id") or ""),
            source_title=str(row.get("source_title") or ""),
            source_tier=str(row.get("source_tier") or ""),
            source_type=str(row.get("source_type") or ""),
            page=str(row.get("page") or ""),
            section=str(row.get("section") or ""),
            content_type=str(row.get("content_type") or "text"),
            table_id=str(row.get("table_id") or ""),
            company=str(row.get("company") or ""),
            text=text,
            snippet=make_snippet(text, tokens),
            score=round(score, 6),
        )

    def chunk_ids(self) -> set[str]:
        return self.store.chunk_ids()

    def metadata_dict(self) -> dict[str, Any]:
        return self.store.corpus_metadata("rag")

    def corpus_hash(self) -> str:
        return str(self.metadata_dict().get("corpus_hash") or corpus_hash(self.chunk_ids()))
