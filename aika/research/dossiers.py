"""Segment dossiers: grouping claims by industry segment and summarising gaps."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from aika.aika_core.text import shorten
from aika.domain_lexicon import company_segment
from aika.research.claims import parse_companies
from aika.research.constants import EXPOSURE_ORDER
from aika.research.hits import sorted_claims, top_claim_texts


def build_segment_dossiers(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        grouped[str(claim.get("topic", ""))].append(claim)

    dossiers: list[dict[str, Any]] = []
    built_at = datetime.now(timezone.utc).isoformat()
    for topic, rows in sorted(grouped.items()):
        if not topic:
            continue
        exposure = best_company_exposure(rows)
        mechanisms = top_claim_texts(rows, {"mechanism", "trend", "supply_chain"}, 5)
        bottlenecks = top_claim_texts(rows, {"bottleneck"}, 5)
        indicators = top_claim_texts(rows, {"indicator"}, 5)
        risks = top_claim_texts(rows, {"risk"}, 5)
        policies = top_claim_texts(rows, {"policy"}, 3)
        gaps = infer_dossier_gaps(topic, exposure, indicators, risks)
        dossier = {
            "topic": topic,
            "built_at": built_at,
            "summary": build_dossier_summary(topic, exposure, mechanisms, bottlenecks, indicators, risks),
            "technology_mechanism": mechanisms,
            "industry_chain": sorted({claim.get("mechanism", "") for claim in rows if claim.get("claim_type") == "supply_chain" and claim.get("mechanism")})[:8],
            "company_exposure": exposure,
            "leading_indicators": indicators,
            "bottlenecks": bottlenecks,
            "risks": risks,
            "policies": policies,
            "evidence_ids": [claim["claim_id"] for claim in sorted_claims(rows)[:20]],
            "gaps": gaps,
            "conflicts": [],
        }
        dossiers.append(dossier)
    return dossiers


def best_company_exposure(claims: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_company: dict[str, tuple[int, str]] = {}
    for claim in claims:
        if claim.get("claim_type") != "company_exposure":
            continue
        level = str(claim.get("exposure_level", "mentioned"))
        for company in parse_companies(claim.get("companies", [])):
            current = by_company.get(company)
            rank = EXPOSURE_ORDER.get(level, 4)
            if current is None or rank < current[0]:
                by_company[company] = (rank, level)
    grouped: dict[str, list[str]] = {"core": [], "direct": [], "indirect": [], "mentioned": []}
    for company, (_, level) in sorted(by_company.items(), key=lambda item: (item[1][0], company_segment(item[0]), item[0])):
        grouped.setdefault(level, []).append(company)
    return {level: names for level, names in grouped.items() if names}


def infer_dossier_gaps(
    topic: str,
    exposure: dict[str, list[str]],
    indicators: list[str],
    risks: list[str],
) -> list[str]:
    gaps = []
    if not exposure.get("core") and not exposure.get("direct"):
        gaps.append(f"{topic} 缺少可稳定排序的直接公司敞口证据。")
    if not indicators:
        gaps.append(f"{topic} 缺少订单、收入、毛利率、产能或渗透率等领先指标证据。")
    if not risks:
        gaps.append(f"{topic} 缺少明确风险或反证证据。")
    return gaps


def build_dossier_summary(
    topic: str,
    exposure: dict[str, list[str]],
    mechanisms: list[str],
    bottlenecks: list[str],
    indicators: list[str],
    risks: list[str],
) -> str:
    direct = exposure.get("core") or exposure.get("direct") or []
    parts = [f"{topic}："]
    if mechanisms:
        parts.append(f"技术机理集中在{shorten(mechanisms[0], 80)}")
    if bottlenecks:
        parts.append(f"主要瓶颈包括{shorten(bottlenecks[0], 80)}")
    if direct:
        parts.append(f"直接敞口公司包括{'、'.join(direct[:8])}")
    if indicators:
        parts.append(f"可跟踪指标包括{shorten(indicators[0], 70)}")
    if risks:
        parts.append(f"主要风险包括{shorten(risks[0], 70)}")
    return "；".join(parts)
