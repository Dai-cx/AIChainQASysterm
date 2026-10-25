"""Scoring and selecting claims for a question."""

from __future__ import annotations

import re
from typing import Any, Iterable

from aika.aika_core.text import shorten
from aika.domain_lexicon import THEME_SYNONYMS, expanded_terms, infer_themes, normalize_topic, text_matches_terms
from aika.research.claims import dedupe_strings, looks_like_low_quality_text, parse_companies, safe_float
from aika.research.constants import CLAIM_TYPE_BONUS, TECHNICAL_HIGH_SIGNAL_TERMS, TECHNICAL_REPORT_PREFIX


def score_claim(claim: dict[str, Any], question: str, topics: list[str], plan: Any) -> float:
    text = " ".join(str(claim.get(key, "")) for key in ("topic", "claim_type", "claim_text", "evidence_span", "section"))
    score = topic_match_score(text, question, topics)
    focus_terms = query_focus_terms(question)
    if focus_terms:
        focus_matches = sum(1 for term in focus_terms if text_matches_terms(text, [term]))
        if focus_matches:
            score += min(24.0, 12.0 * focus_matches)
            if str(claim.get("source_report_id", "")).startswith(TECHNICAL_REPORT_PREFIX):
                score += 3.0
        else:
            score -= 3.0
    claim_type = str(claim.get("claim_type", ""))
    score += CLAIM_TYPE_BONUS.get(claim_type, 0.8)
    if str(claim.get("source_tier", "")) == "1":
        score += 0.5
    score += safe_float(claim.get("confidence"), 0.7)
    level = str(claim.get("exposure_level", ""))
    if level == "core":
        score += 2.0
    elif level == "direct":
        score += 1.4
    elif level == "indirect":
        score += 0.4
    companies = parse_companies(claim.get("companies", []))
    plan_companies = set(getattr(plan, "companies", []) or [])
    if companies and plan_companies and plan_companies & set(companies):
        score += 2.5
    if companies and plan_companies and not (plan_companies & set(companies)) and getattr(plan, "answer_type", "") in {
        "company_compare",
        "risk_analysis",
        "company_profile",
    }:
        score -= 20.0
    answer_type = getattr(plan, "answer_type", "")
    if answer_type == "industry_bottleneck" and claim_type in {"bottleneck", "mechanism", "indicator"}:
        score += 2.0
    if answer_type == "topic_to_company" and claim_type == "company_exposure":
        score += 2.0
    if answer_type == "risk_analysis" and claim_type == "risk":
        score += 2.0
    if answer_type == "company_compare" and companies:
        score += 1.2
    if looks_like_low_quality_text(text):
        score -= 4.0
    return score


def topic_match_score(text: str, question: str, topics: list[str]) -> float:
    score = 0.0
    normalized = normalize_topic(text)
    q_norm = normalize_topic(question)
    for term in expanded_terms([*topics, question]):
        term_norm = normalize_topic(term)
        if not term_norm or len(term_norm) < 2:
            continue
        if term_norm in normalized:
            score += 1.4
        if term_norm in q_norm:
            score += 0.2
    return score


def query_focus_terms(question: str) -> list[str]:
    normalized_question = normalize_topic(question)
    terms = [
        term
        for term in TECHNICAL_HIGH_SIGNAL_TERMS
        if normalize_topic(term) and normalize_topic(term) in normalized_question
    ]
    terms.extend(
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+.\-_/]{2,}", question)
        if normalize_topic(token) not in {"what", "why", "how"}
    )
    return dedupe_strings(terms)


def query_topics(question: str, plan_topics: Iterable[str], expanded_plan_topics: Iterable[str]) -> list[str]:
    del expanded_plan_topics
    plan_topic_list = list(plan_topics)
    topics = [topic for topic in plan_topic_list if topic in THEME_SYNONYMS]
    topics.extend(infer_themes(question))
    if "国产" in question and "算力" in question:
        topics.append("国产算力")
    if not topics and "算力" in question:
        if any(term in question for term in ("瓶颈", "约束", "制约", "卡点", "最大")):
            topics.extend(["AI芯片", "算力网络", "液冷"])
        else:
            topics.extend(["AI服务器", "AI芯片", "算力网络"])
    result = []
    seen = set()
    for topic in topics:
        if topic and topic not in seen:
            seen.add(topic)
            result.append(topic)
        if len(result) >= 3 and not plan_topic_list:
            break
    return result


def should_use_dossier(question: str, plan: Any) -> bool:
    answer_type = getattr(plan, "answer_type", "")
    if answer_type in {"industry_bottleneck", "thematic_research", "topic_to_company"}:
        return True
    return any(term in question for term in ("为什么", "趋势", "瓶颈", "传导", "受益", "跟踪指标", "怎么看"))


def dossier_to_text(dossier: dict[str, Any]) -> str:
    lines = [str(dossier.get("summary", ""))]
    exposure = dossier.get("company_exposure", {}) or {}
    if exposure:
        exposure_text = []
        for level in ("core", "direct", "indirect", "mentioned"):
            names = exposure.get(level) or []
            if names:
                exposure_text.append(f"{level}:{'、'.join(names[:10])}")
        lines.append("公司敞口：" + "；".join(exposure_text))
    for label, key in (
        ("技术机理", "technology_mechanism"),
        ("瓶颈", "bottlenecks"),
        ("领先指标", "leading_indicators"),
        ("风险与反证", "risks"),
        ("证据缺口", "gaps"),
    ):
        values = dossier.get(key) or []
        if values:
            lines.append(f"{label}：" + "；".join(shorten(str(item), 120) for item in values[:4]))
    return "\n".join(line for line in lines if line.strip())
