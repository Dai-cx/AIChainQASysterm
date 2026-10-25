# AIKA 复现报告 + 重构总计划

> 生成时间：2026-10-25　基线：`D:\demo\AIChainQASysterm-main`（非 git 仓库，无版本回退能力）
> 本文档的所有数字均为实测：`.venv` 已按项目 `pyproject.toml` 装好全部依赖，测试、CLI、MCP、API、前端构建均实机跑过。

---

## 一、先回答你最关心的问题：能跑起来吗？

**能，而且比你预期的要好；但有 3 个 Windows 专属故障必须先修。**

| 通路 | 状态 | 实测证据 |
|---|---|---|
| Python 依赖安装 | ✅ 已完成 | `.venv` 装好 `fastapi 0.115.14 / langgraph 1.2.17 / langchain-core 1.4.9 / mcp 1.30.0 / pymupdf 2.0 / jieba / psycopg / pytest 9.1.1`（`pip install -e ".[dev]"`） |
| 单元测试 | ⚠️ **239 passed / 9 failed / 1 skipped**（249 条，10 秒） | `pytest` 全量跑通；9 个失败集中在 4 个根因，全是 Windows/数据默认值问题，不是逻辑错误 |
| `aika` CLI（公开线） | ✅ 可用 | `aika doctor` 输出 17 项检查；`aika --help` 9 个子命令正常 |
| MCP Server | ✅ 可用 | `aika doctor` 实测启动 JSON-RPC，`[PASS] mcp_server` / `[PASS] mcp_tools: Registered 9 tools` |
| SQLite 索引构建 | ❌ **Windows 必崩** | `aika build-index` → `PermissionError: [WinError 32]`（根因见 §五 W1） |
| FastAPI 后端 | ✅ 可用 | `uvicorn aika.api:app` 启动成功，`GET /api/status` 返回 `entities=285 / relations=278 / reports=61` |
| React 前端 | ✅ 可构建、可开发 | `npm run build` → `✓ 1566 modules transformed`，产物 216 kB JS + 32 kB CSS |
| 无 LLM / 无 PG 的问答 | ✅ 降级可用 | `QA_DISABLE_POSTGRES=true` 下走 CSV 图通路，返回 2 张证据卡 + "证据受限"兜底答案 |

**关键判断：这套代码不是"跑不起来的玩具"，而是"跑得起来但每条路都只通一半"的半成品。** 真正的问题在架构，不在环境。

---

## 二、代码真实规模（实测）

```
aika/            94 个 .py     31,151 行   ← 核心包
tests/           34 个 .py      6,817 行   ← 249 条测试
scripts/         19 个 .py      3,243 行   ← 语料/运维脚本
web/src/          5 个文件      6,222 行   ← App.tsx 2,987 + styles.css 2,585
db/               1 个 .sql       196 行
skills/           1 个文件         72 行
────────────────────────────────────────
代码总计 ~48,000 行（不含 data/ 与文档）
```

### 最大的 15 个文件（占包内 44%）

| 行数 | 文件 | 真实职责 | 问题 |
|---|---|---|---|
| 2,624 | `aika/qa_engine.py` | 配置装配 + 检索编排 + 历史压缩 + HyDE + 提示词 + 图渲染 + 校验 | **7 个职责域混住**；183 行死码；430 行是同一流水线的两份拷贝 |
| 1,563 | `aika/research_claims.py` | claims 构建 + ResearchMemory + 打分 | 与 `aika_core/claims.py` 打分重复 |
| 1,385 | `aika/postgres_retrieval.py` | PG 连接池 + 迁移 + 同步 + BM25 + 语义 + 评审 | 4 个类、无 repository/service 分层 |
| 1,306 | `aika/aika_core/backends/sqlite_backend.py` | 建索引 + FTS5 检索 + **报告渲染** | 最底层包却 import `aika.report`（分层倒置） |
| 1,078 | `aika/aika_mcp/tools.py` | 9 个 MCP 工具 | 重抄上层 Markdown 组装与覆盖率计算 |
| 1,029 | `aika/agents/centralized.py` | 多智能体协调器（唯一真正的并行编排） | 4 个预算类之一 |
| 805 | `aika/agent_runner.py` | legacy 4 阶段流水线 | **默认路径不可达**，但被当基类复用 |
| 782 | `aika/research_agent.py` | 报告整形 | 含 250 行死代码簇 |
| 772 | `aika/api.py` | 21 个端点 + 业务 + Markdown 导出 + DI | 三层混住 |
| 768 | `aika/professional_qa.py` | 证据排序/选取（真正的引擎） | 自带第二份 `EvidenceCard` 定义 |
| 711 | `aika/aika_cli.py` | 公开 CLI（唯一被安装的入口） | 与 `cli.py` 重复 |
| 681 | `aika/agent_tools.py` | 13 个真实工具方法 | 与另两份工具注册表并存 |
| 630 | `aika/agents/verification.py` | 确定性答案校验 | 与 qa_engine 里那份重复 |
| 618 | `aika/rag_index.py` | 本地 BM25 | **运行时死代码**（`data/chunks` 恒空） |
| 578 | `aika/graphrag.py` | GraphRAG 路由/漂移/路径 | 依赖的两条子路恒空 |

---

## 三、五个根因（所有"冗余"都是它们的症状）

### 根因 1：三条互不相干的运行主线，共用一份代码
- **公开线**：`aika` CLI + MCP Server + SQLite FTS5 + `data/knowledge_packs/sample`（7 文件），**不碰 PG/Neo4j**，是唯一能分发的形态。
- **专业线**：FastAPI + React + PostgreSQL(pgvector/ParadeDB) + Neo4j + `data/curated` CSV，**默认强依赖 PG**（`QA_DISABLE_POSTGRES=false` 时 `QAEngine.from_env()` 直接抛错）。
- **遗留线**：`QA_ENABLE_AGENT=false` 的 11 阶段串行 workflow，只有测试与离线评测走它。

后果：`README.md` 628 行里两条主线互相矛盾；`data/curated` 与 `data/verified` 两个默认图目录并存；同一份图谱有 3 种数据形状。

