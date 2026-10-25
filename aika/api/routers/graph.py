"""Knowledge graph summary and subgraph endpoints (``/graph``)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from aika.api.deps import get_knowledge_graph
from aika.frontend_data import RELATION_LABELS, LocalKnowledgeGraph, subgraph_edges

router = APIRouter()


def relation_label_options() -> dict[str, str]:
    return {"全部关系": "", **{label: relation for relation, label in RELATION_LABELS.items()}}


@router.get("/graph/summary")
async def graph_summary(graph: LocalKnowledgeGraph = Depends(get_knowledge_graph)) -> dict[str, Any]:
    entity_counts = graph.entity_counts()
    relation_counts = graph.relation_counts()
    return {
        "companies": entity_counts.get("Company", 0),
        "reports": graph.reports_count(),
        "entities": len(graph.entities),
        "relations": len(graph.relations),
        "entity_counts": dict(entity_counts),
        "relation_counts": {RELATION_LABELS.get(key, key): value for key, value in relation_counts.items()},
        "companies_options": graph.names_by_type("Company"),
        "technologies_options": graph.names_by_type("Technology"),
        "relation_options": relation_label_options(),
    }


@router.get("/graph/subgraph")
async def graph_subgraph(
    company: str = "",
    technology: str = "",
    relation_type: str = "",
    limit: int = Query(80, ge=1, le=200),
    graph: LocalKnowledgeGraph = Depends(get_knowledge_graph),
) -> dict[str, Any]:
    rows = graph.subgraph_relations(
        company=company,
        technology=technology,
        relation_type=relation_type,
        limit=limit,
    )
    edges = subgraph_edges(rows)
    return {
        "rows": rows,
        "edges": edges,
    }
