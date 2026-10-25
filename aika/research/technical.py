"""Turning technical report chunks into claims."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from aika.domain_lexicon import TECHNICAL_SOURCE_TYPES, THEME_SYNONYMS, infer_themes, normalize_topic
from aika.extraction_schema import load_jsonl, stable_id
from aika.research.claims import (
    build_direct_claim_text,
    clean_evidence,
    companies_explicitly_in_text,
    count_matching_terms,
    dedupe_strings,
    has_direct_metric,
    infer_direct_as_of_date,
    infer_direct_horizon,
    infer_direct_mechanism,
    infer_direct_metric_fields,
    looks_like_low_quality_text,
)
from aika.research.constants import (
    MAX_DIRECT_CLAIMS_PER_REPORT,
    TECHNICAL_BOTTLENECK_TERMS,
    TECHNICAL_HIGH_SIGNAL_TERMS,
    TECHNICAL_INDICATOR_TERMS,
    TECHNICAL_LOW_VALUE_TERMS,
    TECHNICAL_MECHANISM_TERMS,
    TECHNICAL_REPORT_PREFIX,
)


def claims_from_technical_chunks(chunks_dir: Path) -> list[dict[str, Any]]:
    """Derive original-text claims from professional technical source chunks."""
    claims: list[dict[str, Any]] = []
    report_counts: dict[str, int] = defaultdict(int)
    if not chunks_dir.exists():
        return claims
    for path in sorted(chunks_dir.glob(f"{TECHNICAL_REPORT_PREFIX}*.jsonl")):
        for chunk in load_jsonl(path):
            report_id = str(chunk.get("report_id", ""))
            if report_counts[report_id] >= MAX_DIRECT_CLAIMS_PER_REPORT:
                continue
            if not is_professional_technical_chunk(chunk):
                continue
            if looks_like_low_value_technical_chunk(chunk):
                continue
            evidence = select_technical_evidence(chunk)
            if not evidence:
                continue
            topics = infer_technical_topics(chunk, evidence)
            if not topics:
                continue
            claim_types = infer_technical_claim_types(evidence)
            companies = companies_explicitly_in_text(evidence)
            for topic in topics[:2]:
                for claim_type in claim_types[:2]:
                    claims.append(technical_claim_from_chunk(chunk, topic, claim_type, evidence, companies))
                    report_counts[report_id] += 1
                    if report_counts[report_id] >= MAX_DIRECT_CLAIMS_PER_REPORT:
                        break
                if report_counts[report_id] >= MAX_DIRECT_CLAIMS_PER_REPORT:
                    break
    return claims


def is_professional_technical_chunk(chunk: dict[str, Any]) -> bool:
    report_id = str(chunk.get("report_id", ""))
    source_type = str(chunk.get("source_type", ""))
    return report_id.startswith(TECHNICAL_REPORT_PREFIX) or source_type in TECHNICAL_SOURCE_TYPES


def looks_like_low_value_technical_chunk(chunk: dict[str, Any]) -> bool:
    text = re.sub(r"\s+", " ", str(chunk.get("text", "") or "")).strip()
    if len(text) < 80:
        return True
    upper = text.upper()
    if any(term in upper for term in TECHNICAL_LOW_VALUE_TERMS):
        signal_terms = count_matching_terms(text, TECHNICAL_HIGH_SIGNAL_TERMS)
        if signal_terms <= 1:
            return True
    section = normalize_topic(chunk.get("section", ""))
    if section in {"contents", "目录"}:
        return True
    if text.count(". . .") >= 4 or text.count(" . . ") >= 8:
        return True
    if looks_like_low_quality_text(text):
        return True
    return count_matching_terms(text, TECHNICAL_HIGH_SIGNAL_TERMS) == 0


def select_technical_evidence(chunk: dict[str, Any]) -> str:
    text = re.sub(r"\s+", " ", str(chunk.get("text", "") or "")).strip()
    candidates = split_evidence_candidates(text)
    if not candidates:
        return ""
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        if len(candidate) < 35 or looks_like_low_quality_text(candidate):
            continue
        if any(term in candidate.upper() for term in TECHNICAL_LOW_VALUE_TERMS):
            continue
        if looks_like_reference_candidate(candidate):
            continue
        signal = count_matching_terms(candidate, TECHNICAL_HIGH_SIGNAL_TERMS)
        if not signal:
            continue
        score = signal * 4
        score += count_matching_terms(candidate, TECHNICAL_MECHANISM_TERMS)
        score += count_matching_terms(candidate, TECHNICAL_BOTTLENECK_TERMS)
        score += count_matching_terms(candidate, TECHNICAL_INDICATOR_TERMS)
        if re.search(r"\d", candidate):
            score += 2
        scored.append((score, candidate))
    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return clean_evidence(scored[0][1])


def split_evidence_candidates(text: str) -> list[str]:
    rough_parts = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    candidates: list[str] = []
    for part in rough_parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" -•\t")
        if not cleaned:
            continue
        if len(cleaned) > 650:
            chunks = re.split(r";\s+|；|,\s+(?=[A-Z])", cleaned)
            candidates.extend(item.strip(" -•\t") for item in chunks if item.strip())
        else:
            candidates.append(cleaned)
    return candidates


def looks_like_reference_candidate(text: str) -> bool:
    value = str(text or "")
    if re.search(r"\bpp\.\s*\d", value, flags=re.I):
        return True
    if re.search(r"\b(?:Proceedings|Conference|SIGCOMM|arXiv preprint)\b", value, flags=re.I):
        return True
    if re.search(r"^[A-Z][A-Za-z\-]+,\s+\".+\"", value):
        return True
    if value.count(" et al.") >= 1 and re.search(r"\b20\d{2}\b", value):
        return True
    return False


def infer_technical_topics(chunk: dict[str, Any], evidence: str) -> list[str]:
    text = " ".join(
        str(chunk.get(key, "") or "") for key in ("source_title", "source_type", "section", "context")
    )
    raw_text = f"{text} {evidence}"
    topics = infer_themes(raw_text)
    normalized = normalize_topic(raw_text)
    if "ucie" in normalized or "chiplet" in normalized or "advancedpackaging" in normalized:
        topics.append("AI芯片")
    if "ualink" in normalized or "ultraethernet" in normalized or "uet" in normalized:
        topics.append("算力网络")
    if "flashattention" in normalized or "pagedattention" in normalized or "fp8" in normalized:
        topics.append("AI芯片")
    if "liquidcooling" in normalized or "coldplate" in normalized or "thermalmanagement" in normalized:
        topics.append("液冷")
    if "siliconphotonics" in normalized or "integratedphotonics" in normalized or "opticalengine" in normalized:
        topics.append("光模块")
    deduped: list[str] = []
    for topic in topics:
        if topic in THEME_SYNONYMS and topic not in deduped and technical_topic_supported(topic, raw_text, normalized):
            deduped.append(topic)
    return deduped


def technical_topic_supported(topic: str, raw_text: str, normalized_text: str) -> bool:
    if topic == "光模块":
        return any(
            term in normalized_text
            for term in (
                "光模块",
                "高速光模块",
                "硅光",
                "光器件",
                "光引擎",
                "siliconphotonics",
                "integratedphotonics",
                "opticalengine",
                "co-packagedoptics",
            )
        ) or bool(re.search(r"\b(?:CPO|LPO|NPO)\b", raw_text, flags=re.I))
    if topic == "液冷":
        return any(
            term in normalized_text
            for term in (
                "液冷",
                "冷板",
                "温控",
                "热管理",
                "coldplate",
                "liquidcooling",
                "thermalmanagement",
                "powerdensity",
                "heat",
                "thermal",
            )
        ) or bool(re.search(r"\bCDU\b", raw_text, flags=re.I))
    if topic == "电源":
        return any(term in normalized_text for term in ("电源", "ups", "powerdelivery", "powersupply"))
    return True


def infer_technical_claim_types(evidence: str) -> list[str]:
    claim_types: list[str] = []
    if count_matching_terms(evidence, TECHNICAL_BOTTLENECK_TERMS):
        claim_types.append("bottleneck")
    if has_direct_metric(evidence):
        claim_types.append("indicator")
    if any(term in normalize_topic(evidence) for term in ("upstream", "downstream", "supplychain", "packaging", "interconnect", "fabric", "cluster")):
        claim_types.append("supply_chain")
    if count_matching_terms(evidence, TECHNICAL_MECHANISM_TERMS):
        claim_types.append("mechanism")
    if not claim_types:
        claim_types.append("trend")
    return dedupe_strings(claim_types)


def technical_claim_from_chunk(
    chunk: dict[str, Any],
    topic: str,
    claim_type: str,
    evidence: str,
    companies: list[str],
) -> dict[str, Any]:
    metric, value, unit = infer_direct_metric_fields(evidence) if claim_type == "indicator" else ("", "", "")
    source_report_id = str(chunk.get("report_id", ""))
    claim_id = stable_id(
        "claim",
        "direct_technical",
        claim_type,
        topic,
        source_report_id,
        chunk.get("chunk_id", ""),
        evidence[:160],
    )
    mechanism = infer_direct_mechanism(topic, claim_type, evidence)
    return {
        "claim_id": claim_id,
        "claim_type": claim_type,
        "topic": topic,
        "claim_text": build_direct_claim_text(topic, claim_type, evidence, str(chunk.get("source_title", ""))),
        "companies": companies,
        "mechanism": mechanism,
        "direction": "negative" if claim_type in {"bottleneck", "risk"} else "positive" if claim_type == "mechanism" else "neutral",
        "horizon": infer_direct_horizon(evidence),
        "metric": metric,
        "value": value,
        "unit": unit,
        "source_report_id": source_report_id,
        "source_title": str(chunk.get("source_title", "")),
        "page": str(chunk.get("page", "")),
        "section": str(chunk.get("section", "")),
        "source_tier": str(chunk.get("source_tier", "")),
        "evidence_span": evidence,
        "confidence": "0.78" if chunk.get("source_tier") == "1" else "0.70",
        "as_of_date": infer_direct_as_of_date(chunk, evidence),
        "exposure_level": "mentioned" if companies else "",
        "review_status": "auto",
        "reviewer_note": "",
        "quality_flags": "",
        "conflict_group_id": "",
    }