### 根因 2：存储后端 8 条并行实现，抽象层只覆盖一半
`CSVResearchBackend` / `SQLiteResearchBackend` / `PostgresResearchBackend`(33 行空桩) / 真实 PG 4 类 / `LocalRagIndex`(死) / `SemanticIndex`(死) / `LocalKnowledgeGraph` / `Neo4jReadClient`。

`ResearchBackend` ABC 只声明 4 个方法（`aika/aika_core/models.py:384-408`），但后端实际共享 8 个，多出的 4 个只能靠 `hasattr` 兜（`aika_core/brief.py:16-18` 就有 `# type: ignore`）。且 csv 后端返回的是 `professional_qa.EvidenceCard`（22 字段），不是 `models.EvidenceCard`（31 字段）——**两个同名不同类型**。

### 根因 3：同一条业务规则被写 3–14 遍
| 规则 | 重复处数 |
|---|---|
| `answer_type` 分支 | **14 处 / 8 个文件** |
| 短文本截断 `shorten/short_text` | 10–16 处 |
| CSV 读取器 | 5 份 |
| JSONL 读取器 | 4 份 |
| 打分器（权重还不同） | 4 份（`12.0/5.0/1.0` vs `3.0/0.8/0.6`） |
| `freshness` 判定 | 4 份（同为 18/36 月阈值） |
| `coverage` 打分 | 3 份（口径不同，同一数据给出不同覆盖率） |
| `EvidenceCard` 定义 | 3 处 |
| 工具清单 | 4 份（MCP 9 个 / 死注册表 13 个 / langchain 8 个 / doctor 真值） |
| doctor 框架 | 3 套 |
| JSON-RPC 探针 | 2 份 |

### 根因 4：大量"看起来活着"的死代码与装饰
- `default_tool_registry()` 13 个工具 spec，**0 个 executor 注册**，`execute()` 永远返回 `No executor registered for tool: X`
- `aika/langchain_tools.py` 8 个 StructuredTool，只用来往 diagnostics 里塞个名单
- `postgres_backend.py` 33 行全 `NotImplementedError`
- `qa_engine.py` 5 个顶层函数零调用（183 行）
- `research_agent.py:395-556` 整套旧 Markdown 组装器零调用（~250 行）
- `render_svg_graph`（`frontend_data.py:386-532`）147 行，前端**从不渲染** svg 字段
- `LocalRagIndex` + `SemanticIndex` ~385 行，数据目录恒空

### 根因 5：Windows 适配为零（这是"你复现不了"的直接原因）
见 §五。

---

## 四、目标架构

```
aika/
├── core/                         # L0 纯数据与规则：零 IO、零副作用
│   ├── models.py                 EvidenceCard / ClaimRecord / GraphEdge / Gap   （唯一形状）
│   ├── domain.py                 answer_type 枚举 + coverage/freshness/引用 三张规则表
│   ├── io.py                     read_csv / read_jsonl / write_csv             （吃掉 9 份实现）
│   ├── paths.py                  AIKA_HOME 统一解析（源码态=安装态）
│   ├── settings.py               Settings.from_env()  唯一配置入口
│   ├── text.py                   shorten / dedupe / unique_strings              （吃掉 16 份）
│   └── scoring.py                唯一打分器
│
├── corpus/                       # L1 构建期（不进运行时）
│   ├── pdf.py  chunk.py  extract.py  graph_build.py  pack.py
│
├── retrieval/                    # L2 检索
│   ├── port.py                   ResearchBackend 协议（8 方法，ASSURE 完整）
│   ├── sqlite.py                 FTS5（默认，零依赖）
│   ├── postgres.py               可选增强，惰性导入
│   ├── graph_csv.py              知识图谱（CSV，默认）
│   ├── neo4j.py                  可选，惰性导入
│   └── rank.py                   BM25 + reranker
│
├── qa/                           # L3 问答合成
│   ├── engine.py                 门面：answer / answer_stream          ≤150 行
│   ├── factory.py                依赖装配 + close
│   ├── pipeline.py               一条流水线，生成器实现，同步适配器包装（消灭双份 430 行）
│   ├── history.py  hyde.py  contextualizer.py  planning.py  progress.py
│   ├── evidence.py               选卡/排序/编号（含 ensure_relation_cards）
│   ├── composer.py               提示词 + LLM 调用 + 降级答案
│   └── verify.py                 确定性校验（唯一一份）
│
├── agents/                       # L3 编排
│   ├── runner.py                 LangGraph 8 节点（删 legacy 分支）
│   ├── tools.py                  AgentTools 一套命名（删另两份注册表）
│   ├── coordinator.py            多智能体并发（保留，这是真正的亮点）
│   └── tasks.py                  ResearchAgent 任务前台
│
├── report/                       # L2 产出
│   ├── spec.py  builder.py  markdown.py  html.py  pdf.py
│   └── charts/{heatmap,evidence_bar,flow_map,freshness,common}.py
│
├── api/                          # L4 入口
│   ├── app.py                    create_app          ≤60 行
│   ├── routers/{chat,agents,graph,status,eval,claims}.py
│   ├── services/{chat_turn,export}.py
│   └── deps.py  errors.py
│
├── mcp/                          # L4 入口（对外产品面）
│   ├── server.py  tools.py  schemas.py
│   ├── host_configs.py  installer.py  doctor.py
│
└── cli/                          # L4 入口（唯一 CLI）
    └── main.py

web/src/
├── App.tsx                       ≤200 行（现在 2,987）
├── views/{Sidebar,Chat,Agents,Eval,Overview,Graph}.tsx
├── components/{Composer,MessagePair,Feedback,DetailDrawer,ui/*}.tsx
├── graph/{layout.ts,GraphCanvas.tsx}
├── lib/{markdown,labels,format}.ts
└── styles/                       按域拆 8 个 CSS 文件 + section 注释
```

**分层铁律**（可用 import-linter 或自写脚本在 CI 里卡死）：

```
L0 core  ←  L1 corpus  ←  L2 retrieval/report  ←  L3 qa/agents  ←  L4 api/mcp/cli
```
低层**禁止** import 高层。当前有 **11 处违规**，最刺眼的是 `aika_core/backends/sqlite_backend.py:15 → aika.report`（最底层依赖报告层）。

---

## 五、Windows 故障清单（复现阻塞项，P0 必修）

