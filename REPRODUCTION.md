# 复现手册（Windows 11 / Python 3.13 / Node 24 实测）

> 从零到看见成果的每一步。全部命令都在本机实测通过，记录时间 2026-10-25。
> 当前测试结果：**243 passed, 1 skipped**。
> 一次性排查过的 Windows 缺陷清单已归档到 `docs/legacy/`，本文只记录"现在要怎么做"。

---

## 0. 一句话结论

四条通路都能跑：命令行（SQLite + 仓库数据，不需要任何外部服务）、MCP 服务器、React 网页查看器、
可选的 PostgreSQL 快车道（BM25 + pgvector 语义检索，已用 ParadeDB 容器实测）。

---

## 1. 环境要求

| 组件 | 版本 | 用途 |
|---|---|---|
| Python | 3.13.14（项目声明 `>=3.11`） | 全部后端 |
| Node.js | 24.18.0 + npm 11.16.0 | 网页查看器 |
| Docker Desktop | 29.7.2（可选） | 只有想跑 PostgreSQL 快车道时才需要 |
| Chrome / Edge | 任意 | 只有想跑截图脚本时才需要 |

---

## 2. 一次性环境准备

### 2.1 虚拟环境与依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip   # 若 venv 已自带 pip 可跳过
$env:PIP_CACHE_DIR = "$PWD\.tmp\pipcache"
.\.venv\Scripts\python.exe -m pip install --no-build-isolation hatchling editables setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-cache-dir -e ".[dev]"
```

`--no-build-isolation` 是必需的：`jieba` 只发布 sdist，在隔离构建里会失败。

前端依赖：

```powershell
cd web
$env:npm_config_cache = "$PWD\..\.tmp\npmcache"
cmd /c "npm install --no-audit --no-fund"
cd ..
```

### 2.2 本机特有的两个绕行（换干净机器可跳过）

本机 `%TEMP%` 的 ACL 很严，而 `tempfile.mkdtemp()` 用 `0o700` 建目录，于是 pip / venv / pytest
往临时目录写文件时会 `PermissionError`。用一个 `sitecustomize` 把 `os.mkdir` 的默认 mode 改成 `0o777`：

```powershell
New-Item -ItemType Directory -Force -Path .tmp\pyshim | Out-Null
@'
import os
_orig_mkdir = os.mkdir
def _mkdir_mode_777(path, mode=0o777, *args, **kwargs):
    return _orig_mkdir(path, 0o777, *args, **kwargs)
os.mkdir = _mkdir_mode_777
'@ | Set-Content -Path .tmp\pyshim\sitecustomize.py -Encoding utf8
```

之后每条 Python 命令都带上 `$env:PYTHONPATH = "$PWD\.tmp\pyshim"`。
`tests/conftest.py` 另外把 pytest 的 `basetemp` 固定到 `.tmp/pytest`，所以测试本身不需要额外参数。

---

## 3. 跑测试

```powershell
$env:PYTHONPATH = "$PWD\.tmp\pyshim"
.\.venv\Scripts\python.exe -m pytest -q
```

```
243 passed, 1 skipped
```

---

## 4. 命令行主线（不需要数据库）

```powershell
$env:PYTHONPATH = "$PWD\.tmp\pyshim"
$env:AIKA_HOME = "$PWD\.tmp\aikahome"        # 索引与知识库放仓库内，避免写用户目录
.\.venv\Scripts\aika.exe init --sample
.\.venv\Scripts\aika.exe build-index
.\.venv\Scripts\aika.exe doctor
.\.venv\Scripts\aika.exe demo
```

实测输出：

```
AIKA home: D:\demo\AIChainQASysterm-main\.tmp\aikahome
Sample knowledge: ...\aikahome\knowledge\sample
Built SQLite index: ...\aikahome\indexes\sample.sqlite
Counts: claims=160, evidence_spans=160, dossiers=5, relations=85

