# AIKA 问答合成层 / 报告产出层 / 评测 / 测试 审计报告

审计范围：`aika/qa_engine.py`、`aika/professional_qa.py`、`aika/question_planner.py`、`aika/research_claims.py`、`aika/research_agent.py`、`aika/report/*`、`aika/report_type.py`、`aika/eval/*`、`data/eval/`、`scripts/`、`tests/`。编排层（`agents/*`、`centralized`、`agent_tools`、`langgraph_runner`）已有 `AGENT_LAYER_AUDIT.md`，本报告只在与合成层耦合处引用，不重复测绘。

---

## 0) 行数更正表

| 任务书断言 | 实测 | 结论 |
|---|---|---|
| `aika/` 94 模块 31,243 行 | 94 个 `.py`，**30,748 行** | 行数偏大 495 行，模块数正确 |
| `aika/qa_engine.py` 2,625 行 | **2,624 行**（104,433 B，纯 LF，文件末尾无换行） | 差 1 行 |
| qa_engine 单向依赖 16 个内部模块 | 顶层 `import` 块 `aika/qa_engine.py:33-60`，**11 个内部模块**（cypher_generator / curated_graph / extraction_schema / frontend_data / llm_client / neo4j_client / agents.verification / professional_qa / postgres_retrieval / question_planner / rag_index） | 依赖数偏大 |
| `log/plan.md` 存 P0–P6 计划 | `log/` 只有 `direction.md`、`log.md`、`v0.0.0-v0.0.1plan.md`；P0–P6 实际在**仓库根 `plan.md`（516 行）** | 路径错误 |
| `ClaimReviewRequest` 17 字段 | **18 字段**（`aika/api.py:65-83`） | +1 |
| `tests/` 34 文件 | 34 文件，**5,673 行，228 个 `test_` 函数** | 新增口径 |
| `pytest --collect-only` 65 collected / 22 errors | 复现一致；但 `tests/test_evidence_cards_ux.py` 单独执行亦 collection error，22 与 23 的口径未完全对齐（**未验证**） | 见 §6 |
| 报告层仅 `aika/report/` | 另有 `aika/report_type.py`（109 行，真实存在）与 `aika/research_agent.py:395-556` 一整套并行 markdown 组装器 | 报告层范围被低估 |

---

## 1) qa_engine 方法清单与拆分映射

文件结构：头部 docstring + imports `1-181`；`CountingLLMClient` `182-199`；`QAEngine` `202-1577`（1,376 行）；模块级函数 `1579-2624`（1,046 行）。**类只占 52%，52% 的代码是没人调用的模块级函数**。

### 1.1 类方法

| 方法 | 行号 | 实际职责 | 目标模块 |
|---|---|---|---|
| `CountingLLMClient` | 182-199 | LLM 调用计数（`TRACKED_METHODS` :183，`__getattr__` :189） | `observability/llm_counter.py` |
| `__init__` | 216-341 | 25 个构造参数 + 全部配置归一化（:303-341） | `engine/config.py` + `engine/factory.py` |
| `from_env` | 342-514 | env 解析、后端选择、Postgres 装配（:391-402） | `engine/factory.py` |
| `close` | 515-525 | 资源释放 | `engine/factory.py` |
| `answer_question` | 526-563 | **入口分流**：`if self.enable_agent: QAAgent(...).run(...)`（:548-556）否则 workflow | `engine/facade.py` |
| `answer_question_stream` | 564-609 | 同上流式分流（:589-598） | `engine/facade.py` |
| `_prepare_conversation_history` | 610-692 | 历史压缩编排 | `pipeline/history.py` |
| `_answer_question_workflow` | 693-889 | **11 阶段流水线主控**（纯编排，197 行） | `pipeline/answer_pipeline.py` |
| `_answer_question_stream_workflow` | 890-1120 | 同流水线**第二份实现**（231 行） | 与上合并，删一份 |
| `_should_use_llm_planner` | 1121-1138 | 触发条件（仅 `thematic_research` 且零实体，:1138） | `pipeline/planning.py` |
| `_build_hyde_query` | 1140-1222 | HYDE 生成 + 三级回退 | `pipeline/hyde.py` |
| `_hyde_retrieval_query` | 1223-1226 | **纯转发**到 `build_hyde_retrieval_query` | 删除（内联） |
| `_generate_display_cypher` | 1227-1272 | Cypher 三级降级（CSV→pseudo→template→LLM） | `retrieval/ports.py` |
| `_query_graph` | 1274-1310 | 图查询 + Neo4j→CSV 回落 | `retrieval/ports.py` |
| `_search_rag` | 1312-1338 | RAG 检索 + **内嵌业务规则**：仅单公司且 `answer_type ∈ {risk_analysis, company_profile}` 才加 company 过滤（:1332） | `retrieval/ports.py`（规则上移 `retrieval/filters.py`） |
| `_search_research` | 1340-1362 | claims 检索 | `retrieval/ports.py` |
| `_contextualize_question` | 1363-1417 | 追问改写 + 4 条回退路径（:1388-1392） | `pipeline/contextualizer.py` |
| `_generate_answer` | 1418-1486 | **答案合成**（prompt 拼接 :1452-1455、三选一 LLM 分支 :1456-1484） | `answer/composer.py` |
| `_generate_answer_stream` | 1487-1577 | 同一件事的流式第二份 | 与上合并 |

### 1.2 模块级函数（1,046 行，按职责）

