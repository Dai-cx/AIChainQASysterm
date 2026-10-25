"""Building a claim from a relation or a piece of text: type, exposure, metric."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from aika.aika_core.text import shorten
from aika.domain_lexicon import (
    THEME_SYNONYMS,
    canonical_company_name,
    company_lookup,
    company_segment,
    infer_themes,
    normalize_topic,
)
from aika.extraction_schema import stable_id
from aika.frontend_data import RELATION_LABELS
from aika.research.constants import (
    DIRECT_METRIC_PATTERN,
    DIRECT_TOPIC_TERMS,
    EXPLICIT_BOTTLENECK_TERMS,
    TECHNICAL_INDICATOR_TERMS,
)


def claims_from_relation(row: dict[str, str]) -> list[dict[str, Any]]:
    relation = row.get("relation", "")
    if relation == "MENTIONED_IN" or not row.get("evidence"):
        return []
    topics = infer_relation_topics(row)
    if not topics:
        return []
    return [claim_from_relation_topic(row, topic) for topic in topics]


def infer_relation_topics(row: dict[str, str]) -> list[str]:
    text = relation_text(row)
    topics = infer_themes(text)
    if row.get("head_type") == "Company":
        topics.extend(infer_themes(company_segment(row.get("head_name", ""))))
    if row.get("tail_type") == "Company":
        topics.extend(infer_themes(company_segment(row.get("tail_name", ""))))
    if "国产" in text and ("算力" in text or "芯片" in text or "服务器" in text):
        topics.append("国产算力")
    deduped = []
    seen = set()
    for topic in topics:
        if topic in THEME_SYNONYMS and topic not in seen:
            seen.add(topic)
            deduped.append(topic)
    return deduped[:3]


def claim_from_relation_topic(row: dict[str, str], topic: str) -> dict[str, Any]:
    relation = row.get("relation", "")
    claim_type = infer_claim_type(row)
    companies = relation_companies(row)
    exposure_level = infer_exposure_level(row, topic) if companies else ""
    metric, value, unit = infer_metric_fields(row)
    direction = infer_direction(row)
    horizon = infer_horizon(row)
    evidence = clean_evidence(row.get("evidence", ""))
    mechanism = infer_mechanism(row, topic)
    claim_text = build_claim_text(row, topic, claim_type, exposure_level, evidence)
    claim_id = stable_id(
        "claim",
        claim_type,
        topic,
        row.get("head_type", ""),
        row.get("head_name", ""),
        relation,
        row.get("tail_type", ""),
        row.get("tail_name", ""),
        row.get("source_report_id", ""),
        evidence[:120],
    )
    return {
        "claim_id": claim_id,
        "claim_type": claim_type,
        "topic": topic,
        "claim_text": claim_text,
        "companies": companies,
        "mechanism": mechanism,
        "direction": direction,
        "horizon": horizon,
        "metric": metric,
        "value": value,
        "unit": unit,
        "source_report_id": row.get("source_report_id", ""),
        "source_title": row.get("source_title", ""),
        "page": row.get("page", ""),
        "section": row.get("section", ""),
        "source_tier": row.get("source_tier", ""),
        "evidence_span": evidence,
        "confidence": row.get("confidence", "0.70"),
        "as_of_date": infer_as_of_date(row),
        "exposure_level": exposure_level,
        "review_status": row.get("review_status", "auto") or "auto",
        "reviewer_note": "",
        "quality_flags": "",
        "conflict_group_id": "",
    }


def evidence_span_from_claim(claim: dict[str, Any]) -> dict[str, Any]:
    text = str(claim.get("evidence_span", ""))
    quality = "high" if len(text) >= 30 and not looks_like_low_quality_text(text) else "medium"
    return {
        "evidence_id": stable_id("evidence", claim["claim_id"], claim.get("source_report_id", ""), claim.get("page", "")),
        "claim_id": claim["claim_id"],
        "source_report_id": claim.get("source_report_id", ""),
        "source_title": claim.get("source_title", ""),
        "page": claim.get("page", ""),
        "section": claim.get("section", ""),
        "source_tier": claim.get("source_tier", ""),
        "text": text,
        "as_of_date": claim.get("as_of_date", ""),
        "quality": quality,
    }


def build_direct_claim_text(topic: str, claim_type: str, evidence: str, source_title: str = "") -> str:
    labels = {
        "mechanism": "技术机理",
        "bottleneck": "约束或瓶颈",
        "indicator": "可跟踪指标",
        "supply_chain": "产业传导",
        "risk": "风险或反证",
        "trend": "技术趋势",
    }
    label = labels.get(claim_type, "技术判断")
    prefix = f"{source_title}：" if source_title and source_title not in evidence else ""
    return f"{topic} 的{label}：{prefix}{evidence}"


def infer_direct_mechanism(topic: str, claim_type: str, evidence: str) -> str:
    if claim_type == "bottleneck":
        return f"{topic} 受 {shorten(evidence, 80)} 约束"
    if claim_type == "indicator":
        return f"{topic} 可通过 {shorten(evidence, 80)} 跟踪"
    if claim_type == "supply_chain":
        return f"{topic} 的产业链传导涉及 {shorten(evidence, 80)}"
    return f"{topic} 由 {shorten(evidence, 80)} 驱动"


def infer_direct_metric_fields(evidence: str) -> tuple[str, str, str]:
    metric = ""
    value = ""
    unit = ""
    metric_terms = (
        "GPU hours",
        "tokens",
        "parameters",
        "throughput",
        "latency",
        "bandwidth",
        "time-to-train",
        "power density",
        "GPU小时",
        "吞吐",
        "时延",
        "带宽",
    )
    for term in metric_terms:
        if term.lower() in evidence.lower():
            metric = term
            break
    match = DIRECT_METRIC_PATTERN.search(evidence)
    if match:
        value = match.group(1).replace(",", "").strip()
        unit_match = re.search(r"(GPU hours|tokens|parameters|GB/s|Tb/s|GT/s|W|kW|MW|PUE|ms|us|ns|%)$", value, flags=re.I)
        if unit_match:
            unit = unit_match.group(1)
    return metric, value, unit


def has_direct_metric(evidence: str) -> bool:
    if DIRECT_METRIC_PATTERN.search(evidence):
        return True
    return bool(re.search(r"\d", evidence) and count_matching_terms(evidence, TECHNICAL_INDICATOR_TERMS))


def infer_direct_horizon(evidence: str) -> str:
    text = evidence.lower()
    if any(term in text for term in ("2030", "long term", "roadmap", "future generation", "未来")):
        return "long_term"
    if any(term in text for term in ("2027", "2028", "next generation", "中期", "逐步")):
        return "mid_term"
    if any(term in text for term in ("2024", "2025", "2026", "current", "rev 1.0", "当前")):
        return "near_term"
    return ""


def infer_direct_as_of_date(chunk: dict[str, Any], evidence: str) -> str:
    text = " ".join(str(chunk.get(key, "") or "") for key in ("year", "source_title", "report_id"))
    match = re.search(r"(20\d{2})", f"{text} {evidence}")
    return match.group(1) if match else ""


def companies_explicitly_in_text(text: str) -> list[str]:
    lookup = company_lookup()
    normalized = normalize_topic(text)
    companies: list[str] = []
    for company, aliases in lookup.aliases_by_company.items():
        if any(normalize_topic(alias) in normalized for alias in aliases):
            companies.append(company)
    return companies


def count_matching_terms(text: str, terms: Iterable[str]) -> int:
    normalized = normalize_topic(text)
    return sum(1 for term in terms if normalize_topic(term) in normalized)


def dedupe_strings(values: Iterable[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        key = str(value).casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(str(value))
    return result


def normalize_claim_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    updated["companies"] = parse_companies(updated.get("companies", []))
    return updated


def relation_text(row: dict[str, str]) -> str:
    return " ".join(str(row.get(key, "") or "") for key in ("head_name", "tail_name", "relation", "evidence", "section"))


def relation_companies(row: dict[str, str]) -> list[str]:
    companies = []
    if row.get("head_type") == "Company":
        companies.append(canonical_company_name(row.get("head_name", "")))
    if row.get("tail_type") == "Company":
        companies.append(canonical_company_name(row.get("tail_name", "")))
    return [company for index, company in enumerate(companies) if company and company not in companies[:index]]


def infer_claim_type(row: dict[str, str]) -> str:
    relation = row.get("relation", "")
    text = relation_text(row)
    if relation == "DISCLOSES_RISK":
        return "risk"
    if relation == "HAS_METRIC" or any(term in text for term in ("订单", "毛利率", "营收", "收入", "产能", "PUE", "市场份额", "渗透率")):
        return "indicator"
    if relation == "CONSTRAINS" or any(term in text for term in EXPLICIT_BOTTLENECK_TERMS):
        return "bottleneck"
    if relation in {"HAS_PRODUCT", "USES_TECHNOLOGY", "BELONGS_TO_CHAIN", "HAS_EXPOSURE"} and row.get("head_type") == "Company":
        return "company_exposure"
    if relation in {"UPSTREAM_OF", "DOWNSTREAM_OF", "DEPENDS_ON"}:
        return "supply_chain"
    if relation in {"ENABLES", "DRIVES", "RELIEVES", "BENEFITS_FROM"}:
        return "mechanism"
    if relation == "SUPPORTED_BY_POLICY":
        return "policy"
    return "trend"


def infer_exposure_level(row: dict[str, str], topic: str) -> str:
    if row.get("head_type") != "Company":
        return ""
    relation = row.get("relation", "")
    company = row.get("head_name", "")
    segment_norm = normalize_topic(company_segment(company))
    topic_norm = normalize_topic(topic)
    tail_norm = normalize_topic(row.get("tail_name", ""))
    evidence_norm = normalize_topic(row.get("evidence", ""))
    direct_terms = DIRECT_TOPIC_TERMS.get(topic, tuple(normalize_topic(term) for term in THEME_SYNONYMS.get(topic, (topic,))))
    direct_match = any(normalize_topic(term) in tail_norm for term in direct_terms)
    segment_match = topic_norm in segment_norm or any(normalize_topic(term) in segment_norm for term in direct_terms)
    if segment_match:
        return "core"
    if topic == "液冷":
        if any(term in segment_norm for term in ("散热", "热管理", "温控")):
            return "direct"
        if direct_match or topic_norm in evidence_norm:
            return "indirect"
    if relation in {"HAS_PRODUCT", "USES_TECHNOLOGY", "HAS_EXPOSURE"} and direct_match:
        return "direct"
    if topic_norm in evidence_norm or any(normalize_topic(term) in evidence_norm for term in direct_terms):
        return "indirect"
    return "mentioned"


def infer_metric_fields(row: dict[str, str]) -> tuple[str, str, str]:
    text = f"{row.get('tail_name', '')} {row.get('evidence', '')}"
    metric = row.get("tail_name", "") if row.get("tail_type") in {"Metric", "LeadingIndicator"} else ""
    value = ""
    unit = ""
    match = re.search(r"([-+]?\d+(?:,\d{3})*(?:\.\d+)?)(\s*(?:%|亿元|万元|元|亿美元|万台|台|个|EFLOPS|PFLOPS|TFLOPS|kW|KW|MW|GW|PUE)?)", text, flags=re.I)
    if match:
        value = match.group(1).replace(",", "")
        unit = match.group(2).strip()
    return metric, value, unit


def infer_direction(row: dict[str, str]) -> str:
    relation = row.get("relation", "")
    if relation in {"CONSTRAINS", "DISCLOSES_RISK"}:
        return "negative"
    if relation in {"ENABLES", "DRIVES", "RELIEVES", "BENEFITS_FROM", "SUPPORTED_BY_POLICY"}:
        return "positive"
    return "neutral"


def infer_horizon(row: dict[str, str]) -> str:
    text = relation_text(row)
    if any(term in text for term in ("长期", "2030", "未来五年", "远期")):
        return "long_term"
    if any(term in text for term in ("2027", "2028", "中期", "逐步")):
        return "mid_term"
    if any(term in text for term in ("当前", "报告期", "2025", "2026", "短期")):
        return "near_term"
    return ""


def infer_mechanism(row: dict[str, str], topic: str) -> str:
    relation = row.get("relation", "")
    label = RELATION_LABELS.get(relation, relation)
    head = row.get("head_name", "")
    tail = row.get("tail_name", "")
    if relation in {"ENABLES", "DRIVES", "RELIEVES", "CONSTRAINS", "DEPENDS_ON", "UPSTREAM_OF", "DOWNSTREAM_OF"}:
        return f"{head} {label} {tail}".strip()
    if row.get("head_type") == "Company":
        return f"{head} 在 {topic} 的关系为{label}{tail}".strip()
    return f"{topic}：{label}{tail}".strip()


def build_claim_text(
    row: dict[str, str],
    topic: str,
    claim_type: str,
    exposure_level: str,
    evidence: str,
) -> str:
    head = row.get("head_name", "")
    tail = row.get("tail_name", "")
    relation_label = RELATION_LABELS.get(row.get("relation", ""), row.get("relation", ""))
    if claim_type == "company_exposure":
        return f"{head} 对 {topic} 的公司敞口为 {exposure_level or 'mentioned'}：{relation_label}{tail}。证据：{evidence}"
    if claim_type == "risk":
        return f"{head} 在 {topic} 相关业务中的风险：{tail}。证据：{evidence}"
    if claim_type == "indicator":
        return f"{topic} 的可跟踪指标：{head}{relation_label}{tail}。证据：{evidence}"
    if claim_type == "bottleneck":
        return f"{topic} 的约束或瓶颈：{head}{relation_label}{tail}。证据：{evidence}"
    return f"{topic} 机理/传导：{head}{relation_label}{tail}。证据：{evidence}"


def infer_as_of_date(row: dict[str, str]) -> str:
    text = " ".join(str(row.get(key, "") or "") for key in ("source_title", "source_report_id", "evidence"))
    match = re.search(r"(20\d{2})", text)
    return match.group(1) if match else ""


def clean_evidence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:500]


def looks_like_low_quality_text(text: str) -> bool:
    value = str(text or "")
    if "免责声明" in value or "请务必" in value:
        return True
    upper = value.upper()
    if any(term in upper for term in ("LEGAL NOTICE", "ALL RIGHTS RESERVED", "MERCHANTABILITY", "TRADEMARK")):
        return True
    if re.fullmatch(r"[\d\s,.%％+\-—/]+", value.strip()):
        return True
    return False


def parse_companies(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
            items = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            items = []
    elif isinstance(value, str) and value.strip():
        items = [value]
    else:
        items = []
    result = []
    for item in items:
        company = canonical_company_name(str(item))
        if company and company not in result:
            result.append(company)
    return result


def first_company(value: Any) -> str:
    companies = parse_companies(value)
    return companies[0] if companies else ""


def claim_title(claim: dict[str, Any]) -> str:
    company = first_company(claim.get("companies", []))
    topic = str(claim.get("topic", ""))
    claim_type = str(claim.get("claim_type", ""))
    if company:
        return f"{company} {topic} {claim_type}".strip()
    return f"{topic} {claim_type}".strip()


def safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