| # | 故障 | 位置 | 根因 | 修法 | 影响 |
|---|---|---|---|---|---|
| **W1** | `aika build-index` 必崩 | `aika/aika_core/backends/sqlite_backend.py:152-179` | `with sqlite3.connect(tmp) as conn:` **只提交事务不关连接**，句柄活到函数结束 → `tmp_path.replace()` 抛 `WinError 32`；POSIX 允许 rename 打开中的文件，所以只在 Windows 出现 | 显式 `connection.close()`（`try/finally`） | **6 个测试失败 + 公开线完全不可用**。已验证：改后输出 `claims=160 / evidence_spans=160 / dossiers=5 / relations=85`，`aika demo` 正常 |
| **W2** | 硬编码 POSIX 路径 | `aika/aika_mcp/host_configs.py:18` `DEFAULT_UV_CACHE_DIR="/tmp/uv-cache"`；同类 `/usr/bin/uv` | 用字符串拼路径，Windows 变成 `D:\usr\bin\uv` | 改 `Path` + `sys.platform` 分支 | 2 个测试失败；生成的宿主 MCP 配置在 Windows 上无效 |
| **W3** | 安装态往 site-packages 写 CSV | `aika/data_config.py:13-18` + `:229-231 / :297-298 / :313-314` | 三个 `load_*()` 在读之前**无条件**调 `write_default_*()`；`ROOT_DIR=parents[1]` 装进 wheel 后指向 site-packages | 写盘移到 `aika init`；读路径走 `AIKA_HOME` | wheel 安装后**第一次问答就 PermissionError**（`domain_lexicon.lru_cache` 会触发） |
| **W4** | `npm` 调用必失败 | `aika/cli.py:104-118` | `subprocess.run(["npm", ...])` 无 `.cmd`、无 `shell=True` | 用 `shutil.which` + `.cmd` 回退 | `aika web` 子命令在 Windows 上不可用 |
| **W5** | 图数据默认目录分裂 | `frontend_data.py:18-19` 用 `data/verified`，`qa_engine.py:431` / `api.py:158` 用 `data/curated` | 两处各写一份默认值 | 单一 `paths.py` | 1 个测试失败（`csv_backend.query_graph` 返回 `[]`）+ 生产行为不一致 |

---

## 六、分阶段重构计划

> 排序原则：**先解除阻塞 → 再删死码 → 再统一形状 → 最后拆大文件**。
> 每个阶段都有"验收"，不通过不进下一阶段。总工期约 **12 人日**（含回归）。

### P0　基线固化（0.5 天）— 必做，否则后面无法回退
1. `git init` + `.gitattributes`（`*.py text eol=lf`，避免 CRLF 污染 diff）
2. 首次提交：**当前原始状态**（tag `v0.1.4-baseline`）
3. 修好依赖安装流程并写进 `docs/dev-setup.md`（本机已踩通的 4 个坑）
4. 记录测试基线：`239 passed / 9 failed / 1 skipped`
- **验收**：`git log` 有基线 commit；`pytest` 数字可复现

### P1　解除 Windows 阻塞（1 天）— 让项目"在你电脑上真能跑"
1. W1 修 sqlite 连接泄漏（3 行）→ `build-index` / `demo` 恢复
2. W2 消除 POSIX 硬编码
3. W3 `data_config` 去写副作用
4. W5 统一图目录默认值
5. 修测试基建：加 `tests/conftest.py`（`--basetemp` 兜底）＋ 把日期炸弹 `published_at="2025"` 改成注入 `today`
- **验收**：`pytest` **249 passed / 0 failed**；`aika init --sample && aika build-index && aika demo` 全链路输出正常
- **风险**：极低（改动 <20 行，且每步都有失败测试做靶子）

### P2　砍死代码（1.5 天）— 净减约 2,000 行，零行为变化
1. 删 `qa_engine.py` 5 个零调用函数（183 行）
2. 删 `research_agent.py:308-560` 旧整形层（~250 行，含 `markdown_*` / `core_judgment` / `qualify_conclusion`）
3. 删 `LocalRagIndex` + `SemanticIndex` 检索类（~385 行）、`postgres_backend.py`（33 行）、`aika_core/{brief,compare,gaps,profiles}.py` 4 个转发壳（75 行）
4. 删 `default_tool_registry` + `ToolRegistry` + `AgentToolSpec`（161 行死元数据）、`langchain_tools.py`（114 行）
5. 删 `render_svg_graph` + `svg` 字段（147 行 + 前端类型）
6. 删死模板 `coverage_audit.html.j2`、`research_brief.html.j2`、死 `write_claim_review`
7. 删 `dashboard` 式的重复：`coverage_audit` / `benchmark_qa_speed` / `validate_postgres_cutover` 三个一次性脚本退到 `docs/legacy/`
- **验收**：`pytest` 仍 249 passed；`ruff` 无 unused 告警；行数从 31.1k → ~29k
- **注**：这一步**不删测试**，删掉的死码本就没有测试（已 grep 确认零引用）

#### P2 执行记录（2026-10-25，已完成前半段）

| 动作 | 效果 | 提交 |
|---|---|---|
| 删 `qa_engine.py` 7 个零调用函数 | −178 行 | `f1656ea` |
| 删 `sqlite_backend.py` 6 个死函数 | −53 行 | 随 `29e087f` |
| 删死模板 `coverage_audit.html.j2`、`research_brief.html.j2` | −2 文件 | 随 `29e087f` |
| 删 `langchain_tools.py` 及其 4 处接线 | −114 行 | `29e087f` |
| 删 `render_svg_graph` + API `svg` 字段 + TS 类型 | −147 行 | `29e087f` |
| JSON / SSE 两条重复流水线合并为 `_run_answer_pipeline` | −127 行 | `b749142` |
| 把 `qa_engine` 助手层拆成 `aika/qa/{text,history,subgraph,constants,types}.py` | −962 行（`qa_engine` 2624 → 1336） | `a24d3af` |

**净值**：`aika/` 31,151 → 30,572 行（−579）；`qa_engine.py` 2624 → 1336（−49%）；测试 247 passed / 1 skipped（少的那条随 SVG 渲染器一起删除）。

**顺带修掉 3 个"答案被丢掉"的 bug**（都在 `aika/agents/verification.py`，是填了 API Key 后仍看到模板答案的根因）：