| 函数（行号） | 职责 | 目标模块 / 处置 |
|---|---|---|
| `build_answer_prompt` 1585；`build_evidence` 2185；`graph_records_to_subgraph` 2225；`detect_unsupported_terms` 2496；`normalize_for_support` 2534；`unique_texts` 2546；`fallback_answer` 2597 | **死代码**（全仓 grep：定义处之外零引用；`normalize_for_support`/`unique_texts` 仅被死函数 `detect_unsupported_terms` 调用，:2511-2531） | **删除，共 183 行** |
| `normalize_contextualizer_mode` 1608 / `normalize_hyde_query_mode` 1623 / `normalize_query_text` 1631 / `normalize_agent_max_steps` 1704 / `normalize_agent_runner` 1720 | 配置归一化（后两个被 `api.py:30,124,128` 使用） | `engine/config.py`（60 行） |
| `build_hyde_prompt` 1636 / `sanitize_hyde_answer` 1651 / `build_hyde_retrieval_query` 1664 / `hyde_diagnostics` 1677 | HYDE，`hyde_diagnostics` 被 `agent_runner.py:617,662` 使用 | `pipeline/hyde.py`（155 行） |
| `record_timing` 1735 / `stream_progress` 1813 / `describe_plan_progress` 1826 / `chunk_text` 1851 | 进度与计时；`stream_progress`(7 处)/`chunk_text`(4 处)/`describe_plan_progress`(2 处) 被 agent_runner/langgraph_runner 使用 | `pipeline/progress.py`（115 行） |
| `build_llm_options` 1795 / `template_cypher_for_plan` 1746（内嵌 `industry_bottleneck` 关系补全，:1761） | LLM 选项 / Cypher 模板 | `llm/options.py` / `retrieval/cypher_template.py`（50 行） |
| `normalize_conversation_history` 1870 / `normalize_conversation_messages` 1900 / `trim_history_to_chars` 1916 / `fit_summary_and_recent_to_budget` 1939 / `compress_history_with_llm` 1956 / `history_chunks` 1996 / `request_history_summary` 2018 / `sanitize_history_summary` 2053 / `format_history_for_prompt` 2167 | 历史预算与压缩 | `pipeline/history.py`（250 行） |
| `build_contextualizer_prompt` 2062 / `heuristic_contextual_question` 2078 / `question_needs_context` 2103 / `sanitize_contextual_question` 2146 | 追问改写 | `pipeline/contextualizer.py`（160 行） |
| `answer_subgraph` 2255 / `add_dossier_edges` 2380（解析「公司敞口：/技术机理：/瓶颈：/领先指标：/风险与反证：」五种中文前缀 :2398-2424）/ `label_for_claim` 2427 / `target_for_claim` 2454 / `target_type_for_claim` 2477 | claim→图边映射（业务规则，被 `agent_runner.py:617,625` 使用） | `graph/subgraph_builder.py`（235 行） |
| `ensure_relation_cards` 2565 | 风险类证据补齐（被 `agent_tools.py:333,350,365,386` 使用） | `answer/evidence_policy.py`（32 行） |

**拆分后目标模块与预估行数**（合计 ≈2,430，去掉死码 183 与重复流水线 ≈180）：

| 新模块 | 行数 |
|---|---|
| `engine/facade.py`（入口分流） | 90 |
| `engine/factory.py`（`__init__`+`from_env`+`close` 拆配置对象） | 260 |
| `engine/config.py` | 60 |
| `pipeline/answer_pipeline.py`（合并双份流水线） | 250 |
| `pipeline/history.py` | 250 |
| `pipeline/contextualizer.py` | 160 |
| `pipeline/hyde.py` | 155 |
| `pipeline/planning.py` | 40 |
| `pipeline/progress.py` | 115 |
| `retrieval/ports.py` + `retrieval/cypher_template.py` + `filters.py` | 240 |
| `answer/composer.py`（合并双份合成） | 130 |
| `answer/evidence_policy.py` | 32 |
| `graph/subgraph_builder.py` | 235 |
| `observability/llm_counter.py` | 20 |

### 1.3 纯转发与薄包装

`_hyde_retrieval_query`（1223-1226，4 行，仅调用 `build_hyde_retrieval_query`）、`_search_research`（1340-1362，23 行，仅拼参数调 `self.research_memory.search`）、`close`（515-525，11 行）、`_should_use_llm_planner`（1121-1138，18 行）都是无状态薄包装；`answer_question`/`answer_question_stream`（526-609，共 84 行）也只是"看 `enable_agent` 选 A 或 B"的分流壳，真正的分支知识是 2 个字符串。这类方法在拆分时应直接内联进调用点，不值得单开模块。

另有 3 处**本该在别处的业务规则被焊死在 qa_engine 里**：`_search_rag:1332` 的 `answer_type ∈ {risk_analysis, company_profile}` 才加公司过滤（属检索策略，却在编排层）；`template_cypher_for_plan:1761` 为 `industry_bottleneck` 硬补 4 条关系（属 Cypher 生成，`professional_qa.py:744` 已有 `pseudo_cypher_for_plan` 同职责）；`answer_subgraph:2398-2424` 用 5 个中文前缀（"公司敞口：/技术机理：/瓶颈：/领先指标：/风险与反证："）做字符串解析来推断图边（属 claims 语义解析，应在 `research_claims.py`）。

**结论**：qa_engine 的真正问题不是"2624 行太大"，而是 **65% 的代码属于 5 个互不相关的职责域**（配置、检索、历史、合成、图装配），其中 183 行是死码、约 430 行是同一流水线的两份拷贝、84 行是分流壳。可无风险地先删 183 行死码（见 §8 第 1 项）。

---

## 2) 答案合成链路

