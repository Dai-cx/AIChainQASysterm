# AIKA · AI 算力产业链投研多 Agent 助手

面向 AI 算力产业链（AI 服务器、芯片、光模块、液冷、数据中心）的证据驱动问答系统。每条结论都带证据卡与 claim 引用，证据缺口会被显式列出，而不是编一个答案出来。

![问答界面](docs/screenshots/02-answer.png)

<sub>截图：一次真实问答。左侧是会话历史，右侧答案的 `[E1]`–`[E6]` 都能在证据卡里点开原文位置。</sub>

同一个内核有四种用法，全部只需要 `aika` 一个命令：

| 用法 | 命令 | 需要什么 |
|---|---|---|
| 本地问答 / 检索 | `aika demo`、`aika search-evidence`、`aika search-claims` | 无（SQLite FTS5 + 仓库内数据） |
| 接进 Claude Code / Codex | `aika mcp install --host claude-code` | 无（9 个 MCP 工具） |
| 网页查看器（问答 / 图谱 / 评测 / 任务） | `aika api` + `aika web` | Node 20+ |
| 更强的检索（BM25 + pgvector 语义） | `docker compose up -d db` | Docker |

- Python `>=3.11`
- 测试：`pytest` 全绿（246 passed / 1 skipped）
- 一次真实问答：`aika showcase`（LLM 可选，没有 API Key 时退化为"证据堆砌"）

---

## 一、五分钟跑起来

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
pip install -e .
aika init --sample          # 复制内置样例知识包到 ~/.aika（或 $AIKA_HOME）
aika build-index            # 建 SQLite FTS5 索引
aika doctor                 # 自检：目录 / 索引 / MCP / 样例查询
aika demo                   # 跑一次样例问答
```

`aika init --sample` 之后本地目录结构：

```
~/.aika/
├── knowledge/sample/       claims.csv / evidence_spans.csv / segment_dossiers.jsonl
│                           entities.csv / relations.csv / manifest.csv
├── indexes/sample.sqlite   由 build-index 生成（claims / evidence_spans / dossiers / relations 四张表 + FTS5）
└── logs/
```

换成自己的知识包：把同样七个文件放进一个目录，`aika validate-data --path <目录>` 校验通过后，用 `aika init --home <目录>` 指过去即可。

---

## 二、命令行（唯一入口 `aika`）

| 分组 | 命令 | 作用 |
|---|---|---|
| 数据 | `init` | 初始化本地目录（`--sample` 复制样例包） |
| | `validate-data --path DIR` | 校验知识包（列名、必填、重复 id） |
| | `build-index` | 建 SQLite FTS5 索引 |
| | `build-artifacts --relations CSV` | 从关系表重建 claims / evidence_spans / dossiers |
| 查询 | `search-evidence QUERY`、`search-claims QUERY` | 在本地索引里检索（`--company` / `--topic` / `--top-k`） |
| | `demo`、`showcase` | 样例问答；`showcase` 是完整的 QA + Agent 走查 |
| 诊断 | `doctor` | 目录、索引、MCP 服务器、样例查询一次性自检 |
| MCP | `mcp config --host claude-code` | 打印宿主所需配置（不写文件） |
| | `mcp install --host codex --scope user` | 写入宿主配置（`--dry-run` 只看不改） |
| | `mcp doctor` | 检查 MCP 服务器能否被宿主拉起 |
| Skill | `skill list`、`skill install --host codex`、`skill doctor` | 管理 `skills/aika-research` 插件 |
| 任务 | `agent GOAL --type research_brief` | 跑一次 ResearchAgent 任务 |
| 评测 | `eval --suite qa\|rag\|agent` | 三套评测（见第六节） |
| Web | `api --port 8000`、`web --api http://127.0.0.1:8000` | 启动查看器后端 / 前端 |

MCP 一共暴露 9 个工具：`search_evidence`、`search_claims`、`get_company_profile`、`compare_companies`、`query_industry_graph`、`build_research_brief`、`audit_evidence_gaps`、`run_research_task`、`render_report_pdf`。

---

## 三、接进 AI 客户端（MCP + Skill）

```bash
aika mcp install --host claude-code --scope user --with-skill
aika mcp doctor
```

Claude Code 与 Codex 的配置文件由命令生成，不需要手写 `.mcp.json` / `~/.codex/config.toml`。没有 `uv` 的机器会自动回退到当前解释器（`python -m aika.aika_mcp.server`），不要求额外安装。

---

## 四、数据来自哪里

仓库里有三份数据，用途不同：

| 目录 | 内容 | 规模 |
|---|---|---|
| `data/knowledge_packs/sample` | 打包进 wheel 的样例知识包（7 个文件） | 160 claims / 160 evidence spans / 5 dossiers / 85 relations |
| `data/curated` | 人工整理过的投研文物 | 305 claims / 305 evidence spans / 8 dossiers；图谱只有 1 家公司 |
| `data/verified` | 从 61 份 PDF 抽取并校验过的图谱 | 768 实体 / 48 家公司 / 1,219 关系 |