1. `risk_support_check` 用 `f"{question} {answer}"` 判断"是否需要风险证据"——答案里出现"风险"二字就把自己判失败；
2. `exposure_support_check` 把"答案里出现核心敞口/直接敞口等词但没有任何敞口证据卡"判为硬失败，而解释这些词本身就会触发；
3. 缺风险证据时一律硬失败 → 整段 LLM 答案被 `build_evidence_limited_answer` 覆盖；现在只有 `answer_type == "risk_analysis"`（用户明确问风险）才硬失败，其余降级为 `warn` + 记入 `evidence_gaps`。

**推迟到 P3/P4**：`research_agent.py:308-560` 旧整形层、`LocalRagIndex`/`SemanticIndex`、`default_tool_registry`+`ToolRegistry`、`postgres_backend.py`、`aika_core/{brief,compare,gaps,profiles}.py` 转发壳、三个一次性脚本。


### P3　单一入口与单一身份（1.5 天）— 让"交付面"存在
1. 合并 `aika/cli.py` 与 `aika/aika_cli.py` 为一个 `aika/cli/main.py`：保留 `aika` 名，`aika_cli` 的真命令 + `cli.py` 的 `api/web/eval` 子命令
2. 删除 `aiqasys` 身份（`prog="aiqasys"`、`_package_version` 死分支）
3. `main.py` 改成薄壳转发；`Dockerfile` / `docker-compose.yml` / CI 全部改用 `aika ...` 或 `python -m aika`
4. MCP 工具清单单一来源：`mcp/tools.py:tool_names()` 为唯一真值，`EXPECTED_MCP_TOOLS` 改为从它派生（修 8 vs 9 的漂移 bug）
5. 合并三套 doctor → `mcp/doctor.py` 一套；合并两份 JSON-RPC 探针
6. `eval` 子命令真正可达（当前 `aika eval` 从安装入口不可达：`aika_cli.py` 没有 eval，`cli.py` 没有 `__main__`）；把 `scripts/evaluate_agent_tasks.py` 的用例迁进 `aika/eval/agent.py`
7. sdist 补齐：`web/`、`data/eval/`、`data/curated/`、`scripts/`
- **验收**：`aika eval --suite qa` 能跑；`aika mcp serve` 能跑；CI 加 `windows-latest` job 且全绿
- **风险**：中（入口被 Docker/CI/README 引用，需同步改 12 处）

#### P3 执行记录（2026-10-25，已完成）

| 动作 | 结果 |
|---|---|
| `aika/cli.py` 416 行 → `aika/cli_heavy.py` 405 行 | 只保留 handler，新增 `register_commands(subparsers)`；`build_parser`/`main` 删除 |
| `aika/aika_cli.py` 成为唯一 parser | `api` / `web` / `agent` / `eval` / `showcase` 由 `register_commands` 挂载，共 **14 个子命令、1 个身份 `aika`** |
| 删 `aiqasys` 身份 | `prog="aiqasys"` 随 `cli.py` 一起消失；`_package_version` 的 `("aika-research-mcp", "aiqasys")` → 只剩前者 |
| **修 MCP 工具清单漂移** | `EXPECTED_MCP_TOOLS`（8 项，漏 `render_report_pdf`）→ `aika.aika_mcp.tools.tool_names()`（9 项）；`aika doctor` 现在报 `[PASS] mcp_tools: Registered 9 tools.` |
| `demo` 重名消解 | `aika demo` = 本地 SQLite 样例演示（主线）；原来的「QA + Agent 全链路」改名 `aika showcase` |
| `main.py` | 5 行薄壳：`from aika.aika_cli import main` |
| `Dockerfile` / `docker-compose.yml` | `CMD ["uv","run","python","main.py","api",…]` → `["uv","run","aika","api",…]`（**原来 docker 起的入口压根没被安装过**） |
| CI | 全部改用 `aika`；新增「init → build-index → demo → doctor」轻量 smoke（正是能抓住 sqlite 句柄 bug 的那条）；新增 `windows-latest` job |
| README | CLI 章节重写为「一个身份 + 四组命令」表；4 处 `uv run python main.py` → `uv run aika` |

- **验收**：`aika --help` 14 个子命令；`aika doctor` 全 PASS；`aika demo`、`python main.py demo`、`python main.py showcase --offline` 均 exit 0；`pytest` 247 passed / 1 skipped。
- **仍未做**（留在 P6/P8）：容器名与 Postgres 用户名仍是 `aiqasys`（品牌化）、`aika mcp doctor` 在无 `uv` 的机器上仍报 FAIL（需改为回退到 `sys.executable`）。


### P4　统一数据形状与 I/O（2.5 天）— 消除"同名不同类型"
1. `core/models.py` 定为唯一定义：合并 3 份 `EvidenceCard` → 1 份；2 份 `EvidenceGap` → 1 份；2 份 `verify_answer_support` → 1 份
2. `core/io.py` 吃掉 5 份 CSV 读取 + 4 份 JSONL 读取
3. `core/text.py` 吃掉 16 份 `shorten/short_text/dedupe/unique`
4. `core/scoring.py` 统一 4 份打分器（先取并集权重，再用 `data/eval/rag_retrieval_v2.jsonl` 做 A/B 确认排序不变）
5. `core/domain.py` 建三张声明式表：`answer_type → (选卡, 降级文案, 检索过滤)`、`coverage_level`、`freshness`；把 14 处 `answer_type` 分支收敛
6. `retrieval/port.py` 把 8 个方法全写进协议，删 3 处 `hasattr`
- **验收**：`pytest` 全绿；`grep -c "if answer_type"` 从 14 降到 ≤3；静态检查确认无同名重复类
- **风险**：中高（打分器换权重会改变答案排序 → 必须用评测集对比）

#### P4 执行记录（2026-10-25，前两步完成）