**关键前提**：`enable_agent` 默认 `True`（`aika/qa_engine.py:243`），因此生产默认路径是 `answer_question` → `QAAgent`（:548-556，编排层已有报告）；**下面 11 阶段 workflow 是 `enable_agent=False` 的确定性路径**，也是测试与离线评测走的路径。

```
answer_question (qa_engine.py:526)
 └ _answer_question_workflow (:693)
   ① _prepare_conversation_history (:724 → :610)         [LLM ?] 历史压缩 compress_history_with_llm(:1956)
   ② _contextualize_question      (:734 → :1363)         [LLM ?] auto 模式下仅 question_needs_context 为真才调 (:1391)
   ③ heuristic_plan_question      (:739)                 [0] 若 _should_use_llm_planner 则 plan_question(:741)
   ④ _build_hyde_query            (:753 → :1140)         [LLM 1] chat_text/chat_messages (:1170/:1177)
   ⑤ _generate_display_cypher     (:759 → :1227)         [LLM ?] 需 enable_llm_cypher，默认 False(:226)
   ⑥ _query_graph                 (:766 → :1274)         [0]
   ⑦ _search_rag                  (:771 → :1312)         [0]
   ⑧ _search_research             (:776 → :1340)         [0]
   ⑨ 证据合并/排序/编号            (:781-789)             [0] rank_evidence_cards(professional_qa.py:335)
   ⑩ _generate_answer             (:794 → :1418)         [LLM 1] 见下
   ⑪ verify_answer_support        (:808 → agents/verification.py:56) [0] 纯确定性校验
      失败 → build_evidence_limited_answer (:810) 且二次校验 (:811-812)
   产物：legacy_evidence_rows(:816) / answer_subgraph(:820) / build_research_outputs(:822-828)
```

**LLM 调用次数**：默认配置（`enable_llm_planner=False` :227、`enable_llm_cypher=False` :226、`enable_hyde=True` :240、`contextualizer_mode="auto"` :228、`history_compression_enabled=True` :237）下，单轮 **2 次**（HYDE + 答案），有追问时 **3 次**，历史超预算再 **+1**；上限 **6 次**（全开时）。次数由 `CountingLLMClient`（:182-199）统计并写入 `diagnostics["llm_calls"]`（:866）。

**提示词拼接点（5 处，其中 1 处是废弃模板）**：

1. `build_professional_answer_prompt`（`aika/professional_qa.py:506-528`）：payload=`question+plan+graph_records[:30]+cards[:12]`，**四条硬编码规则内嵌在函数体**（:518-523：只用证据、必须标 `[E1]`、固定七段结构、缺证据写"当前证据不足"）。
2. `build_answer_prompt`（`qa_engine.py:1585`，注释自称"旧版格式，用于兼容"）：**死代码**，与 (1) 是两套冲突模板——若未来有人调用它，输出结构（四段）与 (1)（七段）互相矛盾。
3. HYDE prompt：`build_hyde_prompt`（:1636）+ `HYDE_SYSTEM_PROMPT`（:1170 引用）。
4. 追问改写 prompt：`build_contextualizer_prompt`（:2062）。
5. 历史压缩 prompt：`compress_history_with_llm`（:1956）/`request_history_summary`（:2018）；planner prompt 另有 `question_planner.py:123`。

**确定性降级路径（无 LLM 时）**：真正的降级不在 qa_engine，而在 `aika/professional_qa.py:531 fallback_professional_answer`（6 分支，见 §7）。`qa_engine.py:1485` 只在 `llm_client is None` 时调用它；`qa_engine.py:2597 fallback_answer`（基于 graph_records 前 8 条拼句）**从未被调用**，是早期版本的残留。另有两条确定性短路：空证据 → `NO_EVIDENCE_ANSWER`（:1450、:1521）；校验 fail → `build_evidence_limited_answer`（:810、:1035）。

**证据合并顺序即语义优先级**：`raw_cards = research + graph + rag`（:781-785）决定同分卡的先后，`rank_evidence_cards`（`professional_qa.py:335`）重排后统一在 `:789` 分配 `[E1..En]`。这意味着"引用编号"不是稳定标识而是排序产物——重构时若改变合并顺序，历史答案里的 `[E3]` 会指向不同证据。此契约**没有任何测试保护**（`test_rag_qa.py` 只断言 `NO_EVIDENCE_ANSWER` 与证据非空）。

---

## 3) 报告层能力矩阵（`plan.md` P0–P6 vs 落地）

| 计划 | 要求 | 代码落点 | 状态 |
|---|---|---|---|
| P0 | Executive Page 四层信息架构 | `aika/report/render_markdown.py:15-27`（9 节，`##` 平铺）+ `templates/report.html.j2`（148 行） | **部分落地**：有层级，但 9 节与计划 4 层不对应，无"层"概念 |
| P1 | 按 coverage 自动降级四类报告 | `aika/report_type.py:37-47` + `report/builder.py:54` | **落地**，但 `:38 del company_coverage` —— 三个输入参数只用了两个，`plan.md` 伪代码里的 `company_coverage` 从未生效（**死参数**） |
| P2 | `spec.py`/`builder.py`/`render_html`/`render_markdown`/`charts/*` | `spec.py`(118)、`builder.py`(217)、`render_html.py`(14)、`render_markdown.py`(199)、`charts/{heatmap,evidence_bar,flow_map,freshness,common}.py` | **结构落地**，但 `templates/coverage_audit.html.j2`(41 行) 与 `research_brief.html.j2`(31 行) **全仓零引用**（`render_html.py:20` 固定用 `report.html.j2`）⇒ "低覆盖选 audit 模板"未实现 |
| P3 | 四张图（含 0–5 分规则） | `charts/heatmap.py:63-79`（:71 五分）、`evidence_bar.py`、`flow_map.py`、`freshness.py` | **落地**，五分规则真实存在（测试失败是日期炸弹，见 §6） |
| P4 | 证据卡 `<details>` 折叠 | 模板中 `<details>` 出现 **0 次**（4 个 j2 全查）；`render_markdown.py:164-183` 用 `### [E1]` 标题 | **未落地** |
| P5 | 风险雷达图 + 技术路线对比表 | 无 radar 相关代码（模板 grep `radar` = 0） | **未落地**（计划已标"第二阶段"） |
| P6 | 回归测试与离线 smoke | `tests/test_report_{spec,type,builder,charts}.py` 存在且可收集 10 条 | **落地**，但 `test_report_renderers.py` 与 `test_report_charts.py` 各有一条因依赖/日期失效 |

