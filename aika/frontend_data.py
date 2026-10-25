"""Data access and graph helpers shared by the API and React frontend."""

from __future__ import annotations

import html
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aika.aika_core.io import read_csv_rows as io_read_csv_rows

from aika.extraction_schema import normalize_name


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENTITIES_CSV = ROOT_DIR / "data" / "verified" / "entities.csv"
DEFAULT_RELATIONS_CSV = ROOT_DIR / "data" / "verified" / "relations.csv"

RELATION_LABELS = {
    "USES_TECHNOLOGY": "涉及技术",
    "HAS_PRODUCT": "拥有产品",
    "BELONGS_TO_CHAIN": "属于环节",
    "HAS_METRIC": "披露指标",
    "DISCLOSES_RISK": "披露风险",
    "MENTIONED_IN": "来源报告",
    "UPSTREAM_OF": "上游",
    "DOWNSTREAM_OF": "下游",
    "ENABLES": "使能",
    "CONSTRAINS": "约束",
    "DEFINES": "定义",
    "SUPPORTED_BY_POLICY": "政策支撑",
    "DRIVES": "驱动",
    "DEPENDS_ON": "依赖",
    "RELIEVES": "缓解",
    "HAS_EXPOSURE": "具有敞口",
    "HAS_INDICATOR": "跟踪指标",
    "BENEFITS_FROM": "受益于",
}

QUESTION_RELATIONS = {
    "技术": "USES_TECHNOLOGY",
    "产品": "HAS_PRODUCT",
    "产业链": "BELONGS_TO_CHAIN",
    "环节": "BELONGS_TO_CHAIN",
    "指标": "HAS_METRIC",
    "财务": "HAS_METRIC",
    "风险": "DISCLOSES_RISK",
    "政策": "SUPPORTED_BY_POLICY",
    "定义": "DEFINES",
    "上游": "UPSTREAM_OF",
    "下游": "DOWNSTREAM_OF",
}

ENTITY_ORDER = [
    "Company",
    "IndustryChain",
    "ValueChainSegment",
    "IndustryConcept",
    "Technology",
    "Product",
    "Metric",
    "Risk",
    "Workload",
    "Architecture",
    "Bottleneck",
    "LeadingIndicator",
    "DemandDriver",
    "SupplyConstraint",
    "CompanyExposure",
    "Policy",
    "Standard",
    "Report",
]

ENTITY_COLORS = {
    "Company": "#1f6f70",
    "Technology": "#2563eb",
    "Product": "#7a4cc2",
    "IndustryChain": "#b86519",
    "ValueChainSegment": "#c2410c",
    "IndustryConcept": "#0e7490",
    "Metric": "#477148",
    "Risk": "#c43c39",
    "Workload": "#0369a1",
    "Architecture": "#4f46e5",
    "Bottleneck": "#b91c1c",
    "LeadingIndicator": "#15803d",
    "DemandDriver": "#a16207",
    "SupplyConstraint": "#be123c",
    "CompanyExposure": "#0f766e",
    "Policy": "#4f5f9f",
    "Standard": "#8a4f9f",
    "Report": "#64748b",
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    return io_read_csv_rows(path, missing_ok=True)


def contains_name(value: str, query: str) -> bool:
    value_norm = normalize_name(value)
    query_norm = normalize_name(query)
    return bool(query_norm and (query_norm in value_norm or value_norm in query_norm))


def unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value}, key=lambda item: (len(item), item))