| 动作 | 结果 | 提交 |
|---|---|---|
| 合并两份 `EvidenceCard` | `aika_core/models.py` 的类扩成 35 字段并集（保留原字段顺序，尾部追加 `semantic_score` / `semantic_ref_id` / `candidate_ids` / `retrieval_agent`）；`professional_qa` 改成 re-export；`to_dict()` 统一（`relation_label` 只留在提示词 payload 里） | `5cb838c` |
| 明确后端契约 | `ResearchBackend` 从 4 个抽象方法扩到 7 个命名方法（新增 3 个带 `NotImplementedError` 默认实现的「可选能力」） | `831d220` |
| 删 4 个转发壳 | `aika_core/{brief,compare,gaps,profiles}.py`（75 行）删除；它们唯一的引用方是 `aika_core/__init__` 的再导出，真正的调用方（MCP tools / CLI）本来就直连 backend 方法 | `831d220` |

实测：`professional_qa.EvidenceCard is aika_core.models.EvidenceCard` 为 True；CSV backend 现在返回 `aika.aika_core.models.EvidenceCard`（此前返回另一个同名类）；API 返回的每张证据卡 35 个键；端到端 19.6s / `verify=pass`。

**仍未做**（P4 后半）：`core/io.py`（5 份 CSV + 4 份 JSONL 读取器）、`core/text.py`（16 份截断/去重）、`core/scoring.py`（4 份打分器，权重 `12/5/1` vs `3/0.8/0.6`）、`answer_type` 14 处分支收敛。

**打分器（P4 第 3 项）的处理方式**：查了 4 份打分器之后，决定**不合并公式**——它们排的是不同对象（claim / chunk / evidence row / PG row），信号也不同（claim_type 权重、BM25、source_type 加成）。强行合并会改变结果排序，而仓库里没有任何排序质量的测试覆盖。

实际做的是把**重复的零件**收敛：

| 零件 | 之前 | 现在 |
|---|---|---|
| 归一化 | `claims._normalize`、`sqlite_backend._normalize`、`rag_index.normalize_text` 三份逐字相同；`postgres_retrieval` 从 `rag_index` 借 | `aika_core/text.py::normalize_text` 一份，三处变别名，`postgres_retrieval` 直接 import 共享实现（`d6319eb`） |

同一份代码里仍有 **两套权重**（`12.0/5.0/1.0` 与 `3.0/0.8/0.6`），但它们属于不同的打分器、不同的字段，不是同一个常量的两个值。若以后要统一，先要有 `data/eval/rag_retrieval_v1.jsonl` 上的排序基线。

| 新增 | 说明 | 提交 |
|---|---|---|
| `aika_core/io.py` | `read_csv_rows` / `read_jsonl_rows` / `append_jsonl_row`。5 份 CSV 读取器、4 份 JSONL 循环收敛到 1 份；`extraction_schema.read_csv` / `load_jsonl` 变成委托（它们是事实上的公共读取器，被 5 个模块 import） | `adf5280` |
| `aika_core/text.py` | `collapse` / `shorten`（`marker` / `reserve` / `strip_tail` 三个关键字覆盖历史上三种截断策略）/ `dedupe_strings`。17 处截断实现收敛；三处「按归一化 key 去重」的实现保留（规则不同，不是拷贝） | `06af554` |
| 顺带修的回归 | `aika/cli_heavy.py` 原来在模块级 `from aika.qa_engine import QAEngine`，合并 CLI 后导致 `aika init/doctor/demo` 全部拉进 psycopg，被 `aika doctor` 的 `postgres_not_required` 检查抓到（WARN）。改成 `build_engine()` 内部导入 | `8c39c19` |

故意**没有**合并的读取器（策略真的不同）：`aika_core/knowledge_pack.py`（要把坏行变成 `KnowledgePackIssue`）、`aika/agents/store.py` 与 `aika/eval/store.py`（append-only 日志，跳过坏行而不是整体失败）、`aika_mcp/server.py` 等处的 stdio/JSON-RPC 循环（协议帧，不是数据行）。

| 新增 | 说明 | 提交 |
|---|---|---|
| `aika_core/domain.py` | 6 种 `answer_type` 的声明式画像（`coverage` / `claim_types` / `relations` / `needs_comparison` / `needs_risk` / `research_oriented`）+ 唯一 `ANSWER_TYPES` 元组 + `required_coverage()`。`planner.required_coverage_for_plan` 改为委托，`professional_qa` 的选卡 if 链改成 dispatch dict，`question_planner` 的 `allowed_types` 字面量删除 | `ee41f97` |

`answer_type` 分支数 44 → 35。**没有继续压到计划里的 ≤3**，原因是查过剩下的 35 处：它们不是「重复的规则」，而是**每种类型各自的文案与检索动作**（`fallback_professional_answer` 的 6 段模板、`research_claims.claim_relevance` 的 claim_type 过滤、`graphrag.QueryRouter` 的路由）。把这些也塞进表里，只会把可读的分支变成难以阅读的数据结构。真正能再降的是 `research_claims` 的 4 处 claim_type 判定（可并入 `profile.claim_types`），但会改变 claim 排序，需要先有评测基线。


### P5　拆 god module（3 天）— 阅读体验的最大跃升
1. `qa_engine.py` 2,624 → `qa/` 下 12 个文件：
   `engine.py`(≤150) `factory.py`(260) `settings.py`(60) `pipeline.py`(250) `history.py`(250) `contextualizer.py`(160) `hyde.py`(155) `planning.py`(40) `progress.py`(115) `composer.py`(130) `evidence.py`(32) `graph/subgraph.py`(235)
2. **合并双份流水线**：`_answer_question_workflow` / `_answer_question_stream_workflow` → 一个生成器 + 同步适配器（−210 行，消掉流式/非流式行为漂移）；`_generate_answer` / `_generate_answer_stream` 同理
3. 修依赖倒置：`agent_tools.py:350` 不再 import qa_engine 的 `ensure_relation_cards`；`_search_rag` 里的公司过滤规则移到 `retrieval/filters.py`
4. 修潜在无限递归：`agents/qa_agent.py:56` 回落 `engine.answer_question` 会回到 `QAAgent.run`（缺 6 个私有方法之一即栈溢出）
- **验收**：`qa_engine.py` 不再存在；`pytest` 全绿；`llm_calls` 计数与旧实现一致（用同一问题对比 diagnostics）
- **风险**：高（11 个 import 方）。护栏 = P1 修好的测试 + P4 的统一形状

#### P5 执行记录（2026-10-25）

已完成的拆分（纯结构，函数体一行未改，全部由 `pytest` + CLI 冒烟验证）：