**`ReportSpec` 字段清单**（`spec.py:109-118`，`extra="forbid"` :10-11）：`report_type`、`topic`、`title`、`report_type_label`、`usability`、`coverage`（10 字段 `:14-24`）、`executive_summary`（`can_answer`/`cannot_answer`/`key_findings`，:27-30）、`charts`（`flow_map`/`company_coverage_heatmap`/`evidence_strength_bar`/`source_freshness_timeline`，:95-99）、`appendix`（`evidence_cards`/`evidence_gaps`/`company_compare_table`/`risk_checklist`，:102-106）。**冗余字段**：`builder.py:84-97` 让 `can_answer` 与 `key_findings` 取同一份 findings，前端消费时无法区分"能回答什么"与"关键发现"。

**消费者（4 条，全部实测）**：
- 前端：`web/src/types.ts:72` 定义 `ReportSpec`，`App.tsx:2248 const charts = report?.spec?.charts` —— **只消费 charts**，其余字段前端不读；
- MCP：`aika/aika_mcp/schemas.py:185`（`report_spec` 入参）+ `tools.py:457-497`（`_render_report_pdf` / `ReportSpec.model_validate`）；
- SQLite 后端导出：`aika_core/backends/sqlite_backend.py:422 build_report_spec` + `:432 render_markdown`；
- Agent 产出：`aika/research_agent.py:112-123`。

**PDF**：`render_pdf.py:27-45` → `_export_pdf_with_playwright`（:47-74，chromium `page.pdf(A4, print_background=True, margin 16/14mm)`）。**缺依赖不降级**：`playwright` 缺失直接 `raise PdfRenderError("Playwright is not installed.")`（:50-52），并附 `PLAYWRIGHT_INSTALL_FIX`（:13-16）；失败清理半成品 PDF（:76-82）。注意 `pyproject.toml:41-44` 把 playwright 放在 `[pdf]` extra，而 HTML 渲染必需的 jinja2 在核心依赖（:24）——**PDF 是可选能力，HTML 是硬依赖**，这个分层是对的。

**报告层真实能力评级**：规格与渲染骨架 = 可用（P2/P3 完整，`ReportSpec` 已有 5 类消费者）；信息架构 = 半成品（P0 四层未建模、P4 `<details>` 未实现、P5 无代码）；模板体系 = 1 用 2 死；PDF = 可用但重型（每次全量 chromium 导出，无 print 专用样式分流）。

---

## 4) claims 生命周期

**产生**（离线流水线，纯确定性，无 LLM）：`build_research_artifacts`（`research_claims.py:352`）→ `claims_from_relation`(:399) / `claim_from_relation_topic`(:427) / `claims_from_technical_chunks`(:495) → 写 `claims.csv`（24 列，:43-68）+ `segment_dossiers.jsonl`（:391-395）→ 派生 `infer_dossier_gaps`(:905) / `best_company_exposure`(:874)。

**审核接口**：`POST /research/claims/{claim_id}/review`（`api.py:691-713`）。`ClaimReviewRequest` **18 个可选字段**（:65-83），经 `model_dump(exclude_none=True)`(:697) → `normalize_claim_review`(:708 → `research_claims.py:978-1007`) → `research_memory.review_claim`(:710)。

**字段落库**：`REVIEWABLE_CLAIM_FIELDS`（`research_claims.py:70-89`）**恰好也是 18 个**，且是 `CLAIM_CSV_FIELDS` 24 列的子集 ⇒ **无孤儿字段，也无 CSV 缺列**。`normalize_claim_review` 的 `:992` 循环按白名单过滤，`review_status` 走白名单校验否则强制 `needs_review`(:1002-1003)，`companies` 走 `parse_companies`(:997)。**隐式字段**：`updated_at`、`reviewer`（:989-990）不在 18 个字段内但总会写入。

**三处审计写入，行为不一致（核心缺陷）**：
1. `PostgresResearchMemory.review_claim`（`postgres_retrieval.py:1014-1090`）：事务内 `SELECT ... FOR UPDATE`（:1024）、`apply_claim_reviews`(:1030)、重算语义向量与内容哈希(:1032-1057)、写 `claim_reviews` 审计表(:1058-1066)、更新 `research_claims` 行 ⇒ **真正落库**。
2. `ResearchMemory.review_claim`（`research_claims.py:1049-1057`）：只改内存 `self.claims[index]` ⇒ **重启即丢**。
3. `write_claim_review`（`research_claims.py:963-975`，append `claim_reviews.jsonl`）：**全仓零调用者**（tests 也 0 次）⇒ 死代码。

