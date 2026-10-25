"""Text normalisation, HYDE prompts and stream/progress helpers for QA."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any
import json
import re
import time

from aika.cypher_generator import GeneratedCypher
from aika.extraction_schema import normalize_name
from aika.qa.constants import ANSWER_SYSTEM_PROMPT_TEMPLATE, TEMPLATE_RELATIONS
from aika.qa.types import HydeQuery
from aika.question_planner import QuestionPlan


def normalize_contextualizer_mode(value: str) -> str:
    """归一化上下文补全模式配置。

    Args:
        value: 原始模式值

    Returns:
        合法模式值（"auto" / "heuristic" / "llm"），非法值返回 "auto"
    """
    mode = str(value or "auto").strip().casefold()
    if mode not in {"auto", "heuristic", "llm"}:
        return "auto"
    return mode


def normalize_hyde_query_mode(value: str) -> str:
    """归一化 HYDE 检索 query 模式。"""
    mode = str(value or "hybrid").strip().casefold()
    if mode not in {"hybrid", "answer_only"}:
        return "hybrid"
    return mode


def normalize_query_text(value: str) -> str:
    """压缩 query 中的空白，保留中文和英文关键词。"""
    return " ".join(str(value or "").split()).strip()


def build_hyde_prompt(question: str, plan: QuestionPlan, *, max_chars: int) -> str:
    """构建 HYDE 假想答案 prompt。"""
    payload = {
        "question": question,
        "question_plan": plan.to_dict(),
        "max_chars": max_chars,
        "output": "只输出一段用于检索召回的假想答案正文，不要输出解释。",
    }
    return "请为以下问题生成 HYDE 检索用假想答案：\n" + json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def sanitize_hyde_answer(content: str, *, max_chars: int) -> str:
    """清洗 HYDE 输出，避免把提示性包装文本带入检索。"""
    text = str(content or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"(?im)^\s*(#+\s*)?(HYDE|假想答案|检索答案|初步答案)[:：]\s*", "", text).strip()
    text = normalize_query_text(text)
    if not text:
        return ""
    limit = max(80, int(max_chars or 700))
    return text[:limit].strip()


def build_hyde_retrieval_query(question: str, hyde_query: HydeQuery | None) -> str:
    """根据 HYDE 结果生成文本检索 query。"""
    base_query = normalize_query_text(question)
    if hyde_query is None or not hyde_query.hypothetical_answer.strip():
        return base_query
    hypothetical_answer = normalize_query_text(hyde_query.hypothetical_answer)
    if not hypothetical_answer:
        return base_query
    if normalize_hyde_query_mode(hyde_query.query_mode) == "answer_only":
        return hypothetical_answer
    return normalize_query_text(f"{base_query} {hypothetical_answer}")


def hyde_diagnostics(hyde_query: HydeQuery | None) -> dict[str, Any]:
    """序列化 HYDE 诊断信息。"""
    if hyde_query is None:
        return {
            "enabled": False,
            "generated": False,
            "source": "missing",
            "query_mode": "hybrid",
            "answer_chars": 0,
            "query_chars": 0,
            "error": "",
            "preview": "",
        }
    answer = hyde_query.hypothetical_answer or ""
    retrieval_query = hyde_query.retrieval_query or ""
    return {
        "enabled": hyde_query.enabled,
        "generated": bool(answer.strip()),
        "source": hyde_query.source,
        "query_mode": hyde_query.query_mode,
        "answer_chars": len(answer),
        "query_chars": len(retrieval_query),
        "error": hyde_query.error,
        "preview": answer[:160],
    }


def normalize_agent_max_steps(value: Any) -> int:
    """归一化 Agent 最大步数（限制在 1-4 范围内）。

    Args:
        value: 原始步数值

    Returns:
        归一化后的步数（1-4）
    """
    try:
        steps = int(value)
    except (TypeError, ValueError):
        steps = 4
    return max(1, min(steps, 4))


def record_timing(timings_ms: dict[str, float], name: str, started_at: float) -> None:
    """记录阶段耗时到 timings 字典。

    Args:
        timings_ms: 耗时字典（可变）
        name: 阶段名称
        started_at: 阶段开始时间（time.perf_counter）
    """
    timings_ms[name] = round((time.perf_counter() - started_at) * 1000, 2)


def template_cypher_for_plan(plan: QuestionPlan, *, limit: int = 50, error: str = "") -> GeneratedCypher:
    """根据查询计划生成模板化 Cypher 查询。

    自动处理关系类型选择、公司名归一化、主题匹配等逻辑。
    对于 industry_bottleneck 类型问题，自动补充 CONSTRAINS 等瓶颈相关关系。

    Args:
        plan: 查询计划
        limit: 返回记录数上限
        error: 错误信息（可选，传递上游错误）

    Returns:
        GeneratedCypher 对象
    """
    relations = [relation for relation in plan.relations if relation in TEMPLATE_RELATIONS]
    if plan.answer_type == "industry_bottleneck":
        for relation in ("CONSTRAINS", "DISCLOSES_RISK", "SUPPORTED_BY_POLICY", "ENABLES"):
            if relation not in relations:
                relations.append(relation)
    if not relations:
        relations = ["USES_TECHNOLOGY", "HAS_PRODUCT", "BELONGS_TO_CHAIN"]
    relation_clause = "|".join(relations)

    where: list[str] = ["type(r) <> 'MENTIONED_IN'"]
    params: dict[str, Any] = {}
    if plan.companies:
        params["company_norms"] = [normalize_name(company, "Company") for company in plan.companies]
        where.append("c.normalized_name IN $company_norms")
    if plan.expanded_topics:
        topics = plan.expanded_topics[:12]
        params["topics"] = topics
        params["topic_norms"] = [normalize_name(topic) for topic in topics]
        where.append(
            "(x.normalized_name IN $topic_norms OR any(topic IN $topics "
            "WHERE x.name CONTAINS topic OR r.evidence CONTAINS topic OR r.section CONTAINS topic))"
        )

    cypher = (
        f"MATCH (c:Company)-[r:{relation_clause}]->(x)\n"
        f"WHERE {' AND '.join(where)}\n"
        "RETURN c.name AS company, labels(c) AS company_labels, type(r) AS relation, "
        "x.name AS target, labels(x) AS target_labels, r.evidence AS evidence, "
        "r.source_title AS source, r.source_tier AS source_tier, r.page AS page, "
        "r.section AS section, r.source_report_id AS report_id\n"
        f"LIMIT {limit}"
    )
    return GeneratedCypher(cypher=cypher, params=params, source="template", error=error)


def build_llm_options(*, thinking_enabled: bool | None, reasoning_effort: str | None) -> dict[str, Any]:
    """构建 LLM 调用参数选项。

    Args:
        thinking_enabled: 是否启用推理展示
        reasoning_effort: 推理努力程度

    Returns:
        LLM 参数字典（只包含非 None 的配置项）
    """
    options: dict[str, Any] = {}
    if thinking_enabled is not None:
        options["thinking_enabled"] = thinking_enabled
    if reasoning_effort:
        options["reasoning_effort"] = reasoning_effort
    return options


def stream_progress(stage: str, message: str) -> dict[str, str]:
    """构造流式进度事件。

    Args:
        stage: 阶段名称
        message: 进度消息

    Returns:
        进度事件字典
    """
    return {"type": "progress", "stage": stage, "message": message}


def describe_plan_progress(plan: QuestionPlan) -> str:
    """生成问题规划进度的中文描述文本。

    Args:
        plan: 查询计划

    Returns:
        中文描述字符串，如 "问题规划完成：主题研究，关注主题为AI芯片、光模块"
    """
    type_labels = {
        "topic_to_company": "主题到公司检索",
        "company_compare": "公司对比",
        "risk_analysis": "风险分析",
        "industry_bottleneck": "产业瓶颈分析",
        "company_profile": "公司画像",
        "thematic_research": "主题研究",
    }
    parts = [f"问题规划完成：{type_labels.get(plan.answer_type, plan.answer_type)}"]
    if plan.companies:
        parts.append(f"核心公司为{'、'.join(plan.companies[:4])}")
    if plan.topics:
        parts.append(f"关注主题为{'、'.join(plan.topics[:4])}")
    return "，".join(parts)


def chunk_text(text: str, *, size: int = 18) -> Iterator[str]:
    """将文本按指定大小分块。

    用于流式输出时将完整答案切分为多个 answer_delta 事件。

    Args:
        text: 待分块的文本
        size: 每块字符数（默认 18）

    Yields:
        文本块
    """
    value = str(text or "")
    if not value:
        return
    for index in range(0, len(value), size):
        yield value[index : index + size]


def answer_system_prompt(current_date: str | None = None) -> str:
    """生成带当前日期的答案系统提示词。

    Args:
        current_date: 当前日期（可选，默认使用 datetime.now()）

    Returns:
        格式化后的系统提示词
    """
    return ANSWER_SYSTEM_PROMPT_TEMPLATE.format(current_date=current_date or datetime.now().date().isoformat())