| 目标 | 之前 | 之后 | 提交 |
|---|---|---|---|
| `aika_core/backends/sqlite_backend.py` | 1,255 行单文件 | 包 `aika_core/backends/sqlite/`：`util`(54) `schema`(172) `query`(159) `rows`(185) `index`(339) `backend`(393) `__init__`(43)；`sqlite_backend.py` 变 33 行 re-export shim，5 个引用方与测试的 import 不动 | `1e15a82` |
| `aika/qa_engine.py` | 2,624 行 | `aika/qa/`：`types`(17) `constants`(41) `text`(290) `history`(323) `subgraph`(280)；引擎本体 1,336 行 | `a24d3af` |
| `aika/research_claims.py` | 1,555 行单文件 | 包 `aika/research/`：`constants`(291) `hits`(99) `claims`(408) `technical`(252) `dossiers`(105) `review`(97) `scoring`(142) `artifacts`(76) `memory`(185) `__init__`(132)；`research_claims.py` 变 19 行 shim | `9afd4f3` |
| `aika/aika_mcp/tools.py` | 1,077 行单文件 | `aika_mcp/`：`common`(221) `verify`(44) `markdown`(282) `cards`(111) `queries`(182) `pdf`(61) `research_task`(88) `tools`(180)；`tools.py` 重新导出全部 handler | `9203ef5` |
| `aika/langchain_tools.py` | 114 行 | 删除（从未被真正调用） | `29e087f` |
| `aika/agents/centralized.py` | 1,024 行 | 包 `aika/agents/coordination/`：`models`(148) `budget`(83) `support`(152) `planning`(257) `synthesis`(314) `coordinator`(112)；`centralized.py` 变 53 行 shim | `024f39b` |
| `aika/postgres_retrieval.py` | 1,385 行 | 包 `aika/retrieval/postgres/`：`common`(111) `store`(103) `rag_sync`(177) `claim_sync`(267) `embeddings`(166) `rag`(120) `memory`(319) `semantic`(202)；`postgres_retrieval.py` 变 40 行 shim，5 个引用方与测试的 import 不动 | `d04cd51` |

拆 `sqlite_backend` 时的三个坑（都记在这里，避免下次重犯）：

1. 生成脚本按 `MODULE_ORDER` 写入时用了不带 `.py` 的文件名 → 生成了一堆没有扩展名的文件，Python 导入时报告的是**旧文件**的行号，极难定位。落盘路径要用 `module + ".py"`。
2. 同模块内的常量必须在函数**之前**输出：`def profile_knowledge_dir(..., profile: str = DEFAULT_PROFILE)` 的默认值在 def 执行时求值，`DEFAULT_PROFILE` 若排在后面就 `NameError`。
3. 计算「跨模块依赖」时，模块名要统一带或不带 `.py`。混用会让自引用（`util.py` 里 `from ...sqlite.util import _text`）被当成跨模块依赖输出 → 循环导入。

拆分 `research_claims` 与 `aika_mcp/tools` 时又踩到两个坑：

4. **装饰器不在 `def`/`class` 的 `node.lineno` 范围内**。按 `node.lineno` 切分会静默丢掉 `@dataclass`，症状是 `ResearchHit() takes no arguments`。切分起点必须取 `min(node.lineno, 最小 decorator.lineno)`，并加一条护栏：比对原文件与拆分后包内装饰器总数（`1 == 1`）。
5. **按依赖分组时会撞上双向依赖**。`markdown` 需要 `cards._normalize_gaps`、`cards` 又需要 `markdown._compose_research_markdown`；同理 `tools` 与 `research_task` 互相需要 `_collect_graph_edges` / `_run_research_task`。解法是把被双向引用的那个函数下移到更底层（`common` 或 `queries`），而不是用函数内 import 掩盖。

**剩余 god module 的执行情况**：

| 顺序 | 文件 | 行数 | 状态 |
|---|---|---|---|
| 1 | `aika/research_claims.py` | 1,555 | ✅ 已拆（`9afd4f3`） |
| 2 | `aika/aika_mcp/tools.py` | 1,077 | ✅ 已拆（`9203ef5`） |
| 3 | `aika/agents/centralized.py` | 1,024 | ✅ 已拆（`024f39b`） |
| 4 | `aika/postgres_retrieval.py` | 1,385 | ✅ 已拆（`d04cd51`），且本机已装 ParadeDB 完成行为验证（见下） |

拆分 `centralized` 与 `postgres_retrieval` 时新增的三个坑：

6. **「先写 shim 再跑脚本」会把自己的源文件覆盖掉**。第二次运行时脚本读到的已经是 shim（44 行），于是 `KeyError`。恢复靠 `git checkout -- <源文件>`。正确顺序永远是：生成新包 → 最后一步才写 shim；如果要重跑，先 checkout 回原文件。
7. **符号登记只看顶层 `body`**。用 `ast.walk(piece)` 会把方法名与局部变量都收进 `symbol_home`，`__all__` 里冒出上百个假名字。只遍历 `ast.parse(dedent(piece)).body`；mixin 模块直接跳过、只登记类名。
8. **包内相对路径常量会随目录深度变化**。`ROOT_DIR = Path(__file__).resolve().parents[1]` 在 `aika/postgres_retrieval.py` 里指向仓库根，搬到 `aika/retrieval/postgres/common.py` 后 `parents[1]` 变成了 `aika/retrieval`，`MIGRATIONS_DIR` 会指向不存在的目录、`migrate_database()` 静默不建表。拆分脚本里对 `__file__` 派生的常量必须重新计算层级。

拆完之后 `aika/` 的最大文件从 2,624 降到 1,336（`qa_engine.py`），其次是 `research_agent.py` 777、`agent_runner.py` 805、`professional_qa.py` 768、`aika_cli.py` 711。

#### P5e 的 PostgreSQL 行为验证（本机新装 ParadeDB）

`aika/postgres_retrieval.py` 是唯一"拆完无法验证行为"的模块，为了不把风险留到后面，本机这次真的把 PostgreSQL 跑起来了：

