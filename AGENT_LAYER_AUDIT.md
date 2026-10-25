# AIKA Agent 编排层测绘与批评（只读审计）

> 说明：实际行数与任务书给的不符——[agent_runner.py](aika/agent_runner.py) 805 行、[agent_tools.py](aika/agent_tools.py) 681 行、[langgraph_runner.py](aika/langgraph_runner.py) 545 行、[centralized.py](aika/agents/centralized.py) 1029 行、[research_agent.py](aika/research_agent.py) 782 行。以下行号以实际文件为准。

## 1. 真实调用链（活的对象图）

两条顶层入口：

1. HTTP 问答：`QAEngine.answer_question` ([qa_engine.py:526-562](aika/qa_engine.py#L526-L562))，`enable_agent` 默认 `True` ([qa_engine.py:243](aika/qa_engine.py#L243)) → `QAAgent(self, max_steps=...).run` ([qa_engine.py:548-556](aika/qa_engine.py#L548-L556))
2. HTTP 任务：`POST /agent/tasks` → `ResearchAgent(engine, store).run(task_type=, goal=)` ([api.py:457-463](aika/api.py#L457-L463))

向下分叉在 `QAAgent.run` ([agents/qa_agent.py:28-61](aika/agents/qa_agent.py#L28-L61))：按 `engine.agent_runner`（默认 `"langgraph"`，[qa_engine.py:245](aika/qa_engine.py#L245)、[qa_engine.py:322](aika/qa_engine.py#L322)、[agents/qa_agent.py:117-119](aika/agents/qa_agent.py#L117-L119)）二选一：

- **langgraph（默认）**：`LangGraphAgentRunner.run` ([langgraph_runner.py:83-99](aika/langgraph_runner.py#L83-L99)) → `_invoke` (137-192) → `_build_graph` ([194-216](aika/langgraph_runner.py#L194-L216))，8 节点 1 条件环：
  `_plan_node`(218-237) → `_dispatch_node`(239-258) → `_query_wave_node`(260-275) → `_graphrag_join_node`(277-297) → `_review_node`(299-327) → `_route_after_review`(329-334) → 覆盖不足回 dispatch，否则 `_summarize_node`(336-390) → `_verify_answer_node`(392-528) → END
- **legacy**：`AgentRunner.run` ([agent_runner.py:65-111](aika/agent_runner.py#L65-L111)) → `_plan`(277) → `_retrieve`(325) → `_supplement`(382) → `_verify_and_answer`(474)

真实编排者二分为：**图壳** `LangGraphAgentRunner`（[langgraph_runner.py](aika/langgraph_runner.py)）+ **决策大脑** `CentralizedCoordinator`（[centralized.py:231-839](aika/agents/centralized.py#L231-L839)）。`QAAgent` 是 139 行路由壳，`ResearchAgent` 是任务前台。

**没有真正的 ReAct 循环。** `AgentRunner` 是固定 4 阶段流水线，唯一循环是 `_supplement` 的 `while coverage.should_continue`（[agent_runner.py:393-472](aika/agent_runner.py#L393-L472)）；`AgentTraceStep(step/phase/thought/action/observation)`（[agent_runner.py:28-45](aika/agent_runner.py#L28-L45)）只是 ReAct 形状的日志格式，不构成控制流。

## 2. 三套系统：谁活着

| 系统 | 做什么 | 入口 | 谁 import（grep 证据） | 状态 |
|---|---|---|---|---|
| [aika/agent_runner.py](aika/agent_runner.py) | 单进程顺序 4 阶段流水线（先 graph/rag/research/semantic/graphrag 全取，再补检、再 rank/generate/verify） | `AgentRunner.run` ([65](aika/agent_runner.py#L65)) | `agents/qa_agent.py:38,73`（仅 legacy 分支）；`langgraph_runner.py:12-18`（当父类+复用 helper）；`agents/centralized.py:14-20`（复用 merge_* 与 AgentRetrievalState）；`tests/test_agent_phase3.py:1` | **半活**：`run()` 仅 `QA_AGENT_RUNNER=legacy` 可达；其 `_build_result`/merge_*/`build_supplemental_question` 被默认路径复用 |
| [aika/langgraph_runner.py](aika/langgraph_runner.py) | LangGraph StateGraph，中心化并行 | `LangGraphAgentRunner.run` ([83](aika/langgraph_runner.py#L83)) | **只有** `agents/qa_agent.py:48,85` | **活（默认）** |
| [aika/agents/](aika/agents/__init__.py) | QAAgent 路由 + ResearchAgent 任务前台 + centralized 多智能体 + planner/coverage/verification/executor 确定性内核 + store/models | `QAAgent.run`、`ResearchAgent.run` | `qa_engine.py:39,549,590`；`api.py:17-18`；`cli.py:13-14`；`langgraph_runner.py:20-29`；`agent_runner.py:10,16,219,535`；`agent_tools.py:16,679`；`scripts/evaluate_agent_tasks.py:15-16` | **活** |

`aika/langchain_tools.py` 只被 `langgraph_runner.py:29` 引用，且仅用于把工具名塞进 `diagnostics["langchain_tools"]`（[langgraph_runner.py:185](aika/langgraph_runner.py#L185)）；其 docstring 自认是"for future agent/tool-selection work"（[langchain_tools.py:20](aika/langchain_tools.py#L20)）——**无 LLM 选工具，Adapter 是纯装饰**。

## 3. centralized.py（1029 行）枚举

- 常量：`AGENT_TYPES=("graph","rag","research","semantic","graphrag")` (48)、`LLM_METHODS` (49-55)
- `LLMBudgetExhausted` (58)
- 数据类：`AgentAssignment` (62-72)、`AgentResult` (75-96, `diagnostic()`)、`EvidenceCandidate` (99-119, `prompt_payload()`)、`ReviewReport` (122-141)、`EvidenceCardDraft` (144-151)
- `CentralLLMBudget` (154-204)：线程安全 LLM 调用预算，`reserve(role, method)`/`note_fallback`/`diagnostics`
- `RoleLLMClient` (207-228)：`__getattr__` 代理并在 `LLM_METHODS` 上计费
- **`CentralizedCoordinator` (231-839)**：`dispatch` (253-309, LLM 主管出 JSON 指派→`validate_assignments`→确定性兜底)、`execute_wave` (311-371, `ThreadPoolExecutor`+`wait(timeout)`，超时置 `status="timeout"`)、`join_results` (373-437)、`build_candidates` (439-460)、`review` (462-540, LLM 审核→确定性兜底)、`summarize` (542-649, LLM 归纳+risk 卡兜底注入)、`diagnostics` (651-661)、`available_agents` (663-673)、`_fallback_assignments` (675-694)、`_run_assignment_with_metrics` (696-709)、`_run_assignment` (711-790, 按 agent_type 分派工具)、`_rewrite_query` (792-819)、`_safe_json` (821-839)
- 模块函数：`validate_assignments` (842-878)、`merge_graphrag_results` (881-905)、`merge_review_coverage` (908-947)、`validate_drafts` (950-969)、`validate_conflicts` (972-983)、`candidate_id` (986-989)、`clean_ids`/`clean_strings` (992-1008)、`shorten` (1011)、`result_count` (1018-1029)

**是的，这是唯一真正的多智能体实现**：LLM 主管分派 → 5 类检索 Agent 并发 → LLM 审核 → LLM 归纳，全程受 `CentralLLMBudget` 约束。但它是"LLM 选检索员"，不是"Agent 各自规划"——每个 worker 只执行一个固定工具调用（[centralized.py:744-778](aika/agents/centralized.py#L744-L778)）。

## 4. 工具层三份清单

**A. `AgentTools`（[agent_tools.py](aika/agent_tools.py)，真实执行）**：`contextualize_question(question, history)`(92) / `plan_question(question)`(118) / `prepare_cypher(question, plan)`(156) / `build_hyde_query(question, plan)`(185) / `query_graph(generated, plan)`(204) / `search_rag(question, plan)`(221) / `search_research(question, plan)`(238) / `search_semantic(question, plan)`(255) / `run_graphrag(question, plan, graph_records)`(284) / `rank_evidence(research_hits, graph_records, rag_hits, semantic_hits, plan, graphrag_result=None)`(319) / `generate_answer(question, contextual_question, history, plan, graph_records, evidence_cards)`(406) / `verify_answer_support(answer, plan, evidence_cards, raw_cards, question="")`(445) / `supplemental_plan(plan, question, companies=None)`(475)

**B. `default_tool_registry()`（[agents/tools.py:75-161](aika/agents/tools.py#L75-L161)，13 个 `AgentToolSpec`）**：`contextualize_question`(79)、`plan_question`(86)、`query_graph`(93)、`search_rag`(99)、`search_research_claims`(105)、`search_segment_dossiers`(111)、`search_semantic_index`(117)、`graphrag_retrieve`(124)、`rerank_evidence`(130)、`rank_evidence`(137)、`verify_answer_support`(143)、`detect_evidence_gaps`(149)、`build_research_outputs`(155)

**C. `build_langchain_tools()`（[langchain_tools.py:14-80](aika/langchain_tools.py#L14-L80)，8 个 `StructuredTool`）**：`contextualize_question`(23)、`plan_question`(29)、`prepare_cypher`(35)、`query_graph`(41)、`search_rag`(47)、`search_research_claims`(53)、`search_semantic_index`(59)、`graphrag_retrieve`(65)

**重复（同一能力 2-3 个名字）**：

| 能力 | A | B | C |
|---|---|---|---|
| 图谱检索 | `query_graph`(204) | `query_graph`(93) | `query_graph`(41) |
| RAG | `search_rag`(221) | `search_rag`(99) | `search_rag`(47) |
| 研究记忆 | `search_research`(238) | `search_research_claims`(105) | `search_research_claims`(53) |
| 语义索引 | `search_semantic`(255) | `search_semantic_index`(117) | `search_semantic_index`(59) |
| GraphRAG | `run_graphrag`(284) | `graphrag_retrieve`(124) | `graphrag_retrieve`(65) |
| 改写 | `prepare_cypher`(156) | — | `prepare_cypher`(35) |

B 里 `search_segment_dossiers`(111)、`rerank_evidence`(130)、`detect_evidence_gaps`(149)、`build_research_outputs`(155) 在 `AgentTools` 中**没有对应方法**；`build_hyde_query`(185)、`generate_answer`(406) 是真实工具却不在任何注册表里。`detect_evidence_gaps` 仅以手工构造的 `AgentToolCall` 出现（[agent_runner.py:714-727](aika/agent_runner.py#L714-L727)）。

**更关键：注册表是死的。** `register_executor` 全仓仅被 `tests/test_agent_tasks.py:162` 调用，生产代码从不注册，因此 `ToolRegistry.execute` 永远返回 `"No executor registered for tool: X"`（[agents/tools.py:39-41](aika/agents/tools.py#L39-L41)）。13 个 spec 纯属元数据。

## 5. 任务类型如何穿透代码（5 处注册表，互不相通）

代码里的真实名字是 `research_brief / company_compare / company_profile / risk_review / evidence_gap_audit`（[agents/research_agent.py:26-32](aika/agents/research_agent.py#L26-L32)），**不存在** `comparison`、`evidence_gaps` 字面量。

1. `SUPPORTED_TASK_TYPES` + `TASK_SPECS`（[agents/research_agent.py:224-270](aika/agents/research_agent.py#L224-L270)）：每型一个 `normalizer` + `output_schema` + 准备动作
2. `build_task_outputs` 的 if/elif 链（[agents/research_agent.py:362-408](aika/agents/research_agent.py#L362-L408)）：每型重排 `task_outputs`
3. `required_coverage_for_plan`（[agents/planner.py:91-103](aika/agents/planner.py#L91-L103)）：把 `QuestionPlan.answer_type`（另 6 值：`topic_to_company/company_compare/risk_analysis/industry_bottleneck/company_profile/thematic_research`，[question_planner.py:175-182](aika/question_planner.py#L175-L182)）映射到 5 个 coverage 名
4. `QueryRouter.route`（[graphrag.py:141-153](aika/graphrag.py#L141-L153)）：映射到 `metric_only/company_compare/risk_review/company_profile/company_exposure/global_causal`
5. `evidence_gap_list`（[aika/research_agent.py:228](aika/research_agent.py#L228)）与 `select_*_cards`（[professional_qa.py:363-391](aika/professional_qa.py#L363-L391)）第三次按 `answer_type` 分支

**要害**：`task_type` 从不进入执行层。`ResearchAgent.run` 把 `goal` 拼成一句自然语言问题（[agents/research_agent.py:65](aika/agents/research_agent.py#L65)、172-221）后调 `QAAgent.run`（93-97），类型只在最后打包时复用。所以"任务类型"= 提示词模板 + 输出 schema，不是执行路径。

## 6. 具体冗余

- **两套检索编排**：`AgentRunner` 顺序全取（`_retrieve` 325-380）vs `CentralizedCoordinator.execute_wave` 并发分派（311-371）；同一功能两实现，靠 `agent_runner` 开关切换
- **`run_stream` 复制整段生成/校验**：`AgentRunner.run_stream` 在 163-251 内联重写了 `_verify_and_answer`（174-267）的 rank→generate→verify→limited-answer 逻辑
- **三个 `result_count`**：[agents/tools.py:63-72](aika/agents/tools.py#L63-L72)、[agents/executor.py:115-124](aika/agents/executor.py#L115-L124)、[centralized.py:1018-1029](aika/agents/centralized.py#L1018-L1029)
- **四套预算**：`AgentBudget`([planner.py:15-21](aika/agents/planner.py#L15-L21))、`ToolBudget`([executor.py:12-31](aika/agents/executor.py#L12-L31))、`CentralLLMBudget`([centralized.py:154](aika/agents/centralized.py#L154))、`CountingLLMClient`（agent_runner 内）
- **死代码**：`AgentTaskPlan.subtasks` / `tools_for_coverage`（[planner.py:72-88](aika/agents/planner.py#L72-L88)、116-121）产出的工具名字符串无人解析；`AgentState`([models.py:81-147](aika/agents/models.py#L81-L147)) 仅测试使用；`BaseAgent`([base.py](aika/agents/base.py)) 只有 `QAAgent` 继承且无共享逻辑；`AgentRunner.run()` 默认路径不可达
- **`AgentTools` 被实例化两次/轮**：planning（[langgraph_runner.py:150-160](aika/langgraph_runner.py#L150-L160)）与 answering（396-401）各建一个，各自持有 `ToolExecutor` 与 errors 列表
- **graphrag 双入口**：`tools.run_graphrag`(284) 与 `centralized._run_assignment` 里直接 `retrieve_graphrag(...)`(760-768)，后者绕开前者

## 7. 简化机会（按性价比）

| # | 动作 | 收益 | 工作量 |
|---|---|---|---|
| 1 | 删除 `default_tool_registry` + `ToolRegistry` + `AgentToolSpec`（13 spec/0 executor） | 少 161+52 行死元数据，消除"工具已注册"的错觉 | 0.5 天 |
| 2 | 删除 `langchain_tools.py` 及 `diagnostics["langchain_tools"]` | 114 行装饰代码 | 0.5 天 |
| 3 | 统一工具命名为 `AgentTools` 一套，`search_research_claims/search_semantic_index/graphrag_retrieve` 三个别名归一 | 消除 3 套命名、23 处不一致 | 1 天 |
| 4 | 删 `AgentRunner.run/run_stream` 与 `QA_AGENT_RUNNER=legacy` 分支，保留其为 base/helper 类 | 少 ~330 行双实现 + 1 个配置开关 | 1-2 天（需回归） |
| 5 | `run_stream` 改为复用 `_verify_and_answer` 而非内联复制 | 去重 ~90 行，修 "流式/非流式行为漂移" | 1 天 |
| 6 | 把 5 处 answer_type/task_type 分支收敛成 1 张注册表（type → coverage + route + 输出 schema + 提示词） | 消除类型语义漂移 | 2-3 天 |
| 7 | 统一预算：`CentralLLMBudget` 为唯一 LLM 计数器，`AgentBudget/ToolBudget` 降为参数 | 少 3 个类、可解释成本 | 1 天 |
| 8 | `research_agent.py`(782 行) 与 `agents/research_agent.py`(570 行) 同名不同职，重命名（`report_builder.py` / `task_service.py`） | 消除最易误读的一处 | 0.5 天 |
| 9 | `agent_tools.py` 里 `cards_from_*`(545-653) 迁到 `professional_qa.py`，工具模块只留调用边界 | 层次清晰 | 1 天 |
