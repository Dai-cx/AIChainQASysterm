# AIKA 数据层 / 检索层 / 存储层 审计报告

审计范围：`aika/` 全部数据与检索相关模块、`data/` 目录树、索引构建入口、`scripts/` 语料管线。
方法：全量 AST import 扫描 + 逐文件 read + 实机运行探针（Python 3.13.14，项目 `.venv`）。所有行号为实测；「未验证」项已显式标注。

---

## 0) 行数更正表

| 你的表述 | 实测 | 更正说明 |
|---|---|---|
| 包 `aika/` 94 模块 31,243 行 | **94 个 `.py`，30,748 行**（`Get-ChildItem -Recurse *.py`，排除 `__pycache__`） | 差 495 行，建议以 30,748 为准 |
| `aika/aika_core/bundled_sample`（force-include 产物） | **仓库内不存在**（Test-Path False） | 只在 `pyproject.toml:109-111` 的 wheel `force-include` 里生成；源码态解析回退到 `data/knowledge_packs/sample`（`aika/aika_core/sample_data.py:44-49`） |
| `aika/aika_core/models.py` | 408 行 | `Measure-Object -Line` 只数非空行会报 357，误差来自空行 |
| `aika/aika_core/graph.py` | 83 行 | 反向 import 属实：`graph.py:10 → aika.frontend_data` |
| `aika/aika_core/data_paths.py` | 29 行 | 纯常量模块，无逻辑 |
| `aika/aika_core/backends/csv_backend.py` | 401 行 | 反向 import 属实，共 5 处（`:24/:25-31/:32/:33/:34`） |
| `aika/aika_core/backends/sqlite_backend.py` | 1306 行 | 反向 import 属实：`:15 → aika.report` |
| `aika/data_config.py` 会往 site-packages 写 CSV | **属实**，且机制更糟 | `load_companies()`（`:229-230`）/`load_research_keywords()`（`:297-298`）/`load_industry_sources()`（`:313-314`）在读之前**无条件**调 `write_default_*`；`ROOT_DIR=parents[1]`（`:13`）与 `aika_core/data_paths.py:8` 的 `parents[2]` 指向**同一个仓库根**，不是两套根 |
| `aika/curated_graph.py` 属「检索栈」 | **不是检索器** | 是构建期过滤器：`:50-54 should_keep_relation` 丢弃 `MENTIONED_IN`，`:78-127 build_curated_graph`。检索期零调用 |
| `aika/neo4j_client.py` | 87 行 | QAEngine 唯一 Neo4j 出口，只读 + `cypher_guard.ensure_limit`（`:76`） |
| `pdf_parser/kg_loader/graph_builder/llm_extractor` 属「语料入库管线」 | 属实，但**pipeline 不在包内** | 这 4 个模块在 `aika/` 内部**零 import**，只被 `scripts/*.py` 与 `tests/test_stage2_stage3_pipeline.py` 引用；它们是构建期工具，不是运行时依赖 |
| 「`aika/aika_mcp/` 里的建库逻辑」 | **不存在** | 建库逻辑只有一处：`aika/aika_core/backends/sqlite_backend.py:141 build_sqlite_index`；`aika/aika_mcp/tools.py:125-161 resolve_backend` 只读索引 |
| 「`llm_client.py` 是否唯一 LLM 出口」 | **是** | `aika/llm_client.py:63 OpenAICompatibleClient` 是唯一 chat 出口（`:253`/`:279` 两处 `requests.post`）；embedding 另有独立出口 `aika/embedding_client.py:26`（`:95`），无第二套实现 |
| 未提及 | `aika/aika_core/backends/postgres_backend.py` **33 行纯桩** | 4 个方法全 `raise NotImplementedError`（`:17/:20/:30/:33`）；真正的 PG 实现在 `aika/postgres_retrieval.py`（1385 行，4 个类） |

---

## 1) 模块清单与职责

### 1.1 `aika_core` 抽象层（应是最底层，实际不低）

