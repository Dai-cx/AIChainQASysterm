"""Claim and dossier memory backed by PostgreSQL."""

from __future__ import annotations

from typing import Any, Iterable
import psycopg
from psycopg.types.json import Jsonb
from aika.research_claims import (
    ResearchHit,
    ResearchMemory,
    apply_claim_reviews,
    build_segment_dossiers,
    normalize_claim_review,
    normalize_claim_row,
    parse_companies,
    query_topics,
)
from aika.semantic_index import dossier_to_semantic_text

from .common import claim_semantic_text, stable_content_hash


class PostgresResearchMemory:
    """Claim and dossier rule-retrieval adapter backed by PostgreSQL."""

    def __init__(self, store: PostgresRetrievalStore) -> None:
        self.store = store

    def _memory(
        self,
        *,
        topics: Iterable[str] | None = None,
        companies: Iterable[str] | None = None,
        claim_types: Iterable[str] | None = None,
    ) -> ResearchMemory:
        topic_values = [str(item) for item in (topics or []) if str(item)]
        company_values = [str(item) for item in (companies or []) if str(item)]
        type_values = [str(item) for item in (claim_types or []) if str(item)]
        claim_clauses = ["review_status <> 'rejected'"]
        claim_params: list[Any] = []
        if topic_values:
            claim_clauses.append("topic = ANY(%s::text[])")
            claim_params.append(topic_values)
        if company_values:
            claim_clauses.append("companies && %s::text[]")
            claim_params.append(company_values)
        if type_values:
            claim_clauses.append("claim_type = ANY(%s::text[])")
            claim_params.append(type_values)
        dossier_clauses: list[str] = []
        dossier_params: list[Any] = []
        if topic_values:
            dossier_clauses.append("topic = ANY(%s::text[])")
            dossier_params.append(topic_values)
        with self.store.pool.connection() as connection:
            claims = [
                normalize_claim_row(dict(row))
                for row in connection.execute(
                    f"""
                    SELECT claim_id, claim_type, topic, claim_text, companies,
                           mechanism, direction, horizon, metric, value, unit,
                           source_report_id, source_title, page, section, source_tier,
                           evidence_span, confidence, as_of_date, exposure_level,
                           review_status, reviewer_note, quality_flags,
                           conflict_group_id, reviewed_at, reviewer
                    FROM research_claims
                    WHERE {' AND '.join(claim_clauses)}
                    """,
                    claim_params,
                ).fetchall()
            ]
            dossier_sql = "SELECT payload FROM segment_dossiers"
            if dossier_clauses:
                dossier_sql += " WHERE " + " AND ".join(dossier_clauses)
            dossiers = [
                dict(row["payload"] or {})
                for row in connection.execute(dossier_sql, dossier_params).fetchall()
            ]
        return ResearchMemory(claims, dossiers)

    def search(self, question: str, plan: Any, *, limit: int = 8) -> list[ResearchHit]:
        topics = query_topics(question, getattr(plan, "topics", []), getattr(plan, "expanded_topics", []))
        return self._memory(topics=topics).search(question, plan, limit=limit)

    def search_global_dossiers(
        self,
        question: str,
        plan: Any,
        *,
        limit: int = 3,
        topics: list[str] | None = None,
    ) -> list[ResearchHit]:
        selected = topics or query_topics(question, getattr(plan, "topics", []), getattr(plan, "expanded_topics", []))
        return self._memory(topics=selected).search_global_dossiers(
            question,
            plan,
            limit=limit,
            topics=selected,
        )

    def search_local_claims(
        self,
        question: str,
        plan: Any,
        *,
        limit: int = 12,
        claim_types: list[str] | set[str] | tuple[str, ...] | None = None,
        companies: list[str] | set[str] | tuple[str, ...] | None = None,
        topics: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> list[ResearchHit]:
        selected_topics = list(topics or []) or query_topics(
            question,
            getattr(plan, "topics", []),
            getattr(plan, "expanded_topics", []),
        )
        selected_companies = list(companies or getattr(plan, "companies", []) or [])
        return self._memory(
            topics=selected_topics,
            companies=selected_companies,
            claim_types=claim_types,
        ).search_local_claims(
            question,
            plan,
            limit=limit,
            claim_types=claim_types,
            companies=companies,
            topics=selected_topics,
        )

    def get_claim(self, claim_id: str) -> dict[str, Any]:
        with self.store.pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_claims WHERE claim_id = %s",
                (claim_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Claim not found: {claim_id}")
        return normalize_claim_row(dict(row))

    def review_claim(
        self,
        claim_id: str,
        updates: dict[str, Any],
        *,
        reviewer: str = "frontend",
    ) -> dict[str, Any]:
        review = normalize_claim_review(claim_id, updates, reviewer=reviewer)
        with self.store.pool.connection() as connection, connection.transaction():
            current_row = connection.execute(
                "SELECT * FROM research_claims WHERE claim_id = %s FOR UPDATE",
                (claim_id,),
            ).fetchone()
            if current_row is None:
                raise KeyError(f"Claim not found: {claim_id}")
            current = normalize_claim_row(dict(current_row))
            updated = normalize_claim_row(apply_claim_reviews([current], {claim_id: review})[0])
            old_topic = str(current.get("topic") or "")
            semantic_text = claim_semantic_text(updated)
            digest = stable_content_hash(
                {
                    key: updated.get(key)
                    for key in (
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
                        "evidence_span",
                        "confidence",
                        "as_of_date",
                        "exposure_level",
                        "review_status",
                        "reviewer_note",
                        "quality_flags",
                        "conflict_group_id",
                    )
                }
            )
            connection.execute(
                """
                INSERT INTO claim_reviews(
                    claim_id, updates, review_hash, reviewer, created_at
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    claim_id,
                    Jsonb(review),
                    stable_content_hash(review),
                    str(review["reviewer"]),
                    review["updated_at"],
                ),
            )
            connection.execute(
                """
                UPDATE research_claims SET
                    claim_type = %s, topic = %s, claim_text = %s, companies = %s,
                    mechanism = %s, direction = %s, horizon = %s, metric = %s,
                    value = %s, unit = %s, evidence_span = %s, confidence = %s,
                    as_of_date = %s, exposure_level = %s, review_status = %s,
                    reviewer_note = %s, quality_flags = %s, conflict_group_id = %s,
                    reviewed_at = %s, reviewer = %s, semantic_text = %s,
                    content_hash = %s, embedding = NULL, embedding_status = 'stale',
                    updated_at = now()
                WHERE claim_id = %s
                """,
                (
                    str(updated.get("claim_type") or ""),
                    str(updated.get("topic") or ""),
                    str(updated.get("claim_text") or ""),
                    parse_companies(updated.get("companies", [])),
                    str(updated.get("mechanism") or ""),
                    str(updated.get("direction") or ""),
                    str(updated.get("horizon") or ""),
                    str(updated.get("metric") or ""),
                    str(updated.get("value") or ""),
                    str(updated.get("unit") or ""),
                    str(updated.get("evidence_span") or ""),
                    str(updated.get("confidence") or ""),
                    str(updated.get("as_of_date") or ""),
                    str(updated.get("exposure_level") or ""),
                    str(updated.get("review_status") or "revised"),
                    str(updated.get("reviewer_note") or ""),
                    str(updated.get("quality_flags") or ""),
                    str(updated.get("conflict_group_id") or ""),
                    review["updated_at"],
                    str(review["reviewer"]),
                    semantic_text,
                    digest,
                    claim_id,
                ),
            )
            self._rebuild_topics(connection, {old_topic, str(updated.get("topic") or "")})
        return self.get_claim(claim_id)

    def _rebuild_topics(
        self,
        connection: psycopg.Connection[Any],
        topics: set[str],
    ) -> None:
        for topic in {item for item in topics if item}:
            rows = [
                normalize_claim_row(dict(row))
                for row in connection.execute(
                    "SELECT * FROM research_claims WHERE topic = %s AND review_status <> 'rejected'",
                    (topic,),
                ).fetchall()
            ]
            dossiers = build_segment_dossiers(rows)
            if not dossiers:
                connection.execute("DELETE FROM segment_dossiers WHERE topic = %s", (topic,))
                continue
            dossier = dossiers[0]
            semantic_text = dossier_to_semantic_text(dossier)
            digest = stable_content_hash(dossier)
            connection.execute(
                """
                INSERT INTO segment_dossiers(topic, summary, payload, semantic_text, content_hash)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (topic) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    payload = EXCLUDED.payload,
                    semantic_text = EXCLUDED.semantic_text,
                    content_hash = EXCLUDED.content_hash,
                    embedding = NULL,
                    embedding_status = 'stale',
                    updated_at = now()
                """,
                (
                    topic,
                    str(dossier.get("summary") or ""),
                    Jsonb(dossier),
                    semantic_text,
                    digest,
                ),
            )

    def claim_stats(self) -> dict[str, Any]:
        with self.store.pool.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    count(DISTINCT claim_id) AS claims,
                    count(DISTINCT claim_id) FILTER (
                        WHERE review_status IN ('approved', 'revised', 'rejected', 'needs_review')
                    ) AS reviewed_claims,
                    count(DISTINCT claim_id) FILTER (
                        WHERE review_status = 'rejected'
                    ) AS rejected_claims,
                    count(DISTINCT company) FILTER (
                        WHERE claim_type = 'company_exposure'
                          AND exposure_level IN ('core', 'direct')
                    ) AS direct_exposure_companies
                FROM research_claims
                LEFT JOIN LATERAL unnest(companies) AS company ON true
                """
            ).fetchone()
            dossier_count = int(
                connection.execute("SELECT count(*) AS count FROM segment_dossiers").fetchone()["count"]
            )
            type_rows = connection.execute(
                "SELECT claim_type, count(*) AS count FROM research_claims GROUP BY claim_type"
            ).fetchall()
        assert row is not None
        return {
            "claims": int(row["claims"] or 0),
            "dossiers": dossier_count,
            "reviewed_claims": int(row["reviewed_claims"] or 0),
            "rejected_claims": int(row["rejected_claims"] or 0),
            "direct_exposure_companies": int(row["direct_exposure_companies"] or 0),
            "claim_type_counts": {
                str(item["claim_type"] or "unknown"): int(item["count"] or 0)
                for item in type_rows
            },
        }