**结论**：CSV/SQLite 部署下前端审核"看起来成功"（返回 200 + 改后的 claim），但没有任何持久化；只有 Postgres 后端是对的。这是重构时必须先决定的分叉点：要么把 (2) 接到 (3)，要么删除 (3) 并声明"审核仅支持 Postgres"。

**审核状态语义**：`normalize_claim_review` 在未显式给 `review_status` 时默认写 `revised`（:1005-1006），意味着"只改了 reviewer_note"的审核事件也会把 claim 标成"已修订"，污染 `claim_stats.claim_type_counts`/reviewed 统计（:1065）。`reviewed_at`/`reviewer` 两列只存在于 Postgres 表（`postgres_retrieval.py:504`、`:937-939`），CSV 的 24 列里没有 ⇒ 同一套 18 字段在两种后端下落库形状不同，前端拿到的 claim 对象字段数也不同。

---

## 5) 评测体系

**两个 runner，两套数据，互不通信**：

| 组件 | 职责 | 数据 | 结果落点 |
|---|---|---|---|
| `aika/eval/runner.py:19 run_qa_benchmark` | 跑 `QAEngine.answer_question`，逐 case `score_case`(:36)，异常走 `error_case_report`(:38) | `data/eval/qa_benchmark_v1.jsonl`（50 例，24,454 B） | `EvalRunStore` → `data/eval_runs/eval_runs.jsonl`（append-only，`store.py:14`；`_latest_runs:60-78` 按 `run_id` 去重取最新） |
| `aika/eval/rag_runner.py:run_rag_retrieval_benchmark`（472 行） | 只测检索（bm25/semantic/rrf），不测答案 | `data/eval/rag_retrieval_v{1,2}.jsonl`（各 50 例） | 同 store + `review_dir` |
| `scripts/evaluate_agent_tasks.py:20-36` | 15 条硬编码 Agent 任务，`score_task`(:49-72) 只看产物字段是否齐全 | 硬编码 | **不写文件**，只 print；退出码 `:120` |

**auto_judge 的定位**：不是答案评分器，而是**检索证据的人工复核队列辅助**——`auto_judge_batch`（`auto_judge.py:231`）对单 case 的多个 chunk 一次 LLM 调用判 `grade∈{0,1,2}`（`_extract_judgments:176-224`），`auto_judge_review_queue`(:394) 处理 review 队列，`save_judgments`(:456) 落 jsonl。它服务于 `rag_retrieval` 的弱标注，与 `metrics.py:29 score_case` 的 6 指标完全独立。

**case schema 实测**（`qa_benchmark_v1.jsonl` 首行）：`case_id/category/question/expected_answer_type/expected_companies/expected_topics/required_claim_types/expected_claim_ids/forbidden_terms/refusal_expected/scoring_notes/human_score`；`human_score` 全为 `null` ⇒ 无人工基线，`metrics.py:187 metric_means` 里的 `human_score` 均值永远为空。

**指标与 case 的对齐问题**：`metrics.py:29 score_case` 产出 `claim_recall_at_k`(:55)、`evidence_precision_at_k`(:69)、`citation_validity`(:77)、`answer_groundedness`(:92)、`unsupported_claim_rate`(:117)、`automatic_score`(:125) 六个分数，但 case 里的 `required_claim_types` 只在 `card_matches_case`(:197)/`card_hits_slot`(:210) 被用到，`expected_claim_ids` 在 50 例中**全部为空数组** ⇒ 召回类指标实际退化为"claim_type + 公司 + 主题"三重匹配，测不出具体 claim 是否被检索到。`forbidden_terms` 只作用于 `is_forbidden_evidence`(:227)，不作用于答案文本 ⇒ "禁止出现的词出现在答案里"不会扣分。

**前端 `EvalView`**：`web/src/App.tsx:1003` 内联组件（`App.tsx` 共 2,983 行，**无独立视图文件**），挂载于 :557-562，读 `listEvalRuns()`(:245)→`getEvalRun()`(:276)，消费 `summary.{overall_score,pass_rate,cases,failed,warned}`(:1069-1073)、`summary.metrics`(:1082)、`category_scores`(:1093-1099)、`failed_examples`(:1108)、`results`(:1115，最多 50 行 :1150)。

**能否真的跑**：不能。
- `data/eval_runs/` 只有 `.gitkeep`(1 B) ⇒ 前端永远显示"暂无可展示的评测报告"（App.tsx:1057），仓库里从未提交过一份评测产物。
- 评测 CLI 在 `aika/cli.py:146-171`（`aika eval` / `--suite rag|agent`），但 `pyproject.toml:35` 的入口是 `aika = "aika.aika_cli:main"`，而 `aika_cli.py` **没有 eval 子命令**（:55-131 只有 init/build-index/doctor/demo/search-evidence/search-claims/validate-data/skill/mcp）；`aika/cli.py` 也**没有 `__main__` 块**（文件末 :414-416 是 `first_lines`）。全仓对 `aika.cli` 的引用只有两个测试（`tests/test_offline_demo.py:6`、`tests/test_rag_retrieval_eval.py:7`）⇒ **`aika eval` 从安装入口不可达，是孤儿 CLI**。
- 本机缺 `psycopg`/`jinja2`，`from aika.qa_engine import QAEngine` 直接失败 ⇒ 真评测连引擎都构造不出来。唯一能跑通的是 `tests/test_eval_platform.py:184-186` 用 `FakeEvalEngine` 跑 runner 本身。

**一句话结论**：评测平台是写完了的（`aika/eval/` 2,289 行、6 个指标、jsonl 存储、前端面板齐全），但没有一条端到端通路是通的——入口不可达、依赖不可用、产物从未提交。它是"可演示的骨架"而非"可用的度量"；重构时优先修入口（§8 #8）与产物（§8 #10），而不是加指标。