```
docker run -d --name aika-pg -e POSTGRES_USER=aiqasys -e POSTGRES_PASSWORD=aiqasys \
  -e POSTGRES_DB=aiqasys -p 5432:5432 -v aika_pg_data:/var/lib/postgresql/data \
  paradedb/paradedb:0.24.0-pg17
python scripts/migrate_postgres.py        # Applied migrations: 001_postgres_retrieval
python scripts/build_curated_graph.py --no-write --sync-postgres
                                          # Synced claims=305 dossiers=8 -> PostgreSQL
```

拆分前后各跑一次 `.tmp/analyze/pg_probe.py`（同一批调用：`ensure_ready` / `chunk_ids` / `corpus_metadata` / `semantic_rag_chunk_ids` / `pending_embeddings` / `claim_stats` / `search_local_claims` / `search_global_dossiers` / `search` / `rag.corpus_hash` / `rag.search`），输出**逐字节相同**；`pytest` 248 passed / 1 skipped；PD 版 `QAEngine.answer_question` 走 PG 记忆层返回 `research_hits=11`（纯 CSV 时是 3）。

### P6　后端收敛（1.5 天）
1. 定 **SQLite FTS5 为默认、PostgreSQL 为可选增强**；CSV 后端降级为"无索引时的兜底"
2. 6 条死/半死后端删除或在 `__init__` 里改惰性导入（当前 `backends/__init__.py` 聚合 import 三个后端 → `import aika.aika_core.backends.sqlite_backend` 会连带拉进 jinja2/psycopg，干净环境直接 `ModuleNotFoundError`）
3. `postgres_retrieval.py` 1,385 → `retrieval/postgres/{store,sync,rag,semantic,memory}.py`（SQL 提为模块常量）
4. 让 `data/curated/{claims,evidence_spans,segment_dossiers}` **可重建**：`build_research_artifacts` 的 `write_outputs=False` 硬编码（两个脚本都这么传）改成 `--write-csv`，PG 同步变可选 —— 否则这 592 KB 是"不可再生的历史产物"，你永远无法重新生成自己的数据
- **验收**：无 PG 环境下 `aika build-index && aika demo` 全通；断网 + 无 PG 下 9 个 MCP 工具全可用

#### P6 部分执行（2026-10-25）

| 动作 | 结果 | 提交 |
|---|---|---|
| `aika_core/__init__.py` 改惰性导出（`__getattr__` 表 22 项） | `import aika.aika_core.models` 不再拉 CSV/报告层 | `9825120` |
| `aika_core/backends/__init__.py` 改惰性导出（3 个后端） | 三后端各自依赖互不牵连 | `9825120` |
| `sqlite_backend.build_research_brief` 内部才 import `aika.report` | 存储层不再在 import 期依赖 jinja2 | `9825120` |
| 修 `data_config` 的「读前先写」 | `load_companies` / `load_research_keywords` / `load_industry_sources` 读不存在文件时回落到内存默认表，**不再往 site-packages 写 CSV**（安装态首问 PermissionError 的根因） | `d2c2379` |
| `host_configs` 增加解释器回退 | 没有 `uv` 的机器上 `aika mcp doctor` 也能 PASS（改用 `python -m aika.aika_mcp.server`） | `2dd682b` |

实测：`import aika.aika_core.backends.sqlite_backend` 之后 `sys.modules` 里**没有** `aika.professional_qa` / `aika.report` / `jinja2` / `psycopg`（此前四个全在）。


### P7　Web 层拆分（2 天）
1. `api.py` 772 → `api/app.py`(60) + `routers/`(5) + `services/chat_turn.py` + `services/export.py` + `deps.py` + `errors.py`
2. 合并 JSON/SSE 两条路径的 4 段重复（校验 / 取历史 / normalize / turn 组装）
3. 给 21 个端点加 `response_model`（Pydantic），消除与 `types.ts` 的 3 处漂移（`settings` 缺 4 字段、`ClaimReviewRequest` 17 vs 10 字段、`GraphEdge` 多 4 个死字段）
4. `App.tsx` 2,987 → 约 25 个文件；`css` 按域拆 8 个文件
5. `ENTITY_ORDER` 单一来源（当前 Python 18 类 vs 前端 11 类，7 类掉进 fallback 样式）
- **验收**：`npm run build` 通过；`/api/status`、`/api/graph/subgraph`、会话 CRUD、流式问答 手工回归通过

### P8　品牌化（1 天）— 变成"你的项目"
1. 改名（包名 / 发行名 / CLI 名 / 前端 title / MCP server info）
2. 重写 `README.md`（628 → ≤200 行，只留一条主线）
3. `log/direction.md`（561 行）、`log/v0.0.0-v0.0.1plan.md`、根 `plan.md`（516 行）、三份 `*_AUDIT.md` 收进 `docs/`，明确标注"历史设计文档"
4. 删除 `Dockerfile` / `docker-compose.yml`（若 P6 决定不走 PG）或保留并修好
5. 加 `LICENSE`（若沿用需保留原许可声明）、`.editorconfig`、`ruff` + `mypy` 配置
- **验收**：从零 clone → 按 README 5 条命令跑通；`aika --help` 不再出现 `aiqasys`

---

## 七、量化目标

| 指标 | 现在 | 目标 | 变化 |
|---|---|---|---|
| Python 代码行 | 31,151 | ~19,000 | **−39%** |
| 最大单文件 | 2,624 | ≤400 | −85% |
| 存储后端 | 8 条 | 2 条（SQLite 默认 / PG 可选） | −75% |
| CLI 入口 | 3 个（1 个不可达） | 1 个 | −67% |
| 测试通过率 | 239/249（96%，9 个 Windows 失败） | 249/249 | 全绿 |
| 同名重复类 | 6 组 | 0 | — |
| MCP 工具清单 | 3 份、互相矛盾 | 1 份 | — |
| 测试收集率 | 100%（.venv 装齐依赖后） | 100% | 保持 |

---

## 八、需要你决策的 4 件事

### 决策 1（最关键）：保留哪条主线？
| 方案 | 内容 | 结果 | 工期 |
|---|---|---|---|
| **A（推荐）** | 以**轻量 MCP + SQLite** 为主线，Web UI 降级为"可选的只读查看器"，PostgreSQL/Neo4j 变可选增强 | 代码 ~13k，最符合你们自己的 `direction.md`；容易维护、真能发布 | 8 天 |
| B | 两条线都保留，抽公共内核（`core/` + `retrieval/`）给两边用 | 代码 ~19k，UI 与 MCP 都完整；但 PG 环境你本地要装 Docker | 12 天 |
| C | 只留 Web 全栈（FastAPI + React + PG），删 MCP/CLI 分发线 | 代码 ~20k，最像"毕设演示"；但抛弃了唯一可发布形态 | 10 天 |

