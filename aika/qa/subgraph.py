"""Assemble the graph payload that explains an answer."""

from __future__ import annotations

from typing import Any

from aika.frontend_data import RELATION_LABELS


def answer_subgraph(records: list[dict[str, Any]], evidence_cards: list[Any]) -> list[dict[str, str]]:
    """从图谱记录和证据卡片构建答案的可视化子图。

    支持多种卡片类型：
    - graph: 图谱关系边
    - dossier: 公司档案（解析敞口、技术机理、瓶颈等行）
    - claim / rag: 研究声明/文本摘要（映射到公司和主题的关系）

    Args:
        records: 图谱查询记录
        evidence_cards: 证据卡片列表

    Returns:
        子图边列表（去重，最多 100 条）
    """
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_edge(
        source: str,
        target: str,
        label: str,
        *,
        source_type: str = "",
        target_type: str = "",
        source_kind: str = "",
        citation_id: str = "",
        claim_type: str = "",
        exposure_level: str = "",
    ) -> None:
        source = str(source or "").strip()
        target = str(target or "").strip()
        label = str(label or "").strip()
        if not source or not target or not label:
            return
        key = (source, target, label, citation_id)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            {
                "source": source,
                "target": target,
                "label": label,
                "source_type": source_type,
                "target_type": target_type,
                "source_kind": source_kind,
                "citation_id": citation_id,
                "claim_type": claim_type,
                "exposure_level": exposure_level,
            }
        )

    # 图谱关系边
    for record in records:
        company = str(record.get("company") or "")
        target = str(record.get("target") or "")
        relation = str(record.get("relation") or "")
        target_labels = record.get("target_labels") or []
        target_type = target_labels[0] if isinstance(target_labels, list) and target_labels else ""
        add_edge(
            company,
            target,
            RELATION_LABELS.get(relation, relation),
            source_type="Company",
            target_type=target_type,
            source_kind="graph",
        )

    # 证据卡片边
    for card in evidence_cards:
        kind = str(getattr(card, "kind", "") or "")
        citation_id = str(getattr(card, "citation_id", "") or "")
        claim_type = str(getattr(card, "claim_type", "") or "")
        exposure_level = str(getattr(card, "exposure_level", "") or "")
        topic = str(getattr(card, "topic", "") or "")
        company = str(getattr(card, "company", "") or "")
        relation = str(getattr(card, "relation", "") or "")
        target = str(getattr(card, "target", "") or "")

        if kind == "dossier":
            add_dossier_edges(card, add_edge)
            continue
        if kind == "graph" and company and target:
            add_edge(
                company,
                target,
                RELATION_LABELS.get(relation, relation),
                source_type="Company",
                target_type=target_type_for_claim(claim_type, relation),
                source_kind=kind,
                citation_id=citation_id,
                claim_type=claim_type,
                exposure_level=exposure_level,
            )
            continue
        if company:
            claim_target = target_for_claim(card)
            add_edge(
                company,
                claim_target,
                label_for_claim(card),
                source_type="Company",
                target_type=target_type_for_claim(claim_type, relation),
                source_kind=kind,
                citation_id=citation_id,
                claim_type=claim_type,
                exposure_level=exposure_level,
            )
            continue
        if topic:
            add_edge(
                topic,
                target_for_claim(card),
                label_for_claim(card),
                source_type="ValueChainSegment",
                target_type=target_type_for_claim(claim_type, relation),
                source_kind=kind,
                citation_id=citation_id,
                claim_type=claim_type,
                exposure_level=exposure_level,
            )
    return edges[:100]