---

## 6) 测试现状与行为契约

**可执行性（实测）**：`python -m pytest --collect-only tests` → `65 tests collected, 22 errors`。**228 个 `test_` 函数只有 65 个被收集（28.5%）**。22 个文件在 import 期即失败，根因只有 3 条链：

| 缺失依赖 | 失败链 | 受影响测试文件（用例数） |
|---|---|---|
| `psycopg` | `postgres_retrieval.py:13` ← `qa_engine.py:52` | test_professional_qa(15)、test_rag_qa(8)、test_research_claims(4)、test_agent_runner、test_centralized_multi_agent 等 |
| `jinja2` | `report/render_html.py:7` ← `report/__init__.py:4` ← `research_agent.py:18` ← `aika_core/backends/csv_backend.py:33` | test_report_renderers(4)、test_research_agent(3)、test_evidence_cards_ux(3)、test_aika_core、test_offline_demo 等 |
| `mcp` / `fitz`(PyMuPDF) / `bs4` | 直接 import | test_aika_mcp_*(40)、test_stage2_stage3_pipeline(19) 等 |

**真实运行结果**（11 个可执行文件、61 个用例）：**33 passed / 2 failed / 26 errors**（4.97s）。

- **26 个 ERROR 全部是环境问题**：`_pytest/tmpdir.py:213 getbasetemp` → `PermissionError: [WinError 5] 拒绝访问: 'C:\Users\LENOVO\AppData\Local\Temp\dsh-DemtLQ\pytest-of-LENOVO'`。凡用 `tmp_path` 的用例在受限沙箱下必错，**不是代码缺陷**。另注：`tests/` **没有 `conftest.py`**（全仓递归搜索确认），因此没有全局 fixture、没有 marker 注册、也没有 `tmp_path` 兜底——这既是 26 个 error 的根因，也说明测试套件从未为"在受限环境里跑"做过设计。
- **2 个 FAILED 也都不是产品缺陷**（实测重跑确认）：
  - `test_embedding_semantic.py::test_embedding_index_requires_database_url`：测试期望脚本输出 `DATABASE_URL is required`，但脚本在更早的 import 阶段就崩了——`ModuleNotFoundError: No module named 'psycopg'`（`scripts/build_embedding_index.py` → `aika/postgres_retrieval.py:13`），断言在 `tests/test_embedding_semantic.py:244`。即"依赖缺失导致的假失败"，不是逻辑错。
  - `test_report_charts.py::test_company_coverage_heatmap_scores_evidence_strength`：`assert 4 == 5`。根因是**日期炸弹**：测试用 `published_at="2025"`（`tests/test_report_charts.py:31-32`）期望"新鲜"，而 `charts/common.py:93` 的 fresh 窗口是 18 个月，系统日 2026-10-25 时 2025-01-01 已 21 个月 ⇒ aging。同文件 `test_source_freshness_timeline` 显式注入 `today=date(2026,6,20)`（:82）故通过；`tests/test_evidence_cards_ux.py:13` 甚至把断言放宽成 `in {"fresh","aging"}` 来规避——**作者知道这个炸弹，选择绕开而不是修**。

**按被测模块归类**：

| 域 | 文件 | 用例 | 状态 |
|---|---|---|---|
| 报告层（spec/type/builder/charts/renderers） | 5 | 14 | 10 可跑，4 因 jinja2 不可跑 |
| 评测平台（dataset/metrics/store/runner） | 1 | 6 | 3 可跑，3 因 tmp_path error |
| QA 主链路（professional_qa / rag_qa / claims / qa_engine） | 4 | 30 | **全部不可跑** |
| Agent/编排 | 5 | 32 | 全部不可跑 |
| MCP/CLI/打包 | 5 | 58 | 全部不可跑 |
| 数据管线（stage2/3、prepare_stage1、knowledge_pack） | 4 | 32 | 全部不可跑 |
| 纯函数/前端数据（frontend_data、llm_client、verification、conversation_store、embedding） | 6 | 25 | 22 可跑 |
| 遗留（phase3/phase5、sqlite_backend、api） | 4 | 17 | 全部不可跑 |

**只测死代码/废弃路径的测试**：`tests/` 对 `markdown_executive_page`、`markdown_compare_table`、`markdown_coverage_audit`、`detect_unsupported_terms`、`fallback_answer`、`graph_records_to_subgraph`、`build_answer_prompt`、`write_claim_review` 的引用数**均为 0**（`build_evidence` 的 9 次命中实为 `build_evidence_limited_answer` 子串）。也就是说 §1.2 的 183 行死码 + `research_agent.py` 的 ~250 行死链，**没有任何测试在保护它们**，删除无需改动测试。

**端到端 vs 单元，以及测试数据来源**：真正端到端只有 3 条 pytest 用例——`test_rag_qa.py::test_qa_engine_combines_graph_and_rag_evidence`、`::test_qa_engine_returns_evidence_gap_answer_without_evidence`、`test_professional_qa.py::test_answer_question_stream_emits_progress_deltas_and_final_result`（外加非 pytest 的 `scripts/evaluate_agent_tasks.py`），**全部不可在本机执行**。其余都是单元/契约测试：报告层用手工 `EvidenceCard` 夹具（`test_report_charts.py:11-23`）或直接构造 `ReportSpec` 字典；评测层用 `FakeEvalEngine`（`test_eval_platform.py:184-186`）返回手写 dict——**这等于把 runner 的输出格式抄进测试**，runner 改字段名时测试会跟着改而不会报错，契约强度低；QA 层用 `tmp_path` 现造 CSV。**没有任何测试读 `data/` 下的真实语料**，唯一例外是 `test_eval_platform.py::test_default_benchmark_loads_50_cases` 读 `data/eval/qa_benchmark_v1.jsonl`。**也没有任何网络 mock**：所有 LLM 交互靠"传 None 或传假 client"绕过，没有 respx/httpx 级录制，所以"LLM 返回畸形 JSON"这类真实故障模式没有任何回归覆盖。

