"""AIKA Core lightweight research library.

This package exposes the service-free core used by CLI, MCP tools, and the web app.

Everything is resolved lazily. The CSV backend drags in the research/QA stack and the
report layer (which needs jinja2), while the SQLite backend needs nothing beyond the
standard library - so importing ``aika.aika_core.models`` must not pay for the CSV path.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

# name -> (module, attribute)
_EXPORTS: dict[str, tuple[str, str]] = {
    "AikaCoreConfig": ("aika.aika_core.config", "AikaCoreConfig"),
    "CSVResearchBackend": ("aika.aika_core.backends.csv_backend", "CSVResearchBackend"),
    "ClaimRecord": ("aika.aika_core.models", "ClaimRecord"),
    "CompanyComparison": ("aika.aika_core.models", "CompanyComparison"),
    "CompanyProfile": ("aika.aika_core.models", "CompanyProfile"),
    "ConclusionCard": ("aika.aika_core.models", "ConclusionCard"),
    "EvidenceCard": ("aika.aika_core.models", "EvidenceCard"),
    "EvidenceGap": ("aika.aika_core.models", "EvidenceGap"),
    "EvidenceLink": ("aika.aika_core.models", "EvidenceLink"),
    "GraphEdge": ("aika.aika_core.models", "GraphEdge"),
    "GraphNode": ("aika.aika_core.models", "GraphNode"),
    "LocalKnowledgeGraph": ("aika.aika_core.graph", "LocalKnowledgeGraph"),
    "ResearchBackend": ("aika.aika_core.models", "ResearchBackend"),
    "ResearchBrief": ("aika.aika_core.models", "ResearchBrief"),
    "SQLiteResearchBackend": ("aika.aika_core.backends.sqlite_backend", "SQLiteResearchBackend"),
    "audit_evidence_gaps": ("aika.aika_core.gaps", "audit_evidence_gaps"),
    "build_research_brief": ("aika.aika_core.brief", "build_research_brief"),
    "compare_companies": ("aika.aika_core.compare", "compare_companies"),
    "get_company_profile": ("aika.aika_core.profiles", "get_company_profile"),
    "load_claims": ("aika.aika_core.claims", "load_claims"),
    "load_graph": ("aika.aika_core.graph", "load_graph"),
    "search_claim_records": ("aika.aika_core.claims", "search_claim_records"),
    "subgraph_edges": ("aika.aika_core.graph", "subgraph_edges"),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attribute = target
    value = getattr(import_module(module_path), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*_EXPORTS, "default_backend", "query_graph", "search_claims", "search_evidence"])


def default_backend() -> Any:
    from aika.aika_core.backends.csv_backend import CSVResearchBackend

    return CSVResearchBackend.from_env()


def search_evidence(query: str, *, top_k: int = 8, **filters: Any) -> list[Any]:
    return default_backend().search_evidence(query, top_k=top_k, **filters)


def search_claims(query: str, *, top_k: int = 8, **filters: Any) -> list[Any]:
    return default_backend().search_claims(query, top_k=top_k, **filters)


def query_graph(
    *,
    company: str = "",
    technology: str = "",
    relation_type: str = "",
    limit: int = 80,
) -> list[Any]:
    return default_backend().query_graph(
        company=company,
        technology=technology,
        relation_type=relation_type,
        limit=limit,
    )


__all__ = [
    *_EXPORTS,
    "default_backend",
    "query_graph",
    "search_claims",
    "search_evidence",
]