AIKA local demo
Query: 液冷产业链
Evidence cards: 3
Claims: 3
Brief title: 液冷产业链证据覆盖审计报告
```

其余命令：`showcase`（QA + Agent 全链路）、`search-evidence`、`search-claims`、`validate-data`、
`build-artifacts`、`agent`、`eval`、`mcp`、`skill`、`api`、`web`。完整列表见 `aika --help` 或 README。

---

## 5. 网页查看器（可选）

两个终端：

```powershell
# 终端 1：后端
$env:PYTHONPATH = "$PWD\.tmp\pyshim"
$env:QA_DISABLE_POSTGRES = "true"
$env:AIKA_HOME = "$PWD\.tmp\aikahome"
.\.venv\Scripts\python.exe -m uvicorn aika.api:app --host 127.0.0.1 --port 8000
```

```powershell
# 终端 2：前端
cd web
$env:npm_config_cache = "$PWD\..\.tmp\npmcache"
cmd /c "npm run dev"
```

打开 <http://localhost:5173/>。前端所有请求都走相对路径 `/api/...`，由 Vite 代理到 `127.0.0.1:8000`
（`web/vite.config.ts`，可用 `VITE_API_PROXY_TARGET` 覆盖）。

**端到端实测**（没有 LLM Key 也能出答案，走图谱 + 规则兜底）：

- 「液冷产业链有哪些关键环节？」→ `answer_type=thematic_research`、6 张证据卡、答案约 580 字
- 「紫光股份的液冷业务有哪些优势？」→ `company_profile`、验证态 `pass`
- 产业链图谱页：**81 节点 / 80 关系 / 48 家公司**
- 截图：`docs/screenshots/{01-home,02-answer,03-graph,04-overview}.png`

截图脚本（Playwright，需要 `TEMP`/`TMP` 指到仓库内，因为 node 侧也会在临时目录建目录）：

```powershell
$env:TEMP = "$PWD\.tmp\playwright-tmp"; $env:TMP = $env:TEMP; $env:TMPDIR = $env:TEMP
.\.venv\Scripts\python.exe .tmp\analyze\shoot_ui.py
```

### 接真实大模型

复制 `.env.example` 为 `.env`，只填 Key 即可（默认端点已是 OpenAI 兼容格式）：

```
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

没有 Key 时 `llm_enabled=false`：链路能跑通，但答案只能堆证据、写不出分析性文字。

---

## 6. 可选：PostgreSQL 快车道（BM25 + pgvector）

不装也能用，装了检索更快并支持语义检索。

```powershell
docker run -d --name aika-pg `
  -e POSTGRES_USER=aiqasys -e POSTGRES_PASSWORD=aiqasys -e POSTGRES_DB=aiqasys `
  -p 5432:5432 -v aika_pg_data:/var/lib/postgresql/data `
  paradedb/paradedb:0.24.0-pg17

.\.venv\Scripts\python.exe scripts\migrate_postgres.py
.\.venv\Scripts\python.exe scripts\build_curated_graph.py --sync-postgres
$env:QA_DISABLE_POSTGRES = "false"
```

实测：迁移 `001_postgres_retrieval` 通过；同步 `claims=305 dossiers=8`；`tests/test_postgres_retrieval.py`
3 passed / 1 skipped；同一问题在 PG 通路下 `research_hits=11`（纯离线 3）。
`docker-compose.yml` 里的 `db` 服务是同一个镜像，用 `docker compose up -d db` 也行。

---

## 7. 现在还有哪些边界（已知，不打算在本次重构里改）

1. **`data/curated` 的图谱只有 1 家公司**（`data/verified` 有 48 家）。问答与 API 都通过
   `aika_core/data_paths.resolve_graph_dir()` 优先取 `data/verified`，所以正常不会用到那份退化图。
2. **`data/curated` 的 263 条技术报告 claim 无法从零重建**：它们来自 `data/chunks/`，这份语料没有随仓库提供。
   仅从关系表重建得到 305 条（`aika build-artifacts`），是已提交 568 条的真子集。
3. **`aika eval --suite qa` 在样例数据上召回为 0**：50 条 benchmark 按完整语料标注（如"中际旭创 vs 新易盛"），
   样例包里没有这些公司。属于数据范围问题；`--suite agent` 在样例数据上是满分。
4. **`aika eval --suite rag` 需要 PostgreSQL 与完整 chunk 语料**，否则 benchmark 里的 `chunk_id` 对不上。
5. 无 LLM Key 时答案质量有限（只能堆证据，不能做推理）。