**重构必须保留的行为契约**（测试真正锁定的不变量）：

1. `classify_report_type` 双阈值：`coverage<0.3` 或 `direct_claim_ratio<0.25` → audit；`<0.6` brief；`<0.8` industry；否则 deep（`test_report_type.py` 2 条 + `test_report_builder.py:test_builder_downgrades_low_coverage_to_audit`）。**注意**：这条契约里 `company_coverage` 是死的，重构时若"修好"它会改变行为。
2. `ReportSpec` 严格性：`extra="forbid"`（`test_report_spec.py:test_report_spec_requires_core_fields`）、`appendix.evidence_cards` 必填且可序列化（`:test_appendix_evidence_cards_are_required_and_serializable`）。
3. 图表空态文案：`empty_message="当前证据不足"`（`test_report_renderers.py:test_html_renderer_outputs_hierarchy_and_empty_chart_message`）。
4. flow map 免责 caption 必须渲染（`test_report_renderers.py:test_html_renderer_outputs_flow_caption_when_chart_is_present`）。
5. PDF 渲染路径与接口：写 html + 调 playwright + 返回 dict（`test_report_renderers.py:test_pdf_renderer_writes_html_and_invokes_playwright_export`，monkeypatch 掉真实导出）。
6. 热力图 0–5 分规则（`test_report_charts.py`，但因日期炸弹当前红）。
7. benchmark 50 例、`case_id` 唯一性拒收（`test_eval_platform.py:test_default_benchmark_loads_50_cases` / `test_dataset_rejects_duplicate_case_ids`）。
8. 评分与拒答识别（`test_eval_platform.py:test_metrics_score_supported_answer` / `test_metrics_detect_refusal_quality`）。
9. run 与 feedback 的 jsonl 持久化格式（`test_eval_platform.py:test_eval_run_store_and_feedback_store_persist_jsonl`）。
10. runner 产出报告结构（`test_eval_platform.py:test_runner_saves_report_with_fake_engine`）。
11. freshness 三态（unknown/stale/其他）与放宽边界（`test_evidence_cards_ux.py:test_freshness_status_classifies_dates`）。
12. 图谱/技术→公司推断与 SVG 输出（`test_frontend_data.py` 4 条）。

---

## 7) 重复实现清单

| # | 业务规则 | 实现点（全部实测） | 差异 |
|---|---|---|---|
| 1 | **answer_type 分支** | `professional_qa.py:70-99`（图谱过滤）、`:377-388`（选卡）、`:535-608`（降级答案）、`research_claims.py:1238-1244`+`:1306`（打分权重）、`graphrag.py:145-151`+`:487`、`agents/planner.py:93-101`、`qa_engine.py:787`/`:1002`/`:1138`(planner 条件)/`:1332`(RAG 过滤)/`:1761`(Cypher 模板)、`research_agent.py:228`/`:241` | **8 个文件、14 处**；同一组枚举值被反复硬编码，`answer_type` 新增一类要改 8 处 |
| 2 | **coverage 打分** | `report/builder.py:39-41`；`research_agent.py:308-340`（`report_coverage_metrics` 自算）、`:499-503`（`agent_coverage_score`） | 三份公式，`card/(card+unsupported)` 与 `card/(card+gaps)` 口径不同 ⇒ 同一份数据在旧/新报告层给出不同覆盖率 |
| 3 | **可用性分级** | `report_type.py:54 report_usability`（0.3/0.6/0.8）；`research_agent.py:506 agent_usability_label`（同阈值） | 两份，返回同文案 |
| 4 | **结论限定语** | `report/builder.py:197 _qualify`；`research_agent.py:370 qualify_conclusion` | 两份 |
| 5 | **freshness 判定** | `report_type.py:73-88 normalize_freshness_status`；`report/charts/common.py:82-97 freshness_status`；`aika_core/evidence.py:44 freshness_status`；`builder.py:126 _aggregate_freshness` ≡ `report_type.py:63` | **4 份**，18/36 个月阈值散落 2 处 |
| 6 | **markdown 报告组装** | `report/render_markdown.py:30-183`（9 个 `_section`）；`research_agent.py:395-556`（`markdown_compare_table`/`markdown_risks`/`markdown_gaps`/`markdown_executive_page`/`markdown_coverage_audit`/`markdown_evidence_summary`/`markdown_evidence_appendix`） | **两套并行组装器**，标题措辞不同、`_company_table` 与 `markdown_compare_table` 同为 7 列；旧的那套已无调用者 |
| 7 | **引用/无据词校验** | `qa_engine.py:2496 detect_unsupported_terms`（正则 `20\d{2}\|数值+单位` + 12 投研关键词，上限 20）；`agents/verification.py:30-50`+`:430 unsupported_answer_terms`+`:568 normalize_for_support` | qa_engine 那份**是死的**，活的在 verification.py；两份正则关键词集不同（后者多 万台/套/个/G/T/ms/us/ns/GPU hours/tokens） |
| 8 | **短文本截断** | `report/builder.py:205`、`report/render_markdown.py:195`、`eval/auto_judge.py:77`、`eval/runner.py:282`、`eval/rag_runner.py:468`、`agents/verification.py:574`、`agents/models.py:18`、`conversation_store.py:51`、`research_agent.py:759`、`professional_qa.py:739 shorten_inline` | **10 份** |
| 9 | **引用标注** | `professional_qa.py:734 with_citation`、`research_agent.py:738 with_citation`、`builder.py:192 _with_citation` | 3 份 |
| 10 | **流水线本身** | `qa_engine.py:693-889`（197 行 workflow） vs `:890-1120`（231 行 stream workflow）；答案合成 `:1418-1486` vs `:1487-1577` | **2 份**，同一 11 阶段两次实现 |
| 11 | 杂项 | `_ratio`×2（`report_type.py:91`/`builder.py:212`）、`unique`×3（`professional_qa.py:760`/`research_agent.py:770`/`agents/planner.py:124`）、`normalize_key`×2、`dedupe`×13、`_short_text` 见 #8 | — |