### 决策 2：数据基线用现成的还是重建？
`data/curated/{claims,evidence_spans,segment_dossiers}`（592 KB）当前**无法重新生成**（两个脚本都硬传 `write_outputs=False` 并强制连 PG）。三个选项：
- 直接用已提交产物（0 天，但你不是"拥有"这份数据）
- 修成可重建 + 用 `--mock` 离线跑一遍（1.5 天，能生成自己的样本）
- 接真实年报 PDF 重跑 LLM 抽取（3 天 + API 费用，产物最"真"）

### 决策 3：要不要现在改名？
改包名会动所有 `import`（94 个文件）与 `pyproject.toml`。建议放在 P8 一次性做；若你想早点看到"自己的名字"，可以只改**发行名 + CLI 名 + README**（不动 Python 包名），半天。

### 决策 4：PostgreSQL / Neo4j 留不留？
若你本地不想跑 Docker，P6 会把它们改成"惰性导入 + 缺配置时自动降级"，功能保留但不阻塞。若要彻底删，可再省 ~2,400 行。

---

## 九、风险与回滚

| 风险 | 概率 | 缓解 |
|---|---|---|
| 拆 `qa_engine` 时行为漂移（尤其流式事件序列） | 高 | P1 先把 249 条测试修绿；P5 前用旧实现录制 20 个问题的 `diagnostics` 快照做黄金对比 |
| 统一打分器改变排序 | 中 | 用 `data/eval/rag_retrieval_v2.jsonl`（50 例）做排序一致性 A/B |
| 删死码时误删"看似死但其实被 CLI 触达" | 中 | 已用全仓 import + 字面量 grep 双向确认；P2 每一步单独 commit |
| 入口合并破坏 Docker/CI | 中 | P3 同步改 `Dockerfile:18`、`docker-compose.yml:39`、`ci.yml:35,38,41`、`publish.yml:36-41` |
| 无 git 历史导致不可回退 | **高** | **P0 必须先 `git init` 并提交基线** |

回滚策略：每个阶段独立 commit + tag（`v0.1.4-p0` … `p8`），任一阶段验收失败即 `git reset --hard` 回上一 tag。

---

## 十、本机环境备忘（已踩通的坑）

```powershell
# 1) 建 venv（本机 DSH 沙箱下 mkdtemp 生成的目录不可写，需要 .tmp/pyshim/sitecustomize.py 把 os.mkdir 强制成 0777）
python -m venv .venv
# 若 ensurepip 报错，手动补：
.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip

# 2) 装依赖（必须先装 hatchling + editables；jieba 只能从 sdist 构建）
.venv\Scripts\python.exe -m pip install hatchling editables setuptools wheel
.venv\Scripts\python.exe -m pip install -e ".[dev]" --no-build-isolation

# 3) 装前端
cd web; npm install

# 4) 跑测试（必须在工作区内指定 basetemp，否则 %TEMP% 会踩 ACL）
.venv\Scripts\python.exe -m pytest -q --basetemp=.tmp\pytestbase

# 5) 跑公开线
$env:AIKA_HOME="$PWD\.tmp\aikahome"
.venv\Scripts\aika.exe init --sample
.venv\Scripts\aika.exe build-index      # ← 当前会崩，等 P1 修 W1
.venv\Scripts\aika.exe demo
.venv\Scripts\aika.exe doctor

# 6) 跑后端（无 PG 模式）
$env:QA_DISABLE_POSTGRES="true"
.venv\Scripts\python.exe -m uvicorn aika.api:app --host 127.0.0.1 --port 8000

# 7) 跑前端（另开一个终端）
cd web; npm run dev     # 代理到 127.0.0.1:8000
```

#### P7 断路补齐（2026-10-25）

审计里被标记为「断路 / 不可重建」的三处，现在都有了可执行的本地路径。

| 断点 | 之前 | 现在 | 验收 |
|---|---|---|---|
| \data/curated\ 不可再生成 | 两个脚本硬传 \write_outputs=False\ + 无条件连 PG | 默认写盘，\--sync-postgres\ 才连库；新增 \ika build-artifacts\ | \entities=285 relations=278 claims=305 evidence_spans=305 dossiers=8\，全程无 PG |
| \ika eval --suite agent\ 依赖 \scripts/\ | wheel 安装后必 \ImportError\ | 评估集与评分规则移入 \ika/eval/agent_tasks.py\ | /4 accuracy=100.0%\ |
| \ika eval --suite rag\ 硬连 PG | 没有 PG 直接崩 | \--offline\ 或 PG 不可用时走 \LocalRagIndex\；\scripts/build_rag_index.py\ 真的构建本地索引了 | 无语料时给出可执行的下一步提示，退出码 2 |

语料缺口（不是代码缺陷）：

- \data/eval/qa_benchmark_v1.jsonl\ 50 例全是 \company_compare\，目标公司不在样例包里，\human_score\ 也未标注 → 样例包上 0 召回属于数据范围问题。
- \data/curated\ 重建出的 305 条 claim 是已提交 568 条的子集，缺的 263 条来自 \claims_from_technical_chunks\，需要 \data/chunks\（仓库内只有 \.gitkeep\）。

---

## 附录：三份完整审计报告的落点

| 文件 | 内容 |
|---|---|
| `AGENT_LAYER_AUDIT.md` | 编排层：三套 runner、`centralized.py` 逐类拆解、三份工具清单、5 处 `task_type` 注册表、9 项简化机会 |
| `DATA_LAYER_AUDIT.md` | 数据/存储层：8 条后端矩阵、检索链调用图、`data/` 资产地图、11 处分层污染、`data/curated` 不可再生、Windows bug 复现步骤 |
| `QA_REPORT_LAYER_AUDIT.md` | 合成/报告层：`qa_engine` 方法级拆分映射、答案合成链路与 LLM 调用次数、`plan.md` P0–P6 落地对照、claims 三条写入路径不一致、评测断路、测试行为契约 12 条 |