def add_dossier_edges(card: Any, add_edge: Any) -> None:
    """解析公司档案（dossier）卡片中的结构化行，生成子图边。

    解析的证据行类型：
    - "公司敞口：" → 按层级（core/direct/indirect/mentioned）生成敞口边
    - "技术机理：" → 生成"支撑"边
    - "瓶颈：" → 生成"约束"边
    - "领先指标：" → 生成"指标"边
    - "风险与反证：" → 生成"风险"边

    Args:
        card: dossier 类型的证据卡片
        add_edge: 边添加回调函数
    """
    citation_id = str(getattr(card, "citation_id", "") or "")
    topic = str(getattr(card, "topic", "") or getattr(card, "title", "") or "")
    evidence = str(getattr(card, "evidence", "") or "")
    exposure_labels = {"core": "核心敞口", "direct": "直接敞口", "indirect": "间接敞口", "mentioned": "仅提及"}
    for line in evidence.splitlines():
        line = line.strip()
        if line.startswith("公司敞口："):
            for part in line.split("：", 1)[-1].split("；"):
                if ":" not in part:
                    continue
                level, names = part.split(":", 1)
                label = exposure_labels.get(level, "敞口")
                for name in names.split("、")[:10]:
                    add_edge(
                        name,
                        topic,
                        label,
                        source_type="Company",
                        target_type="ValueChainSegment",
                        source_kind="dossier",
                        citation_id=citation_id,
                        exposure_level=level,
                    )
        elif line.startswith("技术机理："):
            add_edge(topic, "技术机理", "支撑", source_type="ValueChainSegment", target_type="IndustryConcept", source_kind="dossier", citation_id=citation_id, claim_type="mechanism")
        elif line.startswith("瓶颈："):
            add_edge(topic, "瓶颈", "约束", source_type="ValueChainSegment", target_type="Risk", source_kind="dossier", citation_id=citation_id, claim_type="bottleneck")
        elif line.startswith("领先指标："):
            add_edge(topic, "领先指标", "指标", source_type="ValueChainSegment", target_type="Metric", source_kind="dossier", citation_id=citation_id, claim_type="indicator")
        elif line.startswith("风险与反证："):
            add_edge(topic, "风险与反证", "风险", source_type="ValueChainSegment", target_type="Risk", source_kind="dossier", citation_id=citation_id, claim_type="risk")


def label_for_claim(card: Any) -> str:
    """根据证据卡片的 claim_type 和 exposure_level 确定子图边标签。

    Args:
        card: 证据卡片

    Returns:
        中文字图边标签
    """
    claim_type = str(getattr(card, "claim_type", "") or "")
    relation = str(getattr(card, "relation", "") or "")
    exposure_level = str(getattr(card, "exposure_level", "") or "")
    if claim_type == "company_exposure":
        return {"core": "核心敞口", "direct": "直接敞口", "indirect": "间接敞口", "mentioned": "仅提及"}.get(exposure_level, "敞口")
    if claim_type == "risk":
        return "风险"
    if claim_type == "indicator":
        return "指标"
    if claim_type == "bottleneck":
        return "约束"
    if claim_type in {"mechanism", "supply_chain", "trend"}:
        return "支撑"
    if relation:
        return RELATION_LABELS.get(relation, relation)
    return "证据支持"


def target_for_claim(card: Any) -> str:
    """根据证据卡片的 claim_type 生成子图中的目标节点名称。

    Args:
        card: 证据卡片

    Returns:
        目标节点名称
    """
    claim_type = str(getattr(card, "claim_type", "") or "")
    target = str(getattr(card, "target", "") or "")
    topic = str(getattr(card, "topic", "") or "")
    if target:
        return target
    if claim_type == "risk":
        return f"{topic}风险" if topic else "风险"
    if claim_type == "indicator":
        return f"{topic}指标" if topic else "指标"
    if claim_type == "bottleneck":
        return f"{topic}瓶颈" if topic else "瓶颈"
    return topic or str(getattr(card, "title", "") or "证据")


def target_type_for_claim(claim_type: str, relation: str = "") -> str:
    """根据 claim_type 和 relation 确定子图中目标节点的类型。

    Args:
        claim_type: 声明类型
        relation: 关系类型

    Returns:
        节点类型标签（Risk / Metric / ValueChainSegment / IndustryConcept）
    """
    if relation == "DISCLOSES_RISK" or claim_type in {"risk", "bottleneck"}:
        return "Risk"
    if relation == "HAS_METRIC" or claim_type == "indicator":
        return "Metric"
    if claim_type == "company_exposure":
        return "ValueChainSegment"
    return "IndustryConcept"


def ensure_relation_cards(cards: list[Any], raw_cards: list[Any], relation: str, *, limit: int) -> list[Any]:
    """确保排序后的证据卡片中包含指定关系类型的卡片。

    如果排序后的 cards 中没有指定 relation 的卡片，
    从 raw_cards 中提取第一条该关系的卡片插入到最前面。

    Args:
        cards: 排序后的证据卡片
        raw_cards: 原始未排序卡片
        relation: 需要确保存在的关系类型
        limit: 总卡片数上限

    Returns:
        确保包含指定关系卡片后的列表
    """
    if any(getattr(card, "relation", "") == relation for card in cards):
        return cards
    additions = [card for card in raw_cards if getattr(card, "relation", "") == relation]
    if not additions:
        return cards
    merged = [additions[0], *cards]
    deduped = []
    seen = set()
    for card in merged:
        key = (getattr(card, "kind", ""), getattr(card, "source", ""), getattr(card, "page", ""), getattr(card, "evidence", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(card)
    return deduped[:limit]
