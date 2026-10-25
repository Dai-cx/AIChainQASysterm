"""Backwards-compatible import surface for the curated research claims.

The implementation moved into :mod:ika.research; this module stays so the engines,
the MCP tools, the scripts and the tests keep their existing imports.
"""

from __future__ import annotations

from aika.research import (  # noqa: F401
    ROOT_DIR, DEFAULT_RESEARCH_DIR, CLAIMS_FILE, EVIDENCE_SPANS_FILE, SEGMENT_DOSSIERS_FILE, CLAIM_REVIEWS_FILE, CLAIM_CSV_FIELDS, REVIEWABLE_CLAIM_FIELDS, CLAIM_REVIEW_STATUSES, EVIDENCE_SPAN_FIELDS, EXPOSURE_ORDER, CLAIM_TYPE_BONUS, EXPLICIT_BOTTLENECK_TERMS, DIRECT_TOPIC_TERMS, TECHNICAL_REPORT_PREFIX, MAX_DIRECT_CLAIMS_PER_REPORT, TECHNICAL_HIGH_SIGNAL_TERMS, TECHNICAL_LOW_VALUE_TERMS, TECHNICAL_MECHANISM_TERMS, TECHNICAL_BOTTLENECK_TERMS, TECHNICAL_INDICATOR_TERMS, DIRECT_METRIC_PATTERN,
    ResearchHit, dedupe_research_hits, diversify_research_hits, sorted_claims, top_claim_texts,
    claims_from_relation, infer_relation_topics, claim_from_relation_topic, evidence_span_from_claim, build_direct_claim_text, infer_direct_mechanism, infer_direct_metric_fields, has_direct_metric, infer_direct_horizon, infer_direct_as_of_date, companies_explicitly_in_text, count_matching_terms, dedupe_strings, normalize_claim_row, relation_text, relation_companies, infer_claim_type, infer_exposure_level, infer_metric_fields, infer_direction, infer_horizon, infer_mechanism, build_claim_text, infer_as_of_date, clean_evidence, looks_like_low_quality_text, parse_companies, first_company, claim_title, safe_float,
    claims_from_technical_chunks, is_professional_technical_chunk, looks_like_low_value_technical_chunk, select_technical_evidence, split_evidence_candidates, looks_like_reference_candidate, infer_technical_topics, technical_topic_supported, infer_technical_claim_types, technical_claim_from_chunk,
    build_segment_dossiers, best_company_exposure, infer_dossier_gaps, build_dossier_summary,
    load_claim_reviews, write_claim_review, normalize_claim_review, apply_claim_reviews,
    score_claim, topic_match_score, query_focus_terms, query_topics, should_use_dossier, dossier_to_text,
    build_research_artifacts, write_csv, serialize_cell,
    ResearchMemory,
)
