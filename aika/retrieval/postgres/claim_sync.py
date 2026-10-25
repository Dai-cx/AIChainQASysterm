"""Mixin part of the PostgreSQL retrieval store: 'claim_sync'."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb

from aika.research_claims import (
    apply_claim_reviews,
    build_segment_dossiers,
    normalize_claim_row,
    parse_companies,
)
from aika.semantic_index import dossier_to_semantic_text

from .common import SCHEMA_VERSION, claim_semantic_text, corpus_hash, stable_content_hash


class ClaimSyncMixin:
    def sync_research(
        self,
        claims: Iterable[dict[str, Any]],
        dossiers: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized = [normalize_claim_row(dict(row)) for row in claims]
        if any(not str(row.get("claim_id") or "").strip() for row in normalized):
            raise ValueError("research claim_id is required")
        effective_claims = apply_claim_reviews(normalized, self.latest_claim_reviews())
        if dossiers is not None and effective_claims == normalized:
            effective_dossiers = [dict(row) for row in dossiers]
        else:
            effective_dossiers = build_segment_dossiers(
                [row for row in effective_claims if str(row.get("review_status") or "") != "rejected"]
            )
        with self.pool.connection() as connection, connection.transaction():
            claim_count, deleted_claims = self._sync_claims(connection, effective_claims)
            dossier_count, deleted_dossiers = self._sync_dossiers(connection, effective_dossiers)
            digest = corpus_hash(
                [str(row.get("claim_id") or "") for row in effective_claims]
                + [str(row.get("topic") or "") for row in effective_dossiers]
            )
            connection.execute(
                """
                INSERT INTO retrieval_builds(
                    build_kind, corpus_hash, record_count, status, details,
                    schema_version, completed_at
                ) VALUES ('research', %s, %s, 'completed', %s, %s, now())
                """,
                (
                    digest,
                    claim_count + dossier_count,
                    Jsonb({"claims": claim_count, "dossiers": dossier_count}),
                    SCHEMA_VERSION,
                ),
            )
        return {
            "claims": claim_count,
            "dossiers": dossier_count,
            "deleted_claims": deleted_claims,
            "deleted_dossiers": deleted_dossiers,
            "corpus_hash": digest,
        }

    def _sync_claims(
        self,
        connection: psycopg.Connection[Any],
        claims: list[dict[str, Any]],
    ) -> tuple[int, int]:
        connection.execute("CREATE TEMP TABLE stage_claim_ids(claim_id text PRIMARY KEY) ON COMMIT DROP")
        values = []
        now = datetime.now(timezone.utc)
        for source in claims:
            row = normalize_claim_row(source)
            semantic_text = claim_semantic_text(row)
            digest = stable_content_hash(
                {
                    key: row.get(key)
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
                    )
                }
            )
            reviewed_at = row.get("reviewed_at") or None
            values.append(
                (
                    str(row.get("claim_id") or ""),
                    str(row.get("claim_type") or ""),
                    str(row.get("topic") or ""),
                    str(row.get("claim_text") or ""),
                    parse_companies(row.get("companies", [])),
                    str(row.get("mechanism") or ""),
                    str(row.get("direction") or ""),
                    str(row.get("horizon") or ""),
                    str(row.get("metric") or ""),
                    str(row.get("value") or ""),
                    str(row.get("unit") or ""),
                    str(row.get("source_report_id") or ""),
                    str(row.get("source_title") or ""),
                    str(row.get("page") or ""),
                    str(row.get("section") or ""),
                    str(row.get("source_tier") or ""),
                    str(row.get("evidence_span") or ""),
                    str(row.get("confidence") or ""),
                    str(row.get("as_of_date") or ""),
                    str(row.get("exposure_level") or ""),
                    str(row.get("review_status") or "auto"),
                    str(row.get("reviewer_note") or ""),
                    str(row.get("quality_flags") or ""),
                    str(row.get("conflict_group_id") or ""),
                    reviewed_at,
                    str(row.get("reviewer") or ""),
                    semantic_text,
                    digest,
                    now,
                )
            )
        if values:
            connection.cursor().executemany(
                """
                INSERT INTO research_claims (
                    claim_id, claim_type, topic, claim_text, companies, mechanism,
                    direction, horizon, metric, value, unit, source_report_id,
                    source_title, page, section, source_tier, evidence_span,
                    confidence, as_of_date, exposure_level, review_status,
                    reviewer_note, quality_flags, conflict_group_id, reviewed_at,
                    reviewer, semantic_text, content_hash, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (claim_id) DO UPDATE SET
                    claim_type = EXCLUDED.claim_type,
                    topic = EXCLUDED.topic,
                    claim_text = EXCLUDED.claim_text,
                    companies = EXCLUDED.companies,
                    mechanism = EXCLUDED.mechanism,
                    direction = EXCLUDED.direction,
                    horizon = EXCLUDED.horizon,
                    metric = EXCLUDED.metric,
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    source_report_id = EXCLUDED.source_report_id,
                    source_title = EXCLUDED.source_title,
                    page = EXCLUDED.page,
                    section = EXCLUDED.section,
                    source_tier = EXCLUDED.source_tier,
                    evidence_span = EXCLUDED.evidence_span,
                    confidence = EXCLUDED.confidence,
                    as_of_date = EXCLUDED.as_of_date,
                    exposure_level = EXCLUDED.exposure_level,
                    review_status = EXCLUDED.review_status,
                    reviewer_note = EXCLUDED.reviewer_note,
                    quality_flags = EXCLUDED.quality_flags,
                    conflict_group_id = EXCLUDED.conflict_group_id,
                    reviewed_at = EXCLUDED.reviewed_at,
                    reviewer = EXCLUDED.reviewer,
                    semantic_text = EXCLUDED.semantic_text,
                    embedding = CASE
                        WHEN research_claims.content_hash = EXCLUDED.content_hash THEN research_claims.embedding
                        ELSE NULL
                    END,
                    embedding_status = CASE
                        WHEN research_claims.content_hash = EXCLUDED.content_hash THEN research_claims.embedding_status
                        ELSE 'stale'
                    END,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = EXCLUDED.updated_at
                """,
                values,
            )
            connection.cursor().executemany(
                "INSERT INTO stage_claim_ids(claim_id) VALUES (%s)",
                [(value[0],) for value in values],
            )
        deleted = connection.execute(
            """
            DELETE FROM research_claims
            WHERE NOT EXISTS (
                SELECT 1 FROM stage_claim_ids s WHERE s.claim_id = research_claims.claim_id
            )
            """
        ).rowcount
        return len(values), deleted

    def _sync_dossiers(
        self,
        connection: psycopg.Connection[Any],
        dossiers: list[dict[str, Any]],
    ) -> tuple[int, int]:
        connection.execute("CREATE TEMP TABLE stage_dossier_topics(topic text PRIMARY KEY) ON COMMIT DROP")
        values = []
        now = datetime.now(timezone.utc)
        for row in dossiers:
            topic = str(row.get("topic") or "")
            if not topic:
                raise ValueError("segment dossier topic is required")
            semantic_text = dossier_to_semantic_text(row)
            digest = stable_content_hash(row)
            values.append(
                (
                    topic,
                    str(row.get("summary") or ""),
                    Jsonb(row),
                    semantic_text,
                    digest,
                    now,
                )
            )
        if values:
            connection.cursor().executemany(
                """
                INSERT INTO segment_dossiers(
                    topic, summary, payload, semantic_text, content_hash, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (topic) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    payload = EXCLUDED.payload,
                    semantic_text = EXCLUDED.semantic_text,
                    embedding = CASE
                        WHEN segment_dossiers.content_hash = EXCLUDED.content_hash THEN segment_dossiers.embedding
                        ELSE NULL
                    END,
                    embedding_status = CASE
                        WHEN segment_dossiers.content_hash = EXCLUDED.content_hash THEN segment_dossiers.embedding_status
                        ELSE 'stale'
                    END,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = EXCLUDED.updated_at
                """,
                values,
            )
            connection.cursor().executemany(
                "INSERT INTO stage_dossier_topics(topic) VALUES (%s)",
                [(value[0],) for value in values],
            )
        deleted = connection.execute(
            """
            DELETE FROM segment_dossiers
            WHERE NOT EXISTS (
                SELECT 1 FROM stage_dossier_topics s WHERE s.topic = segment_dossiers.topic
            )
            """
        ).rowcount
        return len(values), deleted