@dataclass
class LocalKnowledgeGraph:
    entities: list[dict[str, str]]
    relations: list[dict[str, str]]
    _relations_by_company: dict[str, list[dict[str, str]]] = field(init=False, repr=False)
    _relations_by_relation: dict[str, list[dict[str, str]]] = field(init=False, repr=False)
    _relations_by_relation_company: dict[tuple[str, str], list[dict[str, str]]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        by_company: dict[str, list[dict[str, str]]] = defaultdict(list)
        by_relation: dict[str, list[dict[str, str]]] = defaultdict(list)
        by_relation_company: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in self.relations:
            company = row.get("head_name", "")
            relation = row.get("relation", "")
            if company:
                by_company[company].append(row)
            if relation:
                by_relation[relation].append(row)
            if company and relation:
                by_relation_company[(relation, company)].append(row)
        self._relations_by_company = dict(by_company)
        self._relations_by_relation = dict(by_relation)
        self._relations_by_relation_company = dict(by_relation_company)

    @classmethod
    def from_csvs(
        cls,
        entities_csv: Path = DEFAULT_ENTITIES_CSV,
        relations_csv: Path = DEFAULT_RELATIONS_CSV,
    ) -> "LocalKnowledgeGraph":
        return cls(read_csv_rows(entities_csv), read_csv_rows(relations_csv))

    @classmethod
    def from_dir(cls, data_dir: Path) -> "LocalKnowledgeGraph":
        return cls.from_csvs(data_dir / "entities.csv", data_dir / "relations.csv")

    def entity_counts(self) -> Counter:
        return Counter(row["type"] for row in self.entities)

    def relation_counts(self) -> Counter:
        return Counter(row["relation"] for row in self.relations)

    def names_by_type(self, entity_type: str) -> list[str]:
        return unique_sorted([row["name"] for row in self.entities if row["type"] == entity_type])

    def reports_count(self) -> int:
        return sum(1 for row in self.entities if row["type"] == "Report")

    def subgraph_relations(
        self,
        *,
        company: str = "",
        technology: str = "",
        relation_type: str = "",
        limit: int = 80,
    ) -> list[dict[str, str]]:
        rows = self.relations
        if relation_type:
            rows = [row for row in rows if row["relation"] == relation_type]
        if company:
            rows = [row for row in rows if row["head_type"] == "Company" and contains_name(row["head_name"], company)]
        if technology:
            rows = [
                row
                for row in rows
                if row["tail_type"] == "Technology" and contains_name(row["tail_name"], technology)
            ]
        return rows[:limit]

    def relation_candidates(
        self,
        *,
        companies: list[str] | set[str] | tuple[str, ...] | None = None,
        relations: list[str] | set[str] | tuple[str, ...] | None = None,
        head_type: str = "",
        exclude_relations: set[str] | None = None,
    ) -> list[dict[str, str]]:
        company_values = [company for company in (companies or []) if company]
        relation_values = [relation for relation in (relations or []) if relation]
        if company_values and relation_values:
            rows = [
                row
                for relation in relation_values
                for company in company_values
                for row in self._relations_by_relation_company.get((relation, company), [])
            ]
        elif company_values:
            rows = [row for company in company_values for row in self._relations_by_company.get(company, [])]
        elif relation_values:
            rows = [row for relation in relation_values for row in self._relations_by_relation.get(relation, [])]
        else:
            rows = self.relations
        if head_type:
            rows = [row for row in rows if row.get("head_type") == head_type]
        if exclude_relations:
            rows = [row for row in rows if row.get("relation") not in exclude_relations]
        return rows

    def companies_for_technology(self, technology: str) -> list[dict[str, str]]:
        return [
            row
            for row in self.relations
            if row["relation"] == "USES_TECHNOLOGY"
            and row["head_type"] == "Company"
            and row["tail_type"] == "Technology"
            and contains_name(row["tail_name"], technology)
        ]

    def companies_for_topic(self, topic: str) -> list[dict[str, str]]:
        topic = topic.strip()
        if not topic:
            return []
        return [
            row
            for row in self.relations
            if row["head_type"] == "Company"
            and row["relation"] != "MENTIONED_IN"
            and (
                topic in row.get("tail_name", "")
                or topic in row.get("evidence", "")
                or topic in row.get("section", "")
            )
        ]

    def company_relations(self, company: str, relation_type: str) -> list[dict[str, str]]:
        return [
            row
            for row in self.relations
            if row["relation"] == relation_type
            and row["head_type"] == "Company"
            and contains_name(row["head_name"], company)
        ]


def infer_question(graph: LocalKnowledgeGraph, question: str) -> dict[str, Any]:
    question = question.strip()
    companies = graph.names_by_type("Company")
    technologies = graph.names_by_type("Technology")

    matched_company = next((name for name in companies if name and name in question), "")
    matched_technology = next((name for name in technologies if name and name in question), "")

    topic = extract_company_topic(question)
    if ("哪些公司" in question or "公司" in question) and topic:
        cypher = (
            "MATCH (c:Company)-[r]->(x) "
            f'WHERE type(r) <> "MENTIONED_IN" AND (x.name CONTAINS "{topic}" OR r.evidence CONTAINS "{topic}") '
            "RETURN c.name AS company, type(r) AS relation, x.name AS target, "
            "r.evidence AS evidence, r.source_title AS source, r.page AS page"
        )
        records = graph.companies_for_topic(topic)
        return build_answer(question, "topic_to_company", cypher, records)

    if ("哪些公司" in question or "公司" in question) and matched_technology:
        cypher = (
            f'MATCH (c:Company)-[r:USES_TECHNOLOGY]->(t:Technology {{name: "{matched_technology}"}}) '
            "RETURN c.name AS company, t.name AS technology, r.evidence AS evidence, "
            "r.source_title AS source, r.page AS page"
        )
        records = graph.companies_for_technology(matched_technology)
        return build_answer(question, "topic_to_company", cypher, records)

    if matched_company:
        relation_type = "USES_TECHNOLOGY"
        for keyword, candidate in QUESTION_RELATIONS.items():
            if keyword in question:
                relation_type = candidate
                break
        tail_label = relation_type_tail_label(relation_type)
        cypher = (
            f'MATCH (c:Company {{name: "{matched_company}"}})-[r:{relation_type}]->(x:{tail_label}) '
            "RETURN c.name AS company, x.name AS target, r.evidence AS evidence, "
            "r.source_title AS source, r.page AS page"
        )
        records = graph.company_relations(matched_company, relation_type)
        return build_answer(question, "company_to_relation", cypher, records)

    cypher = (
        "MATCH (c:Company)-[r]->(x) "
        "RETURN c.name AS company, type(r) AS relation, x.name AS target, "
        "r.evidence AS evidence, r.source_title AS source, r.page AS page LIMIT 20"
    )
    records = [
        row
        for row in graph.relations
        if row["head_type"] == "Company" and question and any(token in row["evidence"] for token in question[:12])
    ][:20]
    return build_answer(question, "fallback_keyword", cypher, records)


def relation_type_tail_label(relation_type: str) -> str:
    return {
        "USES_TECHNOLOGY": "Technology",
        "HAS_PRODUCT": "Product",
        "BELONGS_TO_CHAIN": "IndustryChain",
        "HAS_METRIC": "Metric",
        "DISCLOSES_RISK": "Risk",
    }.get(relation_type, "Technology")


def extract_company_topic(question: str) -> str:
    if "哪些公司" not in question:
        return ""
    patterns = [
        r"哪些公司(?:.*?)(?:涉及|使用|布局|拥有|披露|属于)([^？?，,。；;]+)",
        r"([^？?，,。；;]+)有哪些公司",
    ]
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            topic = match.group(1).strip()
            topic = re.sub(r"^(了|的|相关|以下|这些)", "", topic).strip()
            return topic
    return ""


def build_answer(question: str, intent: str, cypher: str, records: list[dict[str, str]]) -> dict[str, Any]:
    if not records:
        answer = "当前知识图谱中未找到相关证据。"
    elif intent in {"tech_to_company", "topic_to_company"}:
        companies = unique_sorted([row["head_name"] for row in records])
        answer = f"当前知识图谱中，涉及该技术的公司包括：{'、'.join(companies)}。"
    elif intent == "company_to_relation":
        relation = records[0]["relation"]
        targets = unique_sorted([row["tail_name"] for row in records])
        answer = f"当前知识图谱中，该公司{RELATION_LABELS.get(relation, relation)}包括：{'、'.join(targets)}。"
    else:
        targets = unique_sorted([f"{row['head_name']} - {RELATION_LABELS.get(row['relation'], row['relation'])} - {row['tail_name']}" for row in records])
        answer = f"当前知识图谱中找到 {len(records)} 条相关证据：" + "；".join(targets[:5]) + "。"
    return {
        "question": question,
        "intent": intent,
        "cypher": cypher,
        "records": records,
        "answer": answer,
        "evidence": evidence_rows(records),
        "subgraph": subgraph_edges(records),
    }


def evidence_rows(records: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for record in records:
        rows.append(
            {
                "head": record.get("head_name", ""),
                "relation": RELATION_LABELS.get(record.get("relation", ""), record.get("relation", "")),
                "tail": record.get("tail_name", ""),
                "evidence": record.get("evidence", ""),
                "source": record.get("source_title", ""),
                "page": record.get("page", ""),
            }
        )
    return rows


def subgraph_edges(records: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "source": row.get("head_name", ""),
            "target": row.get("tail_name", ""),
            "label": RELATION_LABELS.get(row.get("relation", ""), row.get("relation", "")),
            "source_type": row.get("head_type", ""),
            "target_type": row.get("tail_type", ""),
        }
        for row in records
    ]
def short_label(value: str, length: int = 12) -> str:
    value = value or ""
    return value if len(value) <= length else value[:length] + "..."