- 问答默认用**最丰富的图谱**：`data/verified` 优先，缺失时才回退 `data/curated`（`aika/aika_core/data_paths.py::resolve_graph_dir`）。
- `data/curated` 的文物可以重建：`aika build-artifacts --relations data/curated/relations.csv --output /tmp/regen`。只从关系表重建会得到 305 claims；要覆盖全部 568 条（含技术报告类 claim）需要 `data/chunks/`，仓库里这份语料没有随代码提供。

---

## 五、可选：PostgreSQL（真正的 BM25 + 向量检索）

不装也能用——本地 SQLite 与图谱走的是另一条通路。装了之后检索更快，并且支持语义检索。

```bash
docker compose up -d db                       # ParadeDB 0.24.0 (pg17)
export DATABASE_URL=postgresql://aiqasys:aiqasys@localhost:5432/aiqasys
python scripts/migrate_postgres.py            # 建表
python scripts/build_curated_graph.py --sync-postgres   # 灌入 claims / dossiers
export QA_DISABLE_POSTGRES=false
```

`QA_DISABLE_POSTGRES=true`（默认）时，所有检索都走本地路径，不会尝试连接数据库。

---

## 六、评测

```bash
aika eval --suite agent --offline      # 15 个 Agent 任务，离线可跑
aika eval --suite qa --limit 10        # 50 条 QA benchmark（需要完整语料）
aika eval --suite rag                  # 50 条检索 benchmark（需要 PG + 完整 chunk 语料）
```

现状要如实说：`qa` 与 `rag` 两套 benchmark 是按**完整语料**标注的（例如"中际旭创 vs 新易盛"），样例包与 curated 子集里没有这些公司，所以在样例数据上跑出来召回是 0——这是数据范围问题，不是代码缺陷。`agent` 套件在样例数据上是满分的。

---

## 七、配置

所有配置走环境变量（或 `.env`，由 `aika/llm_client.py` 读取，自动 `strip()`）：

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 任意 OpenAI 兼容端点（默认 DeepSeek） |
| `QA_ENABLE_AGENT` | 是否用 Agent 编排（默认 true；false 时走确定性 workflow） |
| `QA_AGENT_MAX_STEPS` | Agent 最大步数（默认 4） |
| `QA_DISABLE_POSTGRES` | 默认 true；只在真的起了数据库时改成 false |
| `AIKA_HOME` | 本地数据根目录（默认 `~/.aika`） |
| `KG_DATA_DIR` | 图谱目录；留空自动挑最丰富的一份 |
| `DATABASE_URL` | PostgreSQL 连接串（可选） |

完整清单见 `.env.example`。

---

## 八、代码结构

```
aika/
├── aika_cli.py          唯一命令入口（15 个子命令）
├── cli_heavy.py         api / web / agent / eval / showcase 的实现
├── aika_core/           领域模型、存储后端（SQLite / CSV）、io / text / domain 公共件
├── research/            claim 构造、打分、dossier、记忆
├── retrieval/           PostgreSQL 检索层（common / store / rag / memory / semantic / sync）
├── qa/                  文本归一化、HYDE、历史压缩、子图组装
├── qa_engine.py         问答引擎（编排 + 报告数据）
├── agents/              planner / executor / verification / coordination（多智能体编排）
├── report/              ReportSpec、markdown / html / pdf 渲染、图表
├── aika_mcp/            MCP 工具面（9 个工具）+ 宿主配置 + doctor
├── eval/                QA / RAG / Agent 三套评测
└── api.py               FastAPI（Web 查看器后端）
web/                     React + Vite 查看器
data/                    样例知识包、curated 文物、verified 图谱、评测基准
scripts/                 数据准备与迁移脚本
tests/                   pytest（35 个文件）
```

---

## 九、开发

```bash
pytest                                  # 248 passed / 1 skipped
ruff check aika tests scripts           # pyflakes + isort
aika doctor                             # 端到端自检
cd web && npm install && npm run build  # 前端构建
```

- `REPRODUCTION.md`：在这台机器上从零复现的完整命令序列（含 Windows 上踩过的坑）。
- `REFACTOR_PLAN.md`：这次重构的问题清单、目标架构与逐阶段执行记录。
- `docs/legacy/`：历史设计文档与一次性脚本，仅作留档。

已知边界：`data/curated` 图谱只覆盖 1 家公司（完整图谱在 `data/verified`）；`data/chunks` 语料未随仓库提供，因此 `data/curated` 的 263 条技术报告 claim 无法从零重建；`aika eval --suite rag` 需要 PostgreSQL。