| path | 行数 | 职责 | 被谁 import |
|---|---|---|---|
| `aika/aika_core/data_paths.py` | 29 | 仓库根与 7 个数据文件常量 | csv_backend、sqlite_backend、aika_core/* |
| `aika/aika_core/config.py` | 55 | `AikaCoreConfig`（3 个目录 + 4 个文件），`from_env` 读 `AIKA_CORE_*` | 各 backend |
| `aika/aika_core/models.py` | 408 | `EvidenceCard`/`ClaimRecord`/`GraphEdge`/`CompanyProfile`/`ResearchBrief` + `ResearchBackend(ABC)`（`:384-408`，仅 4 个抽象方法） | csv/sqlite backend、aika_core/* |
| `aika/aika_core/graph.py` | 83 | `load_graph`（`:13-17`）、`edge_from_relation_row`（`:37-53`） | aika_core/__init__、csv_backend |
| `aika/aika_core/claims.py` | 151 | `load_claims`、`search_claim_records`、**纯关键词打分** `score_claim_record`（`:47-93`） | csv_backend |
| `aika/aika_core/evidence.py` | 386 | 证据标准化 / UX bundle 组装 | aika_core/__init__ |
| `aika/aika_core/knowledge_pack.py` | 290 | 知识包校验（`validate_knowledge_pack:91`） | aika_cli、sample_data |
| `aika/aika_core/sample_data.py` | 113 | bundled_sample 解析 + 拷贝到 `~/.aika` | aika_cli |
| `aika/aika_core/backends/csv_backend.py` | 401 | CSV/JSONL 直读后端（`data/curated`） | aika_core/__init__、aika_mcp/tools |
| `aika/aika_core/backends/sqlite_backend.py` | 1306 | **建索引 + FTS5 检索 + 报告渲染** 四合一 | aika_cli、aika_mcp/tools |
| `aika/aika_core/backends/postgres_backend.py` | 33 | **空桩**，全 NotImplementedError | 仅 backends/__init__ |
| `aika/aika_core/{brief,compare,gaps,profiles}.py` | 18/20/21/16 | 纯转发到 backend（`active_backend = backend or CSVResearchBackend.from_env()`） | 仅 aika_core/__init__ |

### 1.2 检索与检索周边

| path | 行数 | 职责 | 被谁 import |
|---|---|---|---|
| `aika/qa_engine.py` | 2412 | QA 编排（prompt 模板 + 11 阶段工作流 + 历史压缩 + HYDE + 证据装配 + 子图构造） | api、aika_mcp/tools、agents |
| `aika/professional_qa.py` | 768 | **真正的证据排序/选取引擎**，自带 `EvidenceCard` 定义（`:28-60`） | csv_backend、qa_engine、research_agent |
| `aika/research_claims.py` | 1563 | claims 构建 + `ResearchMemory`（`:1030`）+ `ResearchHit` | csv_backend、qa_engine、research_agent |
| `aika/postgres_retrieval.py` | 1385 | 真实 PG 实现：Store/RagIndex/ResearchMemory/SemanticIndex 四类 | qa_engine、cli、scripts |
| `aika/rag_index.py` | 618 | 本地 BM25 索引 `LocalRagIndex`（`:249`）+ `RagHit`（`:127`） | **仅 tests + scripts** |
| `aika/semantic_index.py` | 407 | 本地 JSONL 向量索引 `SemanticIndex`（`:306`） | 仅 `agent_tools.py:274`（且运行时该属性恒 None） |
| `aika/reranker.py` | 197 | `EvidenceReranker`（heuristic/llm/auto） | `agent_tools.py:372-374` 唯一生产点 |
| `aika/graphrag.py` | 578 | GraphRAG：QueryRouter/DriftPlanner/PathBuilder | agent_runner、agent_tools、agents.centralized |
| `aika/domain_lexicon.py` | 369 | 主题同义词、公司归一化（`:277-282`）、噪音章节判定 | csv_backend、curated_graph、professional_qa、graph_builder |
| `aika/extraction_schema.py` | 340 | **事实上的数据形状中心**（23 处引用）：CSV/JSONL 读写、`normalize_name` | 几乎所有数据模块 |
| `aika/neo4j_client.py` | 87 | 只读 Neo4j 客户端 | 仅 qa_engine |
| `aika/cypher_generator.py` | 233 | 模板 Cypher / LLM Cypher | qa_engine |
| `aika/cypher_guard.py` | 79 | 强制 LIMIT | neo4j_client、qa_engine |
| `aika/frontend_data.py` | 537 | `LocalKnowledgeGraph`（CSV 图内存实现）、`RELATION_LABELS`、`subgraph_edges` | qa_engine、aika_core/graph、api、scripts |
| `aika/curated_graph.py` | 128 | 构建期关系过滤 → `data/curated` | 仅 scripts |

### 1.3 语料构建管线（不在运行时包内）

| path | 行数 | 职责 | 实际调用者 |
|---|---|---|---|
| `aika/pdf_parser.py` | 395 | PDF → 段落/markdown | `scripts/parse_pdfs.py` |
| `aika/text_cleaner.py` | 424 | 长文 → chunks（`CHUNKS_DIR:13`，`build_chunks_file:418`） | scripts、rag_index |
| `aika/llm_extractor.py` | 118 | LLM 抽取实体/关系 | `scripts/extract_knowledge.py` |
| `aika/graph_builder.py` | 258 | 抽取结果 → `data/verified` 图 CSV | `scripts/build_verified_graph.py` |
| `aika/kg_loader.py` | 156 | 图 CSV → Neo4j | `scripts/load_neo4j.py` |
| `aika/embedding_client.py` | 132 | embedding 出口 | postgres_retrieval、scripts |
| `aika/llm_client.py` | 394 | 唯一 LLM 出口 + `.env` 加载 | qa_engine、aika_mcp/tools、eval、neo4j_client |
| `aika/data_config.py` | 348 | 元数据 CSV 默认值 + **写盘副作用** | domain_lexicon:11、graph_builder:22、llm_extractor:9 |

### 1.4 入口（4 个并存）

`pyproject.toml:34-35` 只暴露 `aika = "aika.aika_cli:main"`。但实际存在：

| 入口 | path:line | 是否暴露 | 依赖 |
|---|---|---|---|
| `aika_cli.py` | `:150-157 main` | ✅ 唯一 console script | **仅 aika_core + SQLite FTS5**，不碰 PG/Neo4j（`:14-30`） |
| `cli.py` | `:87 main` | ❌ 未暴露 | 强依赖 PG（`:179-201` 无降级） |
| 根 `main.py` | `from aika.cli import main` | 手动 `python main.py` | 同上，走 PG |
| `api.py` | `:151-153 QAEngine.from_env()` | FastAPI | **默认强依赖 PG** |
| `aika_mcp/` | `tools.py:125-161` | MCP server | csv/sqlite，**永不碰 PG/Neo4j** |

---

## 2) 存储后端矩阵

**结论：同一个「检索后端」概念有 8 条并行实现**，共享的只有 4 个方法名的 ABC。

| # | 实现 | 位置 | 数据源 | 默认启用 | 开关 | 调用方 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | `CSVResearchBackend` | `csv_backend.py:37` | `data/curated`（CSV/JSONL） | ✅ `aika_core.default_backend()`（`__init__.py:35-36`） | `AikaCoreConfig.from_env()` 读 `AIKA_CORE_DATA_DIR` | aika_core/__init__、`aika_mcp/tools.py:149`（兜底） | 活，但反向依赖 5 个高层模块 |
| 2 | `SQLiteResearchBackend` | `sqlite_backend.py:209` | `~/.aika/knowledge/sample`（7 文件）→ FTS5 | ❌ 需先 `aika init --sample && aika build-index` | `--home` / `AIKA_HOME`（`:36`、`:103-106`） | aika_cli、`aika_mcp/tools.py:136` | **活且最干净**（唯一不依赖 PG/Neo4j 的完整后端） |
| 3 | `PostgresResearchBackend` | `postgres_backend.py:10-33` | — | ❌ | — | 仅 `backends/__init__.py` | **纯桩，33 行全 NotImplementedError** |
| 4 | PG 真实实现（4 类） | `postgres_retrieval.py:147/795/897/1196` | PostgreSQL + pgvector + pg_search | ✅ `QA_DISABLE_POSTGRES=false` 时**强制** | `DATABASE_URL`、`QA_DISABLE_POSTGRES`（`qa_engine.py:381-386`） | qa_engine、cli、scripts | 活；缺 9 项 schema 即抛错（`:187-218`） |
| 5 | `LocalRagIndex` | `rag_index.py:249` | `data/chunks/*.jsonl` | ❌ | — | **仅 tests + `scripts/bootstrap_postgres_retrieval.py`** | **运行时死代码**（`build_rag_index` 亦同） |
| 6 | `SemanticIndex` | `semantic_index.py:306` | `data/semantic_index`（不存在） | ❌ | — | `agent_tools.py:274`，但 `engine.semantic_index` 恒 None（`:269-271` 直接 `return []`） | **双重死路**：文件不存在 + 属性恒 None |
| 7 | `LocalKnowledgeGraph`（CSV 图） | `frontend_data.py` | `KG_DATA_DIR`（默认 `data/curated`，缺失回落 `data/verified`） | ✅ `QA_GRAPH_BACKEND=auto` 且 Neo4j 连不上 → `csv`（`qa_engine.py:442`/`:458-459`） | `KG_DATA_DIR`、`QA_GRAPH_BACKEND` | qa_engine、api | 活，**默认走这条** |
| 8 | `Neo4jReadClient` | `neo4j_client.py:42` | Neo4j（由 `scripts/load_neo4j.py` 灌入） | ❌ 需 `check_connection()` 成功（`qa_engine.py:439-459`） | `NEO4J_URI/USER/PASSWORD`（默认 `password123`） | 仅 qa_engine | 活但默认关闭；空结果/异常都回落 CSV（`:1303-1309`） |

另外两套 ResearchMemory 同接口双实现：`research_claims.py:1030 ResearchMemory`（本地）vs `postgres_retrieval.py:897 PostgresResearchMemory`（PG），方法名完全相同（search / search_global_dossiers / search_local_claims / get_claim / review_claim / claim_stats）。

**抽象层与后端的关系：契约只覆盖一半，数据形状完全不统一。**
- ABC 只声明 4 个方法（`models.py:384-408`），但两个后端都额外实现了 `compare_companies`、`audit_evidence_gaps`、`build_research_brief`（csv `:134/:151/:166`，sqlite `:307/:348/:411`）；`aika_core/brief.py:16-18` 只能用 `hasattr` + `# type: ignore[attr-defined]` 兜住 → 契约不完整的直接证据。
- csv 后端返回 `professional_qa.EvidenceCard`（26 字段，`professional_qa.py:28-60`）而非 `aika_core.models.EvidenceCard`（28 字段，`models.py:57-137`）——**两个同名不同类型**。
- sqlite 后端把行包装成 `_MappingRow(dict)`（`:1007`）再转 card；PG 后端返回 dict（`_hit_from_row:841`）。三种形状。

---

## 3) 检索链调用图（真实形状）

`qa_engine.answer_question`（`:526-562`）在 `:548-556` 立刻分流，**默认走 agent，不走 workflow**——代码默认值即如此：`qa_engine.py:369` `enable_agent = os.getenv("QA_ENABLE_AGENT", "true").casefold() != "false"`，`:371` `agent_runner = os.getenv("QA_AGENT_RUNNER", "langgraph")`。故下图上分支才是常态：

```
qa_engine.answer_question (:526)
 └─ enable_agent=True (:548-556)
     └─ agents/qa_agent.py:28-61 run()
         ├─ runner=="legacy" → agent_runner.AgentRunner (:805)
         └─ 默认 → LangGraphAgentRunner (langgraph_runner.py:199-208)
              query_wave ──► graphrag_join ──► review
                 │
                 └─ agents/centralized.py:321-322 ThreadPoolExecutor(max_workers=5)
                      ├─ :746 tools.query_graph      ──► qa_engine._query_graph (:1274)
                      ├─ :750 tools.search_rag       ──► qa_engine._search_rag (:1312)
                      ├─ :753 tools.search_research  ──► qa_engine._search_research (:1340)
                      ├─ :756 tools.search_semantic  ──► agent_tools.py:268-271 恒 return []
                      └─ :758 retrieve_graphrag      ──► graphrag.py:351（内部再调上面几路）
 否则 (enable_agent=False)
 └─ _answer_question_workflow (:693-888)  ← 纯串行、11 阶段
     history(:724) → contextualize(:734) → plan(:739-748) → HYDE(:753)
     → cypher(:759) → graph(:766) → rag(:771) → research(:776)
     → evidence(:781-789) → answer(:794) → verify(:808)
```

两套编排的差异是本次审计最重要的语义事实：

| 维度 | workflow 分支 | langgraph/agent 分支（**默认**） |
|---|---|---|
| 并发 | 无，全串行（`:704` docstring 自述顺序） | 5 路并行（`centralized.py:321-322`） |
| 检索通路 | 3 条（graph/rag/research） | 5 条（+semantic +graphrag） |
| 排序 | `rank_evidence_cards`（`professional_qa.py:335`） | `EvidenceReranker.rerank`（`agent_tools.py:372-374`） |
| graphrag | **完全不使用** | 每轮都跑（`centralized.py:758-760`） |

**每条通路的真实性（无 PG / 无 Neo4j / 当前仓库数据）：**

| 通路 | 常态结果 | 证据 |
|---|---|---|
| graph（CSV） | ✅ **唯一有实质输出的通路**。实测 `graph_data_dir=data/curated`，entities=285 / relations=278 | `qa_engine.py:428-437`、`_query_graph:1293` |
| graph（Neo4j） | 恒空。`check_connection` 失败只返回 `(False, msg)`（`neo4j_client.py:61-67`）→ backend 回落 csv | `qa_engine.py:442`/`:458-459` |
| rag（PG） | 恒空。`rag_index is None` → `return []`（`:1326-1329`） | `_search_rag` |
| rag（本地） | 恒空。`data/chunks` 为空且 `LocalRagIndex` 从未在运行时代码实例化 | `rag_index.py:182`、全仓 grep |
| research（PG） | 恒空。`research_memory is None` → `return []`（`:1351-1352`） | `_search_research` |
| semantic | 恒空。`engine.semantic_index is None` → `return []`（`agent_tools.py:269-271`）；`data/semantic_index` 不存在 | 双重原因 |
| graphrag | 活，但输出质量退化：内部依赖的 semantic/rag 子路为空，只剩图路径 | `graphrag.py:351` |

实测印证（`QA_DISABLE_POSTGRES=true`，无 LLM key）：`evidence_cards=2, graph_records=2, rag_hits=0, research_hits=0, errors=[]`，answer 为「证据受限」fallback 文本。

**死代码通路清单：** `LocalRagIndex` 全链路（`build_rag_index`→`iter_chunk_records`→BM25 检索，约 370 行）、`SemanticIndex` 检索（约 100 行）、`PostgresResearchBackend`（33 行）、本地 `cloud`/`embedding` 分支（`qa_engine.py:413-426` 需要 PG + embedding 配置才走）。

---

## 4) 数据资产地图

`data/metadata/*.csv` **不是唯一真实知识源，也不是运行时知识源**：

| 资产 | 体量 | 生成者 | 消费者 | 可否不重建索引就跑 |
|---|---|---|---|---|
| `data/curated/{entities,relations}.csv` | 78,790 / 75,675 B | `scripts/build_curated_graph.py:19-20` → `curated_graph.build_curated_graph`（输入 `data/verified`） | CSV 图通路（`qa_engine.py:428-437`） | ✅ 已提交，直接读 |
| `data/curated/{claims,evidence_spans,segment_dossiers}` | 387,045 / 175,898 / 30,016 B | **无生成器**（见下） | `research_claims.ResearchMemory:1030`、`aika_core/claims.py:14` | ✅ 已提交 |
| `data/verified/{entities,relations}.csv` | 163,334 / 304,503 B | `scripts/build_verified_graph.py:16` → `graph_builder`（LLM 抽取结果 + manifest） | curated 构建、图回落（`frontend_data.py:18-19`） | ✅ |
| `data/knowledge_packs/sample/*`（7 文件） | 257,483 B 合计 | `scripts/build_sample_pack.py:150-157`，**唯一有正经默认参数的脚本**（`:79-84` claim-limit 160 / relation-limit 120） | `aika init --sample` → `~/.aika` → SQLite 索引 | ✅（且已随 wheel 打包） |
| `data/metadata/*.csv` | 44,259 B | `scripts/prepare_stage1_data.py:54-56`、`aika/data_config.py:208-226` 的 DEFAULT_* | **仅** `data_config`（被 domain_lexicon/graph_builder/llm_extractor 引用）+ 4 个 scripts | 与本地问答无关 |
| `data/eval/*.jsonl`（3 个） | 151,735 B | 手工/未验证 | `eval/` 包、`cli.py:179-201` | 与问答无关 |
| `data/{chunks,parsed_text,rag,extracted,feedback,eval_runs,agent_tasks}` | 仅 `.gitkeep` | `text_cleaner.build_chunks_file:418`、`pdf_parser`、`llm_extractor` | rag_index / eval | ❌ **全空，RAG 一律无数据** |
| `.aika/`（`~/.aika`） | 仓库内不存在 | `aika_cli.run_init:160-175` → `copy_sample_files` | `SQLiteResearchBackend`（`resolve_aika_home:103-106`） | ❌ 必须先 `aika init --sample` |

**最关键的复现缺陷：`data/curated/{claims,evidence_spans,segment_dossiers}` 在当前代码下无法再生成。**
`research_claims.py:352 build_research_artifacts(..., write_outputs: bool = True)`，落盘受 `:389 if write_outputs:` 控制；两个生产脚本都显式传 `write_outputs=False`（`scripts/build_curated_graph.py:41`、`scripts/build_research_artifacts.py:36`），转而**强制**连 PostgreSQL 写库：

```
scripts/build_curated_graph.py:   build_research_artifacts(..., write_outputs=False)
                                → PostgresRetrievalStore.from_env() + ensure_ready()
                                → store.sync_research(...)     # 必须 PG
```

全仓库只有 `tests/test_research_claims.py:90/174` 用默认 `True`。结论：CSV 图与 claims 的源文件是**已提交的历史产物**，重建必须装 PostgreSQL。README 里的「重建语料」路径实际不成立。

**知识图谱（companies/relations）的真实来源链：** `data/raw_pdfs`（空，无 PDF）→ `pdf_parser` → `data/parsed_text`（空）→ `llm_extractor` → `data/extracted`（空）→ `graph_builder` → `data/verified`（**有**）→ `curated_graph` → `data/curated`（**有**）。也就是说：前端看到的图来自 CSV 静态表，Neo4j 只是可选的第二份拷贝（`scripts/load_neo4j.py`），LLM 抽取是上游一次性动作、产物已提交。

---

## 5) 分层污染全清单

分层定义：L0=`aika_core`，L1=数据/工具（data_config、domain_lexicon、extraction_schema），L2=evidence/report/eval，L3=agents，L4=cli/api/mcp。

| 位置 | 违规 import | 层次 | 正确方向 |
|---|---|---|---|
| `aika/aika_core/backends/csv_backend.py:24` | `aika.domain_lexicon` | L0→L1 | 把词表下沉到 `aika_core/lexicon.py`，或由调用方注入 |
| `csv_backend.py:25-31` | `aika.professional_qa`（5 个符号，含自带 EvidenceCard） | L0→L2 | 证据选取逻辑应属 L0；上移 `professional_qa` 的纯函数到 `aika_core/evidence.py` |
| `csv_backend.py:32` | `aika.question_planner` | L0→L2 | 计划对象定义为 `aika_core/models.py` 的 dataclass，planner 只负责生成 |
| `csv_backend.py:33` | `aika.research_agent` | L0→L3 | `build_research_outputs` 是上层用例，不应被后端调用 |
| `csv_backend.py:34` | `aika.research_claims` | L0→L2 | `ResearchMemory` 属检索核心，应下沉或作为注入接口 |
| `aika/aika_core/backends/sqlite_backend.py:15` | `aika.report`（4 个符号） | L0→L2 | 报告渲染从后端剥离，后端只返回 `ResearchBrief` 数据 |
| `aika/aika_core/graph.py:10` | `aika.frontend_data` | L0→L2 | `LocalKnowledgeGraph` 下沉到 `aika_core/graph.py` 本体（graph.py 只是它的 re-export 壳，`:75-83`） |
| `aika/qa_engine.py:44` | `aika.agents.verification` | L3→L3 | 可接受；但 verification 只用 2 个纯函数，宜下沉为 L2 |
| `aika/qa_engine.py:549` | `aika.agents.qa_agent`（函数内 import） | L3→L3 | 循环依赖的规避手法（agents 反向 import qa_engine），应改用接口注入 |
| `aika/research_agent.py` | `aika.report` | L2→L2 | 报告生成应只由 cli/api 触发 |
| `aika/agent_runner.py` / `agent_tools.py` / `langgraph_runner.py` | 各自 import `aika.agents.{coverage,planner,verification,executor}` | L3→L3 | agents 包未分层，internal 依赖应上提到 `agents/base.py` |

未违规但**架构性错误**的一处：`aika/aika_core/backends/__init__.py:3-7` 同时 import 三个后端，使 `import aika.aika_core.backends.sqlite_backend` 会传递执行 csv_backend → research_agent → report → `jinja2`。实测在干净 Python 上 `python -m aika.aika_cli init` 直接 `ModuleNotFoundError: No module named 'jinja2'`——**这正是「Windows 安装态故障」的前半段**。

建议依赖方向（单向）：

```
L0 aika_core (models/data_paths/claims/graph/evidence/knowledge_pack)
   ▲
L1 数据工具 (extraction_schema/domain_lexicon/data_config → 但必须无写副作用)
   ▲
L2 检索与呈现 (professional_qa/research_claims/rag_index/reranker/graphrag/report)
   ▲
L3 编排 (qa_engine/agent_*/agents/*)
   ▲
L4 入口 (aika_cli/api/aika_mcp)
```

---

## 6) 冗余 / 死代码清单

| path:line | 行数 | 为什么冗余/死 | 建议 |
|---|---|---|---|
| `aika/rag_index.py:249-534` | ~285 | `LocalRagIndex` 全仓库只被 tests 与 `scripts/bootstrap_postgres_retrieval.py` 使用；运行时代码从不实例化 | 移入 tests 或删除；`RagHit`（`:127`）保留（qa_engine 依赖其形状） |
| `aika/rag_index.py:182-248` | ~67 | `iter_chunk_records`/`build_rag_index` 同上下场 | 同上 |
| `aika/semantic_index.py:306-407` | ~100 | `SemanticIndex` 唯一使用点 `agent_tools.py:274` 永远走不到（`engine.semantic_index` 恒 None，`:269-271`） | 保留 `build_semantic_index`（scripts 用），删检索类 |
| `aika/aika_core/backends/postgres_backend.py` | 33 | 4 方法全 `NotImplementedError`（`:17/:20/:30/:33`） | 删除，或真正包 `PostgresRetrievalStore` |
| `aika/aika_core/{brief,compare,gaps,profiles}.py` | 18/20/21/16（共 75） | 纯转发 + `hasattr` 兜底（`brief.py:16-18`），仅 `aika_core/__init__` 引用 | 方法并入 ABC，删四文件 |
| `aika/cli.py` | 416 | 未被 pyproject 暴露；强依赖 PG（`:179-201`），与 `aika_cli.py` 重复 `build_parser/main/run_demo`（`:27/:87/:254` vs `:51/:150/:199`） | 归档到 `scripts/` 或删除；同时改 `main.py:1` |
| `aika/aika_core/claims.py:47-93` | 47 | `score_claim_record` 纯关键词打分，与 `research_claims.score_claim:1203` 功能重叠 | 合并为一个打分函数 |
| `aika/professional_qa.py:28-60` vs `aika/aika_core/models.py:57-137` | 33 / 81 | **两个同名 `EvidenceCard`**，字段集不同，靠 `from_any` 互转 | 统一为 models.py 一份 |
| `aika/agents/coverage.py:13` vs `models.py:315` | — | 两个 `EvidenceGap` | 同上 |
| `aika/agent_tools.py:656` vs `agents/verification.py:56` | — | 两个 `verify_answer_support` | 保留一个 |
| `aika/eval/rag_runner.py` vs `aika/eval/runner.py` | 472 / 286 | 各自实现 `case_report/summarize_results/category_scores/metric_means/file_sha256/git_commit/new_run_id` | 抽 `eval/base.py` |
| `_short_text` ×6 | — | `csv_backend.py:397`、`sqlite_backend.py:1295`、`aika_mcp/tools.py:1048`、`eval/auto_judge.py:77`、`report/builder.py:205`、`report/render_markdown.py:195` | 收进 `aika_core/text.py` |
| `short_text` ×6 | — | `conversation_store.py:51`、`research_agent.py:759`、`agents/models.py:18`、`agents/verification.py:574`、`eval/rag_runner.py:468`、`eval/runner.py:282` | 同上 |
| `shorten` ×4 / `_dedupe` ×4 / `_values` ×2 / `_query_terms` ×2 / `_floatish` ×2 | — | 见 `.tmp/audit/dups.py` 扫描结果；`_floatish` 两处分别在 `models.py:38`、`sqlite_backend.py:1288` | 同上 |
| `aika/aika_cli.py:497/654/674` vs `aika/aika_mcp/doctor.py:187/319`、`server.py:326` | — | CLI 与 MCP 各自 re-implement doctor/JSON-RPC/version | 统一到 `aika_mcp` |
| `aika/qa_engine.py:836`、`:1060` | 2 | `"embedding_hits": 0` 两处硬编码，diagnostics 永不反映真实值 | 删除或接真值 |
| `aika/pdf_parser.py:75` vs `aika/text_cleaner.py:349` | — | 两个 `markdown_escape` | 合并 |
| `aika/graphrag.py:492` vs `aika/rag_index.py:608` | — | 两个 `dedupe_hits` | 合并 |
| `aika/aika_core/backends/sqlite_backend.py:1007-1306` | ~300 | 后端内混入报告渲染与文本工具（`_summarize_cards`/`_card_bullets`/`_gap_bullets`/`_core_judgment`） | 拆到 `aika_core/render.py` |
| `aika/aika_core/backends/csv_backend.py:240-289` | 50 | `_chunk_edges_for_company` 读 `data/chunks`（恒空）→ 恒返回 [] | 随 chunks 管线一起删或修 |

---

## 7) 本机无 PG / 无 Neo4j 的最小可跑路径

**能跑（实测通过）：** `aika init` → `build-index` → `demo` / `search-evidence` / `search-claims`（SQLite FTS5）；MCP 的 9 个工具（csv 兜底）；`QAEngine` 的 CSV 图通路；`graphrag`（退化版）。

**不能跑：** `aika/cli.py` 全部（`run_rag_eval:179-201` 无降级）、`api.py` 默认（`:151-153`）、本地 RAG / semantic（数据目录为空）、任何 `data/chunks` 依赖项。

最小 env（`.env` 或环境变量）：

```
QA_DISABLE_POSTGRES=true        # 唯一必需项；否则 QAEngine.from_env() 直接抛 PostgresRetrievalError
QA_GRAPH_BACKEND=csv            # 或留 auto（自动回落）
AIKA_HOME=<可写目录>            # 默认 ~/.aika
KG_DATA_DIR=data/curated        # 默认值即可（entity 285 / relation 278）
# 可选：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 三者齐全才启用 LLM，否则走规则兜底
```

**步骤与实测结果：**

1. 用项目 `.venv`（13/13 依赖齐备；系统 python 缺 `jinja2`，会崩在 `aika/report/render_html.py:7`）。
2. `python -m aika.aika_cli init --sample` → 建 `~/.aika/{knowledge,indexes,logs}`，拷贝 7 个 sample 文件。
3. `python -m aika.aika_cli build-index` → **当前在 Windows 上必失败**：

```
sqlite_backend.py:176 in build_sqlite_index
    tmp_path.replace(target_path)
PermissionError: [WinError 32] 另一个程序正在使用此文件，进程无法访问:
    '...\.sample.sqlite.<pid>.tmp' -> '...\sample.sqlite'
```

   根因（已用最小复现证实）：`:152 with sqlite3.connect(tmp_path) as connection:` —— **`sqlite3` 的上下文管理器只提交事务、不关闭连接**，句柄活到函数结束，`tmp_path.replace` 因此失败；`:179 tmp_path.unlink()` 再抛一次。POSIX 允许 rename 打开中的文件，所以只在 Windows 出现——恰好命中「Windows 安装态故障」。
   **最小修法**（2 行，无需重构）：

```python
connection = sqlite3.connect(tmp_path)
try:
    ...
finally:
    connection.commit()
    connection.close()
```

   验证：改后同一命令输出 `BUILD OK: {'claims': 160, 'evidence_spans': 160, 'dossiers': 5, 'relations': 85}`，`demo` 输出 `Evidence cards: 3 / Claims: 3 / Top evidence: [E1] UCIe 2.0 Specification ... p.2`。

4. 若只要问答、不要索引：跳过 2–3 步，`aika_mcp` 会自动回落 `CSVResearchBackend` 并给出 warning `SQLite index not found, falling back to bundled CSV backend: ...`（`aika_mcp/tools.py:147-149`）。实测 `search_evidence({"query":"液冷","top_k":3})` 正常返回。

### 7.1 安装态（wheel）写权限的边界与最小改法

- 路径解析：`aika/data_config.py:13 ROOT_DIR=parents[1]` 与 `aika/aika_core/data_paths.py:8 ROOT_DIR=parents[2]` 在**源码态指向同一仓库根**；但装进 site-packages 后，`parents[1]`/`parents[2]` 都落到 site-packages 内部 → `METADATA_DIR` 变成 `site-packages/data/metadata`。
- sdist/wheel 只打包 `aika/`、`skills/aika-research`、`data/knowledge_packs/sample`（`pyproject.toml:107-114`），`data/metadata` 不存在 → 每次 `load_companies()` 都走首次写分支（`:229-230`）→ 只读安装直接 `PermissionError`。
- 触发面比想象大：`aika/domain_lexicon.py:11` import `load_companies`，且 `:257-259 @lru_cache def company_lookup()` 在 QA 热路径（`:277-282` canonical_company_name / is_core_company）被 csv_backend、curated_graph、professional_qa 调用 → **第一次问答就会写盘**。
- **最小改法（0.5 天）**：
  1. `data_config.py:14-15` 的 `DATA_DIR/METADATA_DIR` 改为 `Path(os.getenv("AIKA_DATA_DIR") or (Path.home()/".aika"/"metadata"))`，与 `SQLiteResearchBackend.resolve_aika_home:103-106` 用同一套 `AIKA_HOME` 约定；
  2. 三个 `load_*` 删掉 `write_default_*` 调用（`:229-230`、`:297-298`、`:313-314`），写盘只在 `aika init --sample` / 显式 `--regen-metadata` 时执行；
  3. `write_default_*` 内 `mkdir` 加 `try/except PermissionError` 降级为「用内存 DEFAULT_*」（DEFAULT_COMPANIES 已内置 30 家，`:46-77`）。
  这样源码态行为不变，安装态零写盘。

---

## 8) 简化机会排序（0.5–3 天）

| # | 动作 | 工时 | 风险 | 收益 |
|---|---|---|---|---|
| 1 | 修 `sqlite_backend.py:152-176` 的连接未关闭（显式 close） | 0.5 天 | 极低（3 行，已有复现验证） | **解锁 Windows 上的 `init/build-index/demo` 全链路**；这是当前最痛的单点 |
| 2 | `data_config.py` 去写副作用 + `AIKA_DATA_DIR` 化 | 0.5 天 | 低（DEFAULT_* 已自带 30 家兜底） | 安装态可用；消除热路径 IO |
| 3 | 拆 `aika_core/backends/__init__.py` 的三后端聚合 import（改惰性/按需） | 0.5 天 | 低 | 去掉 jinja2/psycopg 的传递依赖；`aika_cli` 可只装基础依赖运行 |
| 4 | 统一 `EvidenceCard` / `EvidenceGap` / `verify_answer_support` 各 1 份 | 1 天 | 中（涉及 6 处转换点 `from_any`/`to_evidence_card`） | 消除类型漂移，ABC 契约可补全 |
| 5 | 删除/归档死检索代码：`LocalRagIndex`(285) + `SemanticIndex` 检索(100) + `postgres_backend`(33) + 4 个转发模块(75) | 1 天 | 低（只删 tests/scripts 之外无引用者） | −493 行，检索栈从 8 条降到 4 条 |
| 6 | 归档 `aika/cli.py`（416 行）+ 改 `main.py`，或让它走 `aika_cli` | 1 天 | 中（PG eval 流程会失去入口，需确认无人用） | 单一 CLI，减少一套 doctor/main 重复 |
| 7 | 语料管线可复现：给 `build_research_artifacts` 加 `--write-csv`，`build_curated_graph.py:41` 传 True，PG 同步改为可选 | 2 天 | 中（要验证 claims/evidence 与已提交文件一致） | **`data/curated` 从「不可再生产物」变成可重建**，这是复现性的根 |
| 8 | 拆 `qa_engine.py`（2412 行）为 prompt/编排/历史/证据装配四模块；拆分 `sqlite_backend.py`（1306 行）的报告渲染部分 | 3 天 | 高（qa_engine 被 api/aika_mcp/agents 多处依赖，需回归 eval） | 单文件可读性；diagnostics 硬编码（`:836`）可修 |
| 9 | 后端矩阵收敛：定 SQLite FTS5 为唯一默认、PG 为可选增强、删 CSV 后端的反向依赖（把 `professional_qa` 纯函数下沉 L0） | 3 天 | 高（CSV 后端是 MCP 兜底路径） | 8 条实现 → 2 条；分层污染表可清零 |

**优先级建议：** 1→2→7 先做（都是「解除硬阻塞」类，合计 3 天，风险低）；3→5 次之（纯减法，1.5 天）；4、8、9 属重构，需要 eval 基线（`data/eval/rag_retrieval_v2.jsonl` 已有）才能安全推进。

---

## 附：本次审计的一次性事实

- `aika/` 94 文件 / 30,748 行；最大 5 文件：`qa_engine.py` 2412、`research_claims.py` 1563、`postgres_retrieval.py` 1385、`sqlite_backend.py` 1306、`aika_mcp/tools.py` 1078，合计 8044 行（26%）。
- 单一 LLM 出口（`llm_client.py:63`）、单一 embedding 出口（`embedding_client.py:26`）—— 这两项没有冗余，是当前架构最干净的部分。
- `aika/aika_mcp/doctor.py` 全文无 postgres 关键字：MCP 层与 PG 完全解耦，是「无 PG 可跑」的现成范例。
- `db/migrations/001_postgres_retrieval.sql`：5 表（`rag_chunks`/`research_claims`/`claim_reviews`/`segment_dossiers`/`retrieval_builds`）+ 8 个 B-tree/GIN 索引 + 3 个 HNSW 向量索引 + 1 个 BM25 索引 + 2 个扩展（`pg_search`/`vector`），与 `ensure_ready:187-218` 的 9 项检查一一对应。
