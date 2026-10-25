"""Paths, CSV field lists and the term tables the claim rules are built on."""

from __future__ import annotations

import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


DEFAULT_RESEARCH_DIR = ROOT_DIR / "data" / "curated"


CLAIMS_FILE = "claims.csv"


EVIDENCE_SPANS_FILE = "evidence_spans.csv"


SEGMENT_DOSSIERS_FILE = "segment_dossiers.jsonl"


CLAIM_REVIEWS_FILE = "claim_reviews.jsonl"


CLAIM_CSV_FIELDS = [
    "claim_id",
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
]


REVIEWABLE_CLAIM_FIELDS = {
    "claim_text",
    "claim_type",
    "topic",
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
}


CLAIM_REVIEW_STATUSES = {"auto", "approved", "revised", "rejected", "needs_review"}


EVIDENCE_SPAN_FIELDS = [
    "evidence_id",
    "claim_id",
    "source_report_id",
    "source_title",
    "page",
    "section",
    "source_tier",
    "text",
    "as_of_date",
    "quality",
]


EXPOSURE_ORDER = {"core": 0, "direct": 1, "indirect": 2, "mentioned": 3, "": 4}


CLAIM_TYPE_BONUS = {
    "company_exposure": 3.0,
    "mechanism": 2.4,
    "bottleneck": 2.4,
    "indicator": 2.0,
    "risk": 1.8,
    "supply_chain": 1.7,
    "policy": 1.2,
    "trend": 1.2,
}


EXPLICIT_BOTTLENECK_TERMS = (
    "瓶颈",
    "制约",
    "短板",
    "供给不足",
    "紧缺",
    "受限",
    "掣肘",
    "卡点",
    "难以满足",
    "扩容压力",
    "不及预期",
)


DIRECT_TOPIC_TERMS = {
    "AI服务器": ("ai服务器", "智算服务器", "gpu服务器", "推理服务器", "训练服务器", "服务器整机"),
    "光模块": ("光模块", "高速光模块", "光器件", "光芯片", "硅光", "cpo", "lpo", "光引擎"),
    "液冷": ("液冷", "冷板", "浸没", "cdu", "温控", "热管理", "快接头", "分水器"),
    "AI芯片": ("ai芯片", "gpu", "dcu", "cpu", "加速卡", "推理芯片", "训练芯片"),
    "国产算力": ("国产算力", "自主可控", "国产替代", "信创", "国产ai芯片", "国产服务器"),
    "算力网络": ("交换机", "以太网", "scaleup", "scale-out", "高速互联", "算力网络"),
    "PCB": ("pcb", "印制电路板", "高多层板", "封装基板", "ccl", "覆铜板"),
    "数据中心": ("数据中心", "智算中心", "aidc", "idc", "算力中心", "机柜"),
    "电源": ("电源", "ups", "服务器电源", "数据中心电源", "电力模块"),
}


TECHNICAL_REPORT_PREFIX = "industry_tech_"


MAX_DIRECT_CLAIMS_PER_REPORT = 80


TECHNICAL_HIGH_SIGNAL_TERMS = (
    "UCIe",
    "UALink",
    "Ultra Ethernet",
    "UET",
    "RDMA",
    "congestion control",
    "Scale Up",
    "Scale-Up",
    "Scale Out",
    "Scale-Out",
    "SerDes",
    "224G",
    "PAM4",
    "InfiniBand",
    "NVLink",
    "all-to-all",
    "switch fabric",
    "CPO",
    "LPO",
    "NPO",
    "silicon photonics",
    "integrated photonics",
    "optical engine",
    "HBM",
    "chiplet",
    "advanced packaging",
    "heterogeneous integration",
    "2.5D",
    "3D integration",
    "FP8",
    "MoE",
    "MLA",
    "FlashAttention",
    "PagedAttention",
    "MLPerf",
    "time-to-train",
    "throughput",
    "latency",
    "KV cache",
    "memory bandwidth",
    "communication overhead",
    "compute-communication overlap",
    "memory wall",
    "cold plate",
    "liquid cooling",
    "thermal management",
    "CDU",
    "rack manifold",
    "power density",
    "AI accelerator",
    "GPU hours",
)


TECHNICAL_LOW_VALUE_TERMS = (
    "LEGAL NOTICE",
    "ALL RIGHTS RESERVED",
    "MERCHANTABILITY",
    "FITNESS FOR A PARTICULAR PURPOSE",
    "TRADEMARK",
    "INTELLECTUAL PROPERTY",
    "NO LICENSE",
    "GOVERNING DOCUMENTS",
    "WARRANTIES",
    "COPYRIGHT",
    "REFERENCES",
    "BIBLIOGRAPHY",
    "ACM SIGCOMM",
    "IEEE TRANSACTIONS",
)


TECHNICAL_MECHANISM_TERMS = (
    "enable",
    "enables",
    "support",
    "supports",
    "achieve",
    "achieves",
    "improve",
    "improves",
    "reduce",
    "reduces",
    "accelerate",
    "accelerates",
    "efficient",
    "efficiency",
    "overlap",
    "scale",
    "scaling",
    "优化",
    "提升",
    "降低",
    "支撑",
    "推动",
    "提高",
)


TECHNICAL_BOTTLENECK_TERMS = (
    "bottleneck",
    "constraint",
    "constrained",
    "limited",
    "limitation",
    "overhead",
    "latency",
    "congestion",
    "memory wall",
    "bandwidth",
    "power density",
    "thermal",
    "功耗",
    "散热",
    "瓶颈",
    "约束",
    "受限",
    "带宽",
    "拥塞",
)


TECHNICAL_INDICATOR_TERMS = (
    "benchmark",
    "throughput",
    "latency",
    "time-to-train",
    "GPU hours",
    "tokens",
    "parameters",
    "GB/s",
    "Tb/s",
    "GT/s",
    "PAM4",
    "kW",
    "MW",
    "PUE",
    "指标",
    "吞吐",
    "时延",
    "带宽",
)


DIRECT_METRIC_PATTERN = re.compile(
    r"([-+]?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:[KMBT])?\s*(?:GPU hours|tokens|parameters|GB/s|Tb/s|GT/s|W|kW|MW|PUE|ms|us|ns|%))",
    flags=re.I,
)