合计：同一套投研语义被重复编码 **约 40 处**，其中 5 处已是死代码，剩余 35 处散落在 12 个文件里。重构顺序应是先建 `aika/domain/`（`answer_type` 枚举 + coverage/freshness/引用三条规则），再让报告层、检索层、合成层单向依赖它——否则拆完 qa_engine 只是把重复从 1 个文件搬到 14 个文件。

---

## 8) 简化机会排序

| # | 动作 | 收益 | 工时 | 风险 |
|---|---|---|---|---|
| 1 | 删 `qa_engine` 7 个死函数（183 行）+ `research_agent` 死链（~250 行）+ 2 个死模板（72 行） | −505 行，零调用面 | 0.5 d | **低**：tests 对它们零引用 |
| 2 | `pyproject.toml` 依赖分层修正：`qa_engine.py:52` 的 `postgres_retrieval` 改为惰性导入；`jinja2` 从核心依赖降级或让 `report/__init__.py:4` 惰性化 | 一步修掉 22 个 collection error 中的绝大多数；恢复 QA 主链路测试 | 0.5 d | **中**：需确认 `from_env` 的 Postgres 分支可用性 |
| 3 | 合并 `_answer_question_workflow` / `_answer_question_stream_workflow`（428→~250）与 `_generate_answer` / `_generate_answer_stream`（160→~130） | −210 行，消除双份维护 | 2 d | **中高**：流式事件序列是前端契约（`answer_delta`/`progress`/`final`），需先补 stream 测试 |
| 4 | 统一 4 份 freshness + 3 份 coverage + 2 份 usability/qualify → `report/metrics.py` | −120 行，消除新旧报告层数值不一致 | 1 d | **中**：会改变旧报告层输出的数值，需对齐快照 |
| 5 | 删除 `research_agent.py:395-556` 旧 markdown 组装器，统一走 `render_markdown` | −160 行 | 1 d | **中**：`build_research_outputs` 返回的 `sections` 结构需保持 |
| 6 | 按 §1 拆 `qa_engine.py` 为 14 个模块（2,624→~2,430） | 认知负担断崖下降；`pipeline/` 可独立测试 | 5–7 d | **高**：11 个 import 方需同步改，建议先做 #1/#2 再做 |
| 7 | claims 审核路径收敛：删除 `write_claim_review`(:963) 或把 `ResearchMemory.review_claim`(:1049) 接到它；`normalize_claim_review` 缺省 `review_status` 改为 `needs_review`（现为 `revised`，:1005-1006，语义错误） | 消除"审核不落盘"数据丢失 | 1 d | **中** |
| 8 | 统一双 CLI（`aika_cli.py` 711 行 vs `cli.py` 416 行，后者入口不可达） | 恢复 `aika eval` | 1 d | **中低** |
| 9 | 测试基建：加 `conftest.py` 覆盖 `tmp_path` 基目录 + 全仓日期注入（`today` 参数化） | 26 个 error + 1 个假失败归零 | 0.5 d | **低** |
| 10 | 跑一次真实评测并把产物提交到 `data/eval_runs/`，激活前端 `EvalView` | 让 2,983 行 App.tsx 里的评测面板不再是空壳 | 0.5 d | **低**（需 API key） |

**排序理由**：#1/#2/#9 是"零风险、当天见效"，且 #2 会把 28.5% 的测试收集率拉回 70%+，使后续 #3/#6 的重构有测试护栏；#3/#6 是高收益但必须先有护栏；#7/#8/#10 是"功能真实存在但断路"的修复，价值密度最高但用户可见度最低。

**总体判断**：问答合成层的真实复杂度不在 `qa_engine` 的行数，而在**同一业务规则被写了 4–14 遍**（answer_type 14 处、coverage 3 份、freshness 4 份、markdown 2 套、流水线 2 份）。任何"只拆文件不合并规则"的重构都会把重复从 1 个文件扩散到 14 个文件，反而更难治。

**明确不建议的三件事**：① 在 #2/#9 之前动 #3/#6——当前 28.5% 的测试收集率等于没有护栏，拆流水线时最大的风险是"流式事件序列静默变化"；② 把 `answer_type` 抽成策略类继承体系——14 处分支里 9 处只是 3–5 行的取值差异，抽象成本高于收益，应改成一张 `answer_type → (选卡函数, 降级函数, 检索过滤)` 的声明式表；③ 给报告层再包一层模板抽象——HTML 已有 jinja2、markdown 是纯字符串函数，再加一层只会增加间接层，真正缺的是 P0 的层级模型与 P4 的折叠渲染。
