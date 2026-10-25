"""Professional CSV/Neo4j + PostgreSQL RAG + LLM QA orchestration.

QA 引擎核心模块，协调多源数据检索和 LLM 生成的全流程。
支持两种图谱后端（Neo4j / CSV）和多种检索方式（RAG、研究报告、语义向量），
最终由 LLM 整合生成专业投研答案。

核心流程（workflow）：
1. history — 较早对话 LLM 压缩 + 最近对话原文保留
2. contextualize — 追问上下文补全
3. plan — 问题规划（启发式 / LLM）
4. hyde — 生成检索用假想答案
5. cypher — 生成图谱查询语句
6. graph — 执行图查询获取结构化关系
7. rag — 语义检索非结构化文本
8. research — 检索研究报告声明
9. evidence — 证据排序与筛选
10. answer — LLM 生成最终答案
11. verify — 答案事实一致性验证
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aika.cypher_generator import GeneratedCypher, generate_cypher
from aika.aika_core.data_paths import resolve_graph_dir
from aika.curated_graph import DEFAULT_CURATED_DIR
from aika.extraction_schema import normalize_name
from aika.frontend_data import LocalKnowledgeGraph, RELATION_LABELS, subgraph_edges
from aika.llm_client import OpenAICompatibleClient, load_dotenv
from aika.neo4j_client import Neo4jReadClient
from aika.agents.verification import build_evidence_limited_answer, verify_answer_support
from aika.professional_qa import (
    build_professional_answer_prompt,
    cards_from_graph_records,
    cards_from_rag_hits,
    cards_from_research_hits,
    assign_citation_ids,
    fallback_professional_answer,
    legacy_evidence_rows,
    pseudo_cypher_for_plan,
    rank_evidence_cards,
    search_csv_graph,
)
from aika.postgres_retrieval import (
    EMBEDDING_DIMENSIONS,
    PostgresRagIndex,
    PostgresResearchMemory,
    PostgresRetrievalStore,
    PostgresSemanticIndex,
)
from aika.question_planner import QuestionPlan, extract_companies, heuristic_plan_question, plan_question
from aika.rag_index import RagHit
from aika.reranker import normalize_rerank_mode
from aika.research_agent import build_research_outputs
from aika.research_claims import ResearchHit


# ============================================================
# 常量与模板
# ============================================================
from aika.qa.constants import (
    ANSWER_SYSTEM_PROMPT_TEMPLATE,
    HISTORY_COMPRESSION_SYSTEM_PROMPT,
    NO_EVIDENCE_ANSWER,
    TEMPLATE_RELATIONS,
)
from aika.qa.history import (
    normalize_conversation_history,
    normalize_conversation_messages,
    trim_history_to_chars,
    fit_summary_and_recent_to_budget,
    compress_history_with_llm,
    history_chunks,
    request_history_summary,
    sanitize_history_summary,
    build_contextualizer_prompt,
    heuristic_contextual_question,
    question_needs_context,
    sanitize_contextual_question,
    format_history_for_prompt,
)
from aika.qa.subgraph import (
    answer_subgraph,
    add_dossier_edges,
    label_for_claim,
    target_for_claim,
    target_type_for_claim,
    ensure_relation_cards,
)
from aika.qa.text import (
    normalize_contextualizer_mode,
    normalize_hyde_query_mode,
    normalize_query_text,
    build_hyde_prompt,
    sanitize_hyde_answer,
    build_hyde_retrieval_query,
    hyde_diagnostics,
    normalize_agent_max_steps,
    record_timing,
    template_cypher_for_plan,
    build_llm_options,
    stream_progress,
    describe_plan_progress,
    chunk_text,
    answer_system_prompt,
)
from aika.qa.types import HydeQuery
CONTEXTUALIZER_SYSTEM_PROMPT = """你是中国 AI 算力产业链问答系统的追问改写器。
根据历史对话，把用户当前问题改写成可独立检索的中文问题。
只输出改写后的问题，不解释，不回答问题，不引入历史对话中没有出现的新公司或主题。"""
HYDE_SYSTEM_PROMPT = """你是中国 AI 算力产业链问答系统的 HYDE 检索生成器。
根据用户问题和结构化问题规划，生成一段可能出现在年报、研报或技术白皮书中的假想答案。
这段内容只用于改进检索召回，不是最终答案，也不是证据。
不要输出 Markdown 标题，不要引用证据编号，不要给股票买卖建议、目标价或收益预测。
不得编造具体数值、日期、页码、报告名或政策名称；缺少证据时用概括性产业机制、公司敞口、风险、指标和同义表达扩展语义。
公司、主题和答案类型必须服从给定的问题规划。只输出假想答案正文。"""
HISTORY_SUMMARY_PREFIX = "历史对话压缩摘要（仅作上下文，不是对当前问题的回答）：\n"
# 模板化 Cypher 查询中支持的关系类型集合
@dataclass
class QAEngineStatus:
    """QA 引擎状态信息，记录各组件的可用性和错误状态。
    Attributes:
        neo4j_enabled: Neo4j 图数据库是否可用
        rag_enabled: RAG 索引是否可用
        llm_enabled: LLM 客户端是否可用
        research_enabled: 研究报告索引是否可用
        embedding_enabled: 语义向量索引是否可用
        csv_graph_enabled: CSV 图谱是否可用
        graph_backend: 当前使用的图谱后端（"neo4j" / "csv" / "none"）
        graph_data_dir: 图谱数据目录路径
        graph_error: 图谱组件的错误信息
        rag_error: RAG 索引的错误信息
        research_error: 研究报告索引的错误信息
        embedding_error: 语义索引的错误信息
        llm_error: LLM 客户端的错误信息
    """
    neo4j_enabled: bool
    rag_enabled: bool
    llm_enabled: bool
    research_enabled: bool = False
    embedding_enabled: bool = False
    csv_graph_enabled: bool = False
    graph_backend: str = "neo4j"
    graph_data_dir: str = ""
    graph_error: str = ""
    rag_error: str = ""
    research_error: str = ""
    embedding_error: str = ""
    llm_error: str = ""


class CountingLLMClient:
    """LLM 客户端代理，在保持 hasattr 行为的同时记录远程调用次数。
    用于诊断和调试，可在 diagnostics 中输出每次 QA 流程的 LLM 调用量。
    只代理 TRACKED_METHODS 中的方法，其余属性和方法透传。
    """
    TRACKED_METHODS = {"chat_json", "chat_text", "chat_text_with_metadata", "chat_messages", "stream_chat_messages"}
    def __init__(self, client: Any) -> None:
        self._client = client
        self.calls: dict[str, int] = {"total": 0}
    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if name not in self.TRACKED_METHODS or not callable(attr):
            return attr
        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls["total"] = self.calls.get("total", 0) + 1
            self.calls[name] = self.calls.get(name, 0) + 1
            return attr(*args, **kwargs)
        return counted
class QAEngine:
    """QA 引擎主类，协调知识图谱、RAG、研究报告、语义检索和 LLM 生成的全流程。
    支持两种回答模式：
    1. Agent 模式（enable_agent=True）— 使用 QAAgent 进行多步工具调用
    2. Workflow 模式 — 按固定流水线依次执行各阶段
    数据源支持：
    - 知识图谱：Neo4j 或 CSV 文件
    - RAG 索引：PostgreSQL 中的文档向量索引
    - 研究报告：PostgreSQL 中的声明/摘要索引
    - 语义索引：PostgreSQL 中的多类型语义向量索引
    """
    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        graph_client: Any | None = None,
        csv_graph: LocalKnowledgeGraph | None = None,
        rag_index: Any | None = None,
        research_memory: Any | None = None,
        semantic_index: Any | None = None,
        retrieval_store: PostgresRetrievalStore | None = None,
        enable_llm_cypher: bool = False,
        enable_llm_planner: bool = False,
        contextualizer_mode: str = "auto",
        rag_top_k: int = 6,
        semantic_top_k: int = 8,
        graph_limit: int = 50,
        rerank_top_n: int = 12,
        evidence_top_n: int = 6,
        core_companies_only: bool = True,
        history_max_turns: int = 3,
        history_max_chars: int = 4000,
        history_compression_enabled: bool = True,
        history_summary_max_chars: int = 1600,
        history_compression_chunk_chars: int = 12000,
        enable_hyde: bool = True,
        hyde_query_mode: str = "hybrid",
        hyde_max_chars: int = 700,
        enable_agent: bool = True,
        agent_max_steps: int = 4,
        rerank_mode: str = "auto",
        drift_max_subquestions: int = 6,
        global_dossier_top_k: int = 3,
        local_claim_top_k: int = 12,
        graph_path_top_k: int = 6,
        multi_agent_max_workers: int = 5,
        multi_agent_max_llm_calls: int = 12,
        multi_agent_task_timeout_seconds: float = 90.0,
        status: QAEngineStatus | None = None,
    ) -> None:
        """初始化 QA 引擎。
        Args:
            llm_client: LLM 客户端（如 OpenAICompatibleClient）
            graph_client: Neo4j 图数据库客户端
            csv_graph: CSV 图谱数据（LocalKnowledgeGraph）
            rag_index: RAG 索引（PostgresRagIndex）
            research_memory: 研究报告索引（PostgresResearchMemory）
            semantic_index: 语义向量索引（PostgresSemanticIndex）
            retrieval_store: PostgreSQL 检索存储
            enable_llm_cypher: 是否启用 LLM 生成 Cypher 查询
            enable_llm_planner: 是否启用 LLM 问题规划
            contextualizer_mode: 追问上下文补全模式（"auto" / "heuristic" / "llm"）
            rag_top_k: RAG 检索返回的候选数
            semantic_top_k: 语义检索返回的候选数
            graph_limit: 图谱查询返回的记录数上限
            rerank_top_n: 重排序的候选数
            evidence_top_n: 最终保留的证据卡片数
            core_companies_only: 是否只查询核心上市公司
            history_max_turns: 不压缩、直接保留原文的最近对话轮数
            history_max_chars: 压缩摘要与最近原文的总字符预算
            history_compression_enabled: 是否使用 LLM 压缩较早对话
            history_summary_max_chars: 压缩摘要的最大字符数
            history_compression_chunk_chars: 单次送入压缩器的历史字符数
            enable_hyde: 是否启用 HYDE 检索前假想答案生成
            hyde_query_mode: HYDE 检索 query 模式（"hybrid" / "answer_only"）
            hyde_max_chars: HYDE 假想答案最大字符数
            enable_agent: 是否启用 Agent 模式
            agent_max_steps: Agent 最大步数（1-4）
            rerank_mode: 重排序模式（"auto" / "llm" / "none"）
            drift_max_subquestions: GraphRAG DRIFT 最大子问题数
            global_dossier_top_k: 全局档案检索 top-k
            local_claim_top_k: 本地声明检索 top-k
            graph_path_top_k: 图谱路径检索 top-k
            multi_agent_max_workers: 中心化查询 Agent 最大并发数
            multi_agent_max_llm_calls: 单次问答的中心化 Agent LLM 调用预算
            multi_agent_task_timeout_seconds: 单轮并行查询的超时时间
            status: 引擎状态对象（可选，不传则自动生成）
        """
        self.llm_client = llm_client
        self.graph_client = graph_client
        self.csv_graph = csv_graph
        self.rag_index = rag_index
        self.research_memory = research_memory
        self.semantic_index = semantic_index
        self.retrieval_store = retrieval_store
        self.enable_llm_cypher = enable_llm_cypher
        self.enable_llm_planner = enable_llm_planner
        self.contextualizer_mode = normalize_contextualizer_mode(contextualizer_mode)
        self.rag_top_k = rag_top_k
        self.semantic_top_k = semantic_top_k
        self.graph_limit = graph_limit
        self.rerank_top_n = rerank_top_n
        self.evidence_top_n = evidence_top_n
        self.core_companies_only = core_companies_only
        self.history_max_turns = max(0, int(history_max_turns or 0))
        self.history_max_chars = max(0, int(history_max_chars or 0))
        self.history_compression_enabled = bool(history_compression_enabled)
        self.history_summary_max_chars = max(200, int(history_summary_max_chars or 1600))
        self.history_compression_chunk_chars = max(1000, int(history_compression_chunk_chars or 12000))
        self.enable_hyde = bool(enable_hyde)
        self.hyde_query_mode = normalize_hyde_query_mode(hyde_query_mode)
        self.hyde_max_chars = max(80, int(hyde_max_chars or 700))
        self.enable_agent = enable_agent
        self.agent_max_steps = normalize_agent_max_steps(agent_max_steps)
        self.rerank_mode = normalize_rerank_mode(rerank_mode)
        self.drift_max_subquestions = max(1, int(drift_max_subquestions or 6))
        self.global_dossier_top_k = max(0, int(global_dossier_top_k or 3))
        self.local_claim_top_k = max(0, int(local_claim_top_k or 12))
        self.graph_path_top_k = max(0, int(graph_path_top_k or 6))
        self.multi_agent_max_workers = max(1, int(multi_agent_max_workers or 5))
        self.multi_agent_max_llm_calls = max(0, int(multi_agent_max_llm_calls or 12))
        self.multi_agent_task_timeout_seconds = max(1.0, float(multi_agent_task_timeout_seconds or 90.0))
        self.status = status or QAEngineStatus(
            neo4j_enabled=graph_client is not None,
            csv_graph_enabled=csv_graph is not None,
            rag_enabled=rag_index is not None,
            research_enabled=research_memory is not None,
            embedding_enabled=semantic_index is not None,
            llm_enabled=llm_client is not None,
            graph_backend="neo4j" if graph_client is not None else "csv" if csv_graph is not None else "none",
        )
    @classmethod
    def from_env(cls) -> "QAEngine":
        """从环境变量构造 QAEngine 实例。
        读取 .env 文件或系统环境变量中的配置，自动初始化所有组件。
        组件初始化失败时记录错误到 status，不影响引擎启动（优雅降级）。
        Returns:
            配置完成的 QAEngine 实例
        """
        load_dotenv()
        rag_top_k = int(os.getenv("RAG_TOP_K", "6"))
        semantic_top_k = int(os.getenv("SEMANTIC_TOP_K", "8"))
        graph_limit = int(os.getenv("QA_GRAPH_LIMIT", "50"))
        rerank_top_n = int(os.getenv("QA_RERANK_TOP_N", "12"))
        evidence_top_n = int(os.getenv("QA_EVIDENCE_TOP_N", "6"))
        core_companies_only = os.getenv("QA_CORE_COMPANIES_ONLY", "true").casefold() != "false"
        enable_llm_cypher = os.getenv("QA_ENABLE_LLM_CYPHER", "false").casefold() != "false"
        enable_llm_planner = os.getenv("QA_ENABLE_LLM_PLANNER", "false").casefold() != "false"
        contextualizer_mode = normalize_contextualizer_mode(os.getenv("QA_CONTEXTUALIZER_MODE", "auto"))
        history_max_turns = int(os.getenv("QA_HISTORY_MAX_TURNS", "3"))
        history_max_chars = int(os.getenv("QA_HISTORY_MAX_CHARS", "4000"))
        history_compression_enabled = os.getenv("QA_HISTORY_COMPRESSION_ENABLED", "true").casefold() != "false"
        history_summary_max_chars = int(os.getenv("QA_HISTORY_SUMMARY_MAX_CHARS", "1600"))
        history_compression_chunk_chars = int(os.getenv("QA_HISTORY_COMPRESSION_CHUNK_CHARS", "12000"))
        enable_hyde = os.getenv("QA_ENABLE_HYDE", "true").casefold() != "false"
        hyde_query_mode = normalize_hyde_query_mode(os.getenv("QA_HYDE_QUERY_MODE", "hybrid"))
        hyde_max_chars = int(os.getenv("QA_HYDE_MAX_CHARS", "700"))
        enable_agent = os.getenv("QA_ENABLE_AGENT", "true").casefold() != "false"
        agent_max_steps = normalize_agent_max_steps(os.getenv("QA_AGENT_MAX_STEPS", "4"))
        rerank_mode = normalize_rerank_mode(os.getenv("QA_RERANK_MODE", "auto"))
        drift_max_subquestions = int(os.getenv("QA_DRIFT_MAX_SUBQUESTIONS", "6"))
        global_dossier_top_k = int(os.getenv("QA_GLOBAL_DOSSIER_TOP_K", "3"))
        local_claim_top_k = int(os.getenv("QA_LOCAL_CLAIM_TOP_K", "12"))
        graph_path_top_k = int(os.getenv("QA_GRAPH_PATH_TOP_K", "6"))
        multi_agent_max_workers = int(os.getenv("QA_MULTI_AGENT_MAX_WORKERS", "5"))
        multi_agent_max_llm_calls = int(os.getenv("QA_MULTI_AGENT_MAX_LLM_CALLS", "12"))
        multi_agent_task_timeout_seconds = float(os.getenv("QA_MULTI_AGENT_TASK_TIMEOUT_SECONDS", "90"))
        graph_backend = os.getenv("QA_GRAPH_BACKEND", "auto").casefold()
        disable_postgres = os.getenv("QA_DISABLE_POSTGRES", "false").strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }
        # PostgreSQL 检索存储
        retrieval_store = None
        rag_index = None
        research_memory = None
        rag_error = ""
        research_error = ""
        if not disable_postgres:
            retrieval_store = PostgresRetrievalStore.from_env()
            try:
                retrieval_store.ensure_ready()
            except Exception:
                retrieval_store.close()
                raise
            rag_index = PostgresRagIndex(retrieval_store)
            research_memory = PostgresResearchMemory(retrieval_store)
        # LLM 客户端
        llm_client = None
        llm_error = ""
        try:
            llm_client = OpenAICompatibleClient()
        except Exception as exc:
            llm_error = str(exc)
        # 语义向量索引
        semantic_index = None
        embedding_error = ""
        if retrieval_store is not None:
            try:
                from aika.embedding_client import OpenAICompatibleEmbeddingClient, embedding_configured
                if embedding_configured():
                    embedding_client = OpenAICompatibleEmbeddingClient(dimensions=EMBEDDING_DIMENSIONS)
                    semantic_index = PostgresSemanticIndex(
                        retrieval_store,
                        embedding_client=embedding_client,
                    )
            except Exception as exc:
                embedding_error = str(exc)
        # CSV 图谱
        csv_graph = None
        graph_error = ""
        graph_data_dir = resolve_graph_dir(os.getenv("KG_DATA_DIR"))
        try:
            csv_graph = LocalKnowledgeGraph.from_dir(graph_data_dir)
        except Exception as exc:
            graph_error = f"CSV graph unavailable: {exc}"
        # Neo4j 图数据库
        graph_client = None
        neo4j_enabled = False
        selected_backend = "csv" if csv_graph is not None else "none"
        if graph_backend in {"auto", "neo4j"}:
            try:
                candidate = Neo4jReadClient()
                ok, message = candidate.check_connection()
                if ok:
                    graph_client = candidate
                    neo4j_enabled = True
                    selected_backend = "neo4j"
                else:
                    candidate.close()
                    if graph_backend == "neo4j":
                        graph_error = message
            except Exception as exc:
                if graph_backend == "neo4j":
                    graph_error = str(exc)
        if graph_backend == "csv":
            selected_backend = "csv" if csv_graph is not None else "none"
        status = QAEngineStatus(
            neo4j_enabled=neo4j_enabled,
            csv_graph_enabled=csv_graph is not None,
            rag_enabled=rag_index is not None,
            research_enabled=research_memory is not None,
            embedding_enabled=semantic_index is not None,
            llm_enabled=llm_client is not None,
            graph_backend=selected_backend,
            graph_data_dir=str(graph_data_dir),
            graph_error=graph_error,
            rag_error=rag_error,
            research_error=research_error,
            embedding_error=embedding_error,
            llm_error=llm_error,
        )
        return cls(
            llm_client=llm_client,
            graph_client=graph_client,
            csv_graph=csv_graph,
            rag_index=rag_index,
            research_memory=research_memory,
            semantic_index=semantic_index,
            retrieval_store=retrieval_store,
            enable_llm_cypher=enable_llm_cypher,
            enable_llm_planner=enable_llm_planner,
            contextualizer_mode=contextualizer_mode,
            rag_top_k=rag_top_k,
            semantic_top_k=semantic_top_k,
            graph_limit=graph_limit,
            rerank_top_n=rerank_top_n,
            evidence_top_n=evidence_top_n,
            core_companies_only=core_companies_only,
            history_max_turns=history_max_turns,
            history_max_chars=history_max_chars,
            history_compression_enabled=history_compression_enabled,
            history_summary_max_chars=history_summary_max_chars,
            history_compression_chunk_chars=history_compression_chunk_chars,
            enable_hyde=enable_hyde,
            hyde_query_mode=hyde_query_mode,
            hyde_max_chars=hyde_max_chars,
            enable_agent=enable_agent,
            agent_max_steps=agent_max_steps,
            rerank_mode=rerank_mode,
            drift_max_subquestions=drift_max_subquestions,
            global_dossier_top_k=global_dossier_top_k,
            local_claim_top_k=local_claim_top_k,
            graph_path_top_k=graph_path_top_k,
            multi_agent_max_workers=multi_agent_max_workers,
            multi_agent_max_llm_calls=multi_agent_max_llm_calls,
            multi_agent_task_timeout_seconds=multi_agent_task_timeout_seconds,
            status=status,
        )
    def close(self) -> None:
        """释放资源：关闭图数据库连接和 PostgreSQL 连接。"""
        if self.graph_client is not None and hasattr(self.graph_client, "close"):
            self.graph_client.close()
        if self.retrieval_store is not None:
            self.retrieval_store.close()
    # ============================================================
    # 公开入口：同步回答 + 流式回答
    # ============================================================
    def answer_question(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        """回答用户问题（同步入口）。
        根据 enable_agent 配置选择使用 Agent 模式还是 Workflow 模式。
        Agent 模式支持多步工具调用，Workflow 模式按固定流水线执行。
        Args:
            question: 用户问题
            conversation_history: 对话历史（可选）
            thinking_enabled: 是否显示思考过程
            reasoning_effort: 推理努力程度
        Returns:
            包含 answer、evidence、verification、subgraph、diagnostics 等的完整结果字典
        """
        if self.enable_agent:
            from aika.agents.qa_agent import QAAgent
            return QAAgent(self, max_steps=self.agent_max_steps).run(
                question,
                conversation_history=conversation_history,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
            )
        return self._answer_question_workflow(
            question,
            conversation_history=conversation_history,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )
    def answer_question_stream(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """流式回答用户问题。
        逐步产生 progress（进度）、answer_delta（答案片段）、final（最终结果）事件。
        支持思考过程的可视化展示。
        Args:
            question: 用户问题
            conversation_history: 对话历史
            thinking_enabled: 是否显示思考过程
            reasoning_effort: 推理努力程度
        Yields:
            事件字典：{"type": "progress", "stage": ..., "message": ...}
            或 {"type": "answer_delta", "content": ...}
            或 {"type": "answer_complete", "answer": ..., "reasoning_content": ...}
            或 {"type": "final", "result": {...}}
        """
        if self.enable_agent:
            from aika.agents.qa_agent import QAAgent
            yield from QAAgent(self, max_steps=self.agent_max_steps).run_stream(
                question,
                conversation_history=conversation_history,
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
            )
            return
        yield from self._answer_question_stream_workflow(
            question,
            conversation_history=conversation_history,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )
    # ============================================================
    # Workflow 内部方法
    # ============================================================
    def _prepare_conversation_history(
        self,
        conversation_history: list[dict[str, str]] | None,
        *,
        errors: list[str],
        llm_options: dict[str, Any],
        llm_client: Any | None,
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """Build short-term memory from an LLM summary plus recent verbatim turns."""
        normalized = normalize_conversation_messages(conversation_history)
        fallback = normalize_conversation_history(
            normalized,
            max_turns=self.history_max_turns,
            max_chars=self.history_max_chars,
        )
        metadata = {
            "history_strategy": "recent_window",
            "history_source_messages": len(normalized),
            "history_summarized_messages": 0,
            "history_summary_chars": 0,
            "history_compressed": False,
        }
        if not normalized:
            metadata["history_strategy"] = "empty"
            return [], metadata
        recent_start = max(0, len(normalized) - self.history_max_turns * 2)
        older = normalized[:recent_start]
        recent_candidates = normalized[recent_start:]
        if not older:
            metadata["history_strategy"] = "full_recent"
            return trim_history_to_chars(recent_candidates, self.history_max_chars), metadata
        if not self.history_compression_enabled or llm_client is None:
            return fallback, metadata
        summary_budget = self.history_summary_max_chars
        if self.history_max_chars > 0:
            available_summary_chars = self.history_max_chars - len(HISTORY_SUMMARY_PREFIX)
            if available_summary_chars <= 0:
                return fallback, metadata
            summary_budget = min(summary_budget, max(1, available_summary_chars // 2))
            recent_budget = max(0, self.history_max_chars - summary_budget - len(HISTORY_SUMMARY_PREFIX))
        else:
            recent_budget = 0
        recent = (
            []
            if self.history_max_chars > 0 and recent_budget <= 0
            else trim_history_to_chars(recent_candidates, recent_budget)
        )
        dropped_recent_count = max(0, len(recent_candidates) - len(recent))
        if dropped_recent_count:
            older = [*older, *recent_candidates[:dropped_recent_count]]
        try:
            summary = compress_history_with_llm(
                older,
                llm_client=llm_client,
                llm_options=llm_options,
                max_summary_chars=summary_budget,
                chunk_chars=self.history_compression_chunk_chars,
            )
        except Exception as exc:
            errors.append(f"Conversation history compression failed: {exc}")
            return fallback, metadata
        if not summary:
            errors.append("Conversation history compression failed: empty summary")
            return fallback, metadata
        summary_message = {
            "role": "assistant",
            "content": HISTORY_SUMMARY_PREFIX + summary,
        }
        history = [summary_message, *recent]
        if self.history_max_chars > 0:
            history = fit_summary_and_recent_to_budget(history, self.history_max_chars)
        metadata.update(
            {
                "history_strategy": "llm_compression",
                "history_summarized_messages": len(older),
                "history_summary_chars": len(summary),
                "history_compressed": True,
            }
        )
        return history, metadata
    def _answer_question_workflow(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any]:
        """Workflow 模式的非流式问答。
        实现见 `_run_answer_pipeline`：这里只负责消费流水线的 final 事件。
        """
        for event in self._run_answer_pipeline(
            question,
            conversation_history,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            stream=False,
        ):
            if event.get("type") == "final":
                return dict(event["result"])
        raise RuntimeError("answer pipeline produced no final result")
    def _answer_question_stream_workflow(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Workflow 模式的流式问答。
        与 `_answer_question_workflow` 共用同一条流水线，区别只是 `stream=True`：
        会额外产出 progress 与 answer_delta 事件。
        """
        yield from self._run_answer_pipeline(
            question,
            conversation_history,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
            stream=True,
        )
    def _run_answer_pipeline(
        self,
        question: str,
        conversation_history: list[dict[str, str]] | None = None,
        *,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
        stream: bool,
    ) -> Iterator[dict[str, Any]]:
        """Workflow 模式的唯一问答流水线。
        按顺序执行 11 个阶段，并记录各阶段耗时：
            history → contextualize → plan → hyde → cypher → graph
                    → rag → research → evidence → answer → verify
        `stream=False` 时不产出任何进度事件，只在最后产出一个 final 事件。
        `stream=True` 且 `thinking_enabled` 时，每个阶段产出 progress，
        answer 阶段逐 token 产出 answer_delta。
        Args:
            question: 用户问题
            conversation_history: 对话历史
            thinking_enabled: 是否输出思考过程
            reasoning_effort: 推理努力程度
            stream: 是否产出流式事件
        Yields:
            progress / answer_delta 事件，以及恰好一个 final 事件
        """
        show_progress = bool(stream and thinking_enabled)
        total_start = time.perf_counter()
        timings_ms: dict[str, float] = {}
        question = question.strip()
        errors: list[str] = []
        llm_client = CountingLLMClient(self.llm_client) if self.llm_client is not None else None
        llm_options = build_llm_options(thinking_enabled=thinking_enabled, reasoning_effort=reasoning_effort)
        # 阶段 1: 对话历史归一化
        if show_progress:
            yield stream_progress("history", "正在结合历史对话理解当前问题")
        stage_start = time.perf_counter()
        history, history_memory = self._prepare_conversation_history(
            conversation_history,
            errors=errors,
            llm_options=llm_options,
            llm_client=llm_client,
        )
        record_timing(timings_ms, "history", stage_start)
        # 阶段 2: 追问上下文补全
        if show_progress:
            yield stream_progress("contextualize", "正在判断是否需要补全追问上下文")
        stage_start = time.perf_counter()
        contextual_question = self._contextualize_question(question, history, errors, llm_options, llm_client)
        record_timing(timings_ms, "contextualize", stage_start)
        if show_progress and contextual_question != question:
            yield stream_progress("contextualize", "已将追问改写为可独立检索的问题")
        # 阶段 3: 问题规划
        if show_progress:
            yield stream_progress("plan", "正在识别公司、主题和答案类型")
        stage_start = time.perf_counter()
        plan = heuristic_plan_question(contextual_question, core_companies_only=self.core_companies_only)
        planner_source = "heuristic"
        if self._should_use_llm_planner(plan, llm_client):
            plan = plan_question(
                contextual_question,
                client=llm_client,
                core_companies_only=self.core_companies_only,
                llm_options=llm_options,
            )
            planner_source = "llm"
        record_timing(timings_ms, "plan", stage_start)
        if show_progress:
            yield stream_progress("plan", describe_plan_progress(plan))
        # 阶段 4: HYDE 检索前假想答案
        if show_progress:
            yield stream_progress("hyde", "正在生成用于检索扩展的假想答案")
        stage_start = time.perf_counter()
        hyde_query = self._build_hyde_query(contextual_question, plan, errors, llm_options, llm_client)
        retrieval_question = hyde_query.retrieval_query or contextual_question
        record_timing(timings_ms, "hyde", stage_start)
        if show_progress:
            message = "HYDE 已生成检索扩展" if hyde_query.hypothetical_answer else "HYDE 未生成，使用原问题检索"
            yield stream_progress("hyde", message)
        # 阶段 5: 生成 Cypher 查询
        if show_progress:
            yield stream_progress("cypher", "正在准备图谱查询条件")
        stage_start = time.perf_counter()
        generated = self._generate_display_cypher(contextual_question, plan, errors, llm_options, llm_client)
        if generated.error:
            errors.append(generated.error)
        record_timing(timings_ms, "cypher", stage_start)
        # 阶段 6: 执行图查询
        if show_progress:
            yield stream_progress("graph", "正在检索产业链图谱关系")
        stage_start = time.perf_counter()
        graph_records = self._query_graph(generated, plan, errors)
        record_timing(timings_ms, "graph", stage_start)
        # 阶段 7: RAG 检索
        if show_progress:
            yield stream_progress("rag", "正在召回本地研报与原文片段")
        stage_start = time.perf_counter()
        rag_hits = self._search_rag(retrieval_question, plan, errors)
        record_timing(timings_ms, "rag", stage_start)
        # 阶段 8: 研究报告检索
        if show_progress:
            yield stream_progress("research", "正在召回投研 Claim 与产业链摘要")
        stage_start = time.perf_counter()
        research_hits = self._search_research(retrieval_question, plan, errors)
        record_timing(timings_ms, "research", stage_start)
        # 阶段 9: 证据合并与排序
        if show_progress:
            yield stream_progress("evidence", "正在筛选可支撑答案的证据")
        stage_start = time.perf_counter()
        raw_cards = [
            *cards_from_research_hits(research_hits, plan),
            *cards_from_graph_records(graph_records, plan),
            *cards_from_rag_hits(rag_hits, plan),
        ]
        evidence_cards = rank_evidence_cards(raw_cards, limit=self.evidence_top_n, plan=plan)
        if plan.answer_type == "risk_analysis":
            evidence_cards = ensure_relation_cards(evidence_cards, raw_cards, "DISCLOSES_RISK", limit=self.evidence_top_n)
        evidence_cards = assign_citation_ids(evidence_cards)
        record_timing(timings_ms, "evidence", stage_start)
        if show_progress:
            yield stream_progress("evidence", f"已保留 {len(evidence_cards)} 条高相关证据，开始组织答案")
        # 阶段 10: LLM 生成答案
        stage_start = time.perf_counter()
        answer = ""
        reasoning_content = ""
        if stream:
            for event in self._generate_answer_stream(
                question,
                contextual_question,
                history,
                plan,
                graph_records,
                evidence_cards,
                errors,
                llm_options,
                llm_client,
                thinking_enabled=bool(thinking_enabled),
            ):
                if event.get("type") in {"answer_delta", "progress"}:
                    yield event
                    continue
                if event.get("type") == "answer_complete":
                    answer = str(event.get("answer") or "")
                    reasoning_content = str(event.get("reasoning_content") or "")
        else:
            answer, reasoning_content = self._generate_answer(
                question,
                contextual_question,
                history,
                plan,
                graph_records,
                evidence_cards,
                errors,
                llm_options,
                llm_client,
            )
        record_timing(timings_ms, "answer", stage_start)
        # 阶段 11: 答案事实一致性验证
        verification = verify_answer_support(answer, plan, evidence_cards, raw_cards, question=contextual_question)
        if verification.get("status") == "fail":
            answer = build_evidence_limited_answer(plan, evidence_cards, verification)
            reasoning_content = ""
            verification = verify_answer_support(answer, plan, evidence_cards, raw_cards, question=contextual_question)
        # 渲染最终输出
        stage_start = time.perf_counter()
        evidence = legacy_evidence_rows(evidence_cards)
        research_outputs = build_research_outputs(
            question=contextual_question,
            plan=plan,
            evidence_cards=evidence_cards,
            graph_records=graph_records,
            verification=verification,
        )
        record_timing(timings_ms, "render_payload", stage_start)
        diagnostics = {
            "graph_backend": self.status.graph_backend,
            "graph_records": len(graph_records),
            "rag_hits": len(rag_hits),
            "research_hits": len(research_hits),
            "embedding_hits": 0,
            "embedding_enabled": bool(getattr(self.status, "embedding_enabled", False)),
            "evidence_cards": len(evidence_cards),
            "rerank_top_n": self.rerank_top_n,
            "history_messages": len(history),
            **history_memory,
            "contextualized": contextual_question != question,
            "contextualizer_mode": self.contextualizer_mode,
            "planner_source": planner_source,
            "hyde": hyde_diagnostics(hyde_query),
            "enable_llm_cypher": self.enable_llm_cypher,
            "enable_llm_planner": self.enable_llm_planner,
            "thinking_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort or "",
            "graph_error": self.status.graph_error,
            "rag_error": self.status.rag_error,
            "research_error": self.status.research_error,
            "embedding_error": getattr(self.status, "embedding_error", ""),
            "llm_error": self.status.llm_error,
            "unsupported_terms": list(verification.get("checks", {}).get("unsupported_terms") or []),
            "agent_enabled": False,
            "agent_runner": "workflow",
            "langgraph_enabled": False,
            "agent_max_steps": self.agent_max_steps,
            "agent_steps": 0,
            "agent_trace": [],
            "agent_verification": verification,
        }
        timings_ms["total"] = round((time.perf_counter() - total_start) * 1000, 2)
        diagnostics["timings_ms"] = timings_ms
        diagnostics["llm_calls"] = llm_client.calls if llm_client is not None else {"total": 0}
        yield {
            "type": "final",
            "result": {
                "question": question,
                "contextual_question": contextual_question,
                "answer": answer,
                "reasoning_content": reasoning_content,
                "answer_type": plan.answer_type,
                "plan": plan.to_dict(),
                "cypher": generated.cypher,
                "cypher_params": generated.params,
                "cypher_source": generated.source,
                "graph_records": graph_records,
                "rag_hits": [hit.to_dict() for hit in rag_hits],
                "research_hits": [hit.to_dict() for hit in research_hits],
                "evidence_cards": [card.to_dict() for card in evidence_cards],
                "evidence": evidence,
                "research_outputs": research_outputs,
                "verification": verification,
                "subgraph": answer_subgraph(graph_records, evidence_cards),
                "diagnostics": diagnostics,
                "errors": errors,
            },
        }
    # ============================================================
    # 各阶段私有方法
    # ============================================================
    def _should_use_llm_planner(self, plan: QuestionPlan, llm_client: Any | None) -> bool:
        """判断是否应该使用 LLM 进行问题规划优化。
        当满足以下条件时使用 LLM planner：
        1. enable_llm_planner 为 True
        2. LLM 客户端可用且支持 chat_json
        3. 问题的 answer_type 为 thematic_research 且未识别出公司和主题
        Args:
            plan: 启发式规则生成的 QuestionPlan
            llm_client: LLM 客户端
        Returns:
            是否启用 LLM 规划
        """
        if not self.enable_llm_planner or llm_client is None or not hasattr(llm_client, "chat_json"):
            return False
        return plan.answer_type == "thematic_research" and not plan.companies and not plan.topics
    def _build_hyde_query(
        self,
        question: str,
        plan: QuestionPlan,
        errors: list[str],
        llm_options: dict[str, Any],
        llm_client: Any | None,
    ) -> HydeQuery:
        """生成 HYDE 检索 query，失败时回退原问题。"""
        base_query = normalize_query_text(question)
        query_mode = self.hyde_query_mode
        if not self.enable_hyde:
            return HydeQuery(
                enabled=False,
                source="disabled",
                query_mode=query_mode,
                retrieval_query=base_query,
            )
        if llm_client is None or not (hasattr(llm_client, "chat_text") or hasattr(llm_client, "chat_messages")):
            return HydeQuery(
                enabled=True,
                source="fallback_no_llm",
                query_mode=query_mode,
                retrieval_query=base_query,
                error="LLM client unavailable",
            )
        prompt = build_hyde_prompt(base_query, plan, max_chars=self.hyde_max_chars)
        try:
            if hasattr(llm_client, "chat_text"):
                content = llm_client.chat_text(
                    system_prompt=HYDE_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=0.0,
                    **llm_options,
                )
            else:
                response = llm_client.chat_messages(
                    messages=[
                        {"role": "system", "content": HYDE_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    **llm_options,
                )
                content = getattr(response, "content", "")
            hypothetical_answer = sanitize_hyde_answer(str(content or ""), max_chars=self.hyde_max_chars)
            if not hypothetical_answer:
                return HydeQuery(
                    enabled=True,
                    source="fallback_empty",
                    query_mode=query_mode,
                    retrieval_query=base_query,
                    error="empty HYDE answer",
                )
            retrieval_query = build_hyde_retrieval_query(
                base_query,
                HydeQuery(
                    enabled=True,
                    source="llm",
                    query_mode=query_mode,
                    hypothetical_answer=hypothetical_answer,
                    retrieval_query=base_query,
                ),
            )
            return HydeQuery(
                enabled=True,
                source="llm",
                query_mode=query_mode,
                hypothetical_answer=hypothetical_answer,
                retrieval_query=retrieval_query,
            )
        except Exception as exc:
            message = f"HYDE generation failed: {exc}"
            errors.append(message)
            return HydeQuery(
                enabled=True,
                source="fallback_error",
                query_mode=query_mode,
                retrieval_query=base_query,
                error=str(exc),
            )
    def _hyde_retrieval_query(self, question: str, hyde_query: HydeQuery | None) -> str:
        """将任意检索问题与本轮 HYDE 假想答案组合。"""
        return build_hyde_retrieval_query(question, hyde_query)
    def _generate_display_cypher(
        self,
        question: str,
        plan: QuestionPlan,
        errors: list[str],
        llm_options: dict[str, Any],
        llm_client: Any | None,
    ) -> GeneratedCypher:
        """根据问题规划生成 Cypher 查询语句（三级降级策略）。
        1. CSV 图谱模式 → 使用 pseudo_cypher_for_plan（基于计划直接构建伪查询）
        2. 模板模式（LLM Cypher 未启用或无 LLM）→ template_cypher_for_plan
        3. LLM 模式 → generate_cypher 让 LLM 动态生成，失败时回退到模板
        Args:
            question: 用户问题
            plan: 查询计划
            errors: 错误收集列表
            llm_options: LLM 调用参数
            llm_client: LLM 客户端
        Returns:
            GeneratedCypher（包含 cypher 语句、参数、来源标记）
        """
        if self.status.graph_backend == "csv" or self.graph_client is None:
            return GeneratedCypher(
                cypher=pseudo_cypher_for_plan(plan, limit=self.graph_limit),
                params={
                    "companies": plan.companies,
                    "topic": plan.expanded_topics[0] if plan.expanded_topics else "",
                },
                source="question_plan_csv",
            )
        if not self.enable_llm_cypher or llm_client is None:
            return template_cypher_for_plan(plan, limit=self.graph_limit)
        try:
            return generate_cypher(
                question,
                client=llm_client,
                enable_llm=self.enable_llm_cypher,
                limit=self.graph_limit,
                llm_options=llm_options,
            )
        except Exception as exc:
            errors.append(f"Cypher generation failed: {exc}")
            return template_cypher_for_plan(plan, limit=self.graph_limit, error=str(exc))
    def _query_graph(
        self,
        generated: GeneratedCypher,
        plan: QuestionPlan,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """执行图查询，获取结构化关系数据。
        支持 CSV 和 Neo4j 两种后端。Neo4j 查询失败时自动降级到 CSV 图谱。
        Args:
            generated: 生成的 Cypher 查询
            plan: 查询计划
            errors: 错误收集列表
        Returns:
            图查询结果记录列表
        """
        if self.status.graph_backend == "csv" and self.csv_graph is not None:
            return search_csv_graph(self.csv_graph, plan, limit=self.graph_limit)
        if self.graph_client is None:
            if self.csv_graph is not None:
                return search_csv_graph(self.csv_graph, plan, limit=self.graph_limit)
            errors.append("Graph backend is not configured.")
            return []
        try:
            rows = self.graph_client.run_read_query(generated.cypher, generated.params, limit=self.graph_limit)
            if rows:
                return rows
            if self.csv_graph is not None:
                return search_csv_graph(self.csv_graph, plan, limit=self.graph_limit)
            return []
        except Exception as exc:
            errors.append(f"Neo4j query failed: {exc}")
            if self.csv_graph is not None:
                return search_csv_graph(self.csv_graph, plan, limit=self.graph_limit)
            return []
    def _search_rag(self, question: str, plan: QuestionPlan, errors: list[str]) -> list[RagHit]:
        """在 RAG 索引中检索非结构化文本证据。
        当问题只涉及一家公司且为风险分析或公司画像时，按公司名过滤检索。
        检索查询 = 问题 + 扩展主题词。
        Args:
            question: 用户问题
            plan: 查询计划
            errors: 错误收集列表
        Returns:
            RagHit 列表
        """
        if self.rag_index is None:
            if self.status.rag_error:
                errors.append(f"RAG index unavailable: {self.status.rag_error}")
            return []
        try:
            filters = {}
            if len(plan.companies) == 1 and plan.answer_type in {"risk_analysis", "company_profile"}:
                filters["company"] = plan.companies[0]
            query = " ".join([question, *plan.expanded_topics])
            return self.rag_index.search(query, top_k=max(self.rag_top_k, min(self.rerank_top_n, 20)), filters=filters)
        except Exception as exc:
            errors.append(f"RAG search failed: {exc}")
            return []
    def _search_research(self, question: str, plan: QuestionPlan, errors: list[str]) -> list[ResearchHit]:
        """在研究报告索引中检索结构化投研声明和摘要。
        Args:
            question: 用户问题
            plan: 查询计划
            errors: 错误收集列表
        Returns:
            ResearchHit 列表
        """
        if self.research_memory is None:
            return []
        try:
            return self.research_memory.search(
                question,
                plan,
                limit=max(self.evidence_top_n, min(self.rerank_top_n, 20)),
            )
        except Exception as exc:
            errors.append(f"Research search failed: {exc}")
            return []
    def _contextualize_question(
        self,
        question: str,
        history: list[dict[str, str]],
        errors: list[str],
        llm_options: dict[str, Any],
        llm_client: Any | None,
    ) -> str:
        """基于对话历史对用户问题进行上下文补全。
        策略（按 contextualizer_mode 决定）：
        - heuristic: 仅使用启发式规则（提取上一轮的公司名拼接到当前问题）
        - auto: 如果问题需要上下文（question_needs_context）则用 LLM，否则启发式
        - llm: 始终用 LLM 改写
        Args:
            question: 用户当前问题
            history: 归一化后的对话历史
            errors: 错误收集列表
            llm_options: LLM 调用参数
            llm_client: LLM 客户端
        Returns:
            补全后的上下文无关问题文本
        """
        fallback = heuristic_contextual_question(question, history)
        if not history or llm_client is None or self.contextualizer_mode == "heuristic":
            return fallback
        if self.contextualizer_mode == "auto" and not question_needs_context(question):
            return fallback
        prompt = build_contextualizer_prompt(question)
        try:
            if hasattr(llm_client, "chat_messages"):
                response = llm_client.chat_messages(
                    messages=[
                        {"role": "system", "content": CONTEXTUALIZER_SYSTEM_PROMPT},
                        *history,
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.0,
                    **llm_options,
                )
                return sanitize_contextual_question(response.content) or fallback
            if hasattr(llm_client, "chat_text"):
                content = llm_client.chat_text(
                    system_prompt=CONTEXTUALIZER_SYSTEM_PROMPT,
                    user_prompt=format_history_for_prompt(history) + "\n\n" + prompt,
                    temperature=0.0,
                    **llm_options,
                )
                return sanitize_contextual_question(content) or fallback
        except Exception as exc:
            errors.append(f"Question contextualization failed: {exc}")
        return fallback
    def _generate_answer(
        self,
        question: str,
        contextual_question: str,
        history: list[dict[str, str]],
        plan: QuestionPlan,
        graph_records: list[dict[str, Any]],
        evidence_cards: list[Any],
        errors: list[str],
        llm_options: dict[str, Any],
        llm_client: Any | None,
    ) -> tuple[str, str]:
        """基于多源证据生成最终答案（非流式）。
        无证据时返回 NO_EVIDENCE_ANSWER。
        有 LLM 时使用专业答案 prompt 调用 LLM 生成。
        无 LLM 时使用 fallback_professional_answer 做模板化回答。
        Args:
            question: 用户原始问题
            contextual_question: 上下文补全后的问题
            history: 对话历史
            plan: 查询计划
            graph_records: 图查询结果
            evidence_cards: 排序筛选后的证据卡片
            errors: 错误收集列表
            llm_options: LLM 参数
            llm_client: LLM 客户端
        Returns:
            (answer_text, reasoning_content) 元组
        """
        if not evidence_cards:
            return NO_EVIDENCE_ANSWER, ""
        prompt_question = question
        if contextual_question != question:
            prompt_question = f"用户当前追问：{question}\n结合历史对话改写后的检索问题：{contextual_question}"
        user_prompt = build_professional_answer_prompt(prompt_question, plan, graph_records, evidence_cards)
        if llm_client is not None and hasattr(llm_client, "chat_text"):
            try:
                if history and hasattr(llm_client, "chat_messages"):
                    response = llm_client.chat_messages(
                        messages=[
                            {"role": "system", "content": answer_system_prompt()},
                            *history,
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.2,
                        **llm_options,
                    )
                    return response.content, response.reasoning_content
                if hasattr(llm_client, "chat_text_with_metadata"):
                    response = llm_client.chat_text_with_metadata(
                        system_prompt=answer_system_prompt(),
                        user_prompt=user_prompt,
                        temperature=0.2,
                        **llm_options,
                    )
                    return response.content, response.reasoning_content
                return llm_client.chat_text(
                    system_prompt=answer_system_prompt(),
                    user_prompt=user_prompt,
                    temperature=0.2,
                    **llm_options,
                ), ""
            except Exception as exc:
                errors.append(f"LLM answer failed: {exc}")
        return fallback_professional_answer(plan, evidence_cards, graph_records), ""
    def _generate_answer_stream(
        self,
        question: str,
        contextual_question: str,
        history: list[dict[str, str]],
        plan: QuestionPlan,
        graph_records: list[dict[str, Any]],
        evidence_cards: list[Any],
        errors: list[str],
        llm_options: dict[str, Any],
        llm_client: Any | None,
        *,
        thinking_enabled: bool,
    ) -> Iterator[dict[str, Any]]:
        """流式生成答案。
        优先使用 LLM 的 stream_chat_messages 实现逐 token 输出。
        如果流式调用失败，回退到 _generate_answer 一次性生成后 chunk 输出。
        Args:
            question: 用户原始问题
            contextual_question: 上下文补全后的问题
            history: 对话历史
            plan: 查询计划
            graph_records: 图查询结果
            evidence_cards: 证据卡片列表
            errors: 错误收集列表
            llm_options: LLM 参数
            llm_client: LLM 客户端
            thinking_enabled: 是否显示思考过程
        Yields:
            answer_delta 事件（逐 chunk）或 answer_complete 事件
        """
        if not evidence_cards:
            for chunk in chunk_text(NO_EVIDENCE_ANSWER):
                yield {"type": "answer_delta", "content": chunk}
            yield {"type": "answer_complete", "answer": NO_EVIDENCE_ANSWER, "reasoning_content": ""}
            return
        prompt_question = question
        if contextual_question != question:
            prompt_question = f"用户当前追问：{question}\n结合历史对话改写后的检索问题：{contextual_question}"
        user_prompt = build_professional_answer_prompt(prompt_question, plan, graph_records, evidence_cards)
        if thinking_enabled:
            yield {"type": "progress", "stage": "answer", "message": "正在生成结论、证据和风险边界"}
        if llm_client is not None and hasattr(llm_client, "stream_chat_messages"):
            chunks: list[str] = []
            try:
                messages = [
                    {"role": "system", "content": answer_system_prompt()},
                    *history,
                    {"role": "user", "content": user_prompt},
                ]
                for chunk in llm_client.stream_chat_messages(
                    messages=messages,
                    temperature=0.2,
                    **llm_options,
                ):
                    content = str(getattr(chunk, "content", "") or "")
                    if not content:
                        continue
                    chunks.append(content)
                    yield {"type": "answer_delta", "content": content}
                answer = "".join(chunks).strip()
                if answer:
                    yield {"type": "answer_complete", "answer": answer, "reasoning_content": ""}
                    return
            except Exception as exc:
                errors.append(f"LLM answer stream failed: {exc}")
                if chunks:
                    yield {"type": "answer_complete", "answer": "".join(chunks).strip(), "reasoning_content": ""}
                    return
        # 流式失败时的降级：用非流式生成后 chunk 输出
        answer, reasoning_content = self._generate_answer(
            question,
            contextual_question,
            history,
            plan,
            graph_records,
            evidence_cards,
            errors,
            llm_options,
            llm_client,
        )
        for chunk in chunk_text(answer):
            yield {"type": "answer_delta", "content": chunk}
        yield {"type": "answer_complete", "answer": answer, "reasoning_content": reasoning_content}
# ============================================================
# 模块级辅助函数
# ============================================================
