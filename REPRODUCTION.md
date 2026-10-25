# 复现手册（Windows 实测通过）

> 本文件记录「从零到看见成果」的每一步，全部命令均在本机（Windows 11 / Python 3.13 / Node 24）实测通过。
> 记录时间：2026-10-25。测试结果：**248 passed, 1 skipped**。

---

## 0. 一句话结论

项目能在 Windows 上跑起来，但**开箱即崩**：原始代码有 5 个只在 Windows 暴露的缺陷（详见 §6），
修完之后 `pytest` 全绿、`aika demo` 有输出、FastAPI + React 前端能端到端问答并出证据卡片。

---

## 1. 环境要求

| 组件 | 版本 | 备注 |
|---|---|---|
| Python | 3.13.14 | 项目声明 `>=3.11`，`.python-version` 写的是 3.11 |
| Node.js | 24.18.0 | 前端构建 |
| 浏览器 | Chrome / Edge | 截图用，非必需 |

---

## 2. 安装依赖（含两个必须的绕行）

### 2.1 临时目录需要"可写模式"补丁

本机 `%TEMP%` 下的目录 ACL 很严，而 `tempfile.mkdtemp()` 建目录用的是 `0o700`，
于是 pip / venv / pytest 往临时目录里写文件时全部 `PermissionError`。
建一个 `sitecustomize` 把 `os.mkdir` 的默认 mode 改成 `0o777` 即可绕开：

```powershell
# .tmp/pyshim/sitecustomize.py
$shim = @'
from __future__ import annotations
import os
_orig_mkdir = os.mkdir
def _mkdir_mode_777(path, mode=0o777, *args, **kwargs):
    return _orig_mkdir(path, 0o777, *args, **kwargs)
os.mkdir = _mkdir_mode_777
'@
New-Item -ItemType Directory -Force -Path .tmp\pyshim | Out-Null
Set-Content -Path .tmp\pyshim\sitecustomize.py -Value $shim -Encoding utf8
$env:PYTHONPATH = "$PWD\.tmp\pyshim"
```

> 这不是项目的问题，是本机沙箱的问题。换一台干净的机器可以跳过。

### 2.2 建虚拟环境

```powershell
python -m venv .venv
# ensurepip 在同款环境下会失败，补跑一次即可
.\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip
```

### 2.3 装依赖

`jieba` 只有 sdist，构建隔离模式在建 wheel 时会崩，所以关掉构建隔离，
并先把构建后端装好：

```powershell
$env:PIP_CACHE_DIR = "$PWD\.tmp\pipcache"     # 默认缓存目录同样被拒
.\.venv\Scripts\python.exe -m pip install --no-build-isolation hatchling editables setuptools wheel
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-cache-dir -e ".[dev]"
```

前端依赖：

```powershell
cd web
$env:npm_config_cache = "$PWD\..\.tmp\npmcache"
cmd /c "npm install --no-audit --no-fund"
cd ..
```

---

## 3. 跑测试

```powershell
$env:PYTHONPATH = "$PWD\.tmp\pyshim"
.\.venv\Scripts\python.exe -m pytest -q
```

```
248 passed, 1 skipped in 8.87s
```

`tests/conftest.py` 会把 pytest 的 `basetemp` 固定到仓库内的 `.tmp/pytest`，
避免 `tmp_path` 再撞上 `%TEMP%` 的权限问题。

---

## 4. 跑公开主线（MCP + SQLite，不依赖数据库）

```powershell
$env:AIKA_HOME = "$PWD\.tmp\aikahome"      # 索引与知识库放仓库内，避免写用户目录
.\.venv\Scripts\aika.exe init --sample
.\.venv\Scripts\aika.exe build-index
.\.venv\Scripts\aika.exe demo
```

实测输出：

```
AIKA home: D:\demo\AIChainQASysterm-main\.tmp\aikahome
Sample knowledge: D:\demo\AIChainQASysterm-main\.tmp\aikahome\knowledge\sample
Built SQLite index: D:\demo\AIChainQASysterm-main\.tmp\aikahome\indexes\sample.sqlite
Counts: claims=160, evidence_spans=160, dossiers=5, relations=85

AIKA local demo
Query: 液冷产业链
Evidence cards: 3
Claims: 3
Top evidence: [E1] UCIe 2.0 Specification ...
Top claim: bottleneck / 液冷
Brief title: 液冷产业链证据覆盖审计报告
```

其它可用子命令：`doctor`、`search-evidence`、`search-claims`、`validate-data`、`skill`、`mcp`。

---

## 5. 跑 Web（可选查看器）

两个终端：

```powershell
# 终端 1：后端
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

打开 <http://localhost:5173/>。

**端到端实测**（无 LLM Key 也能出答案，走的是图谱 + 规则兜底路径）：

- 提问「液冷产业链有哪些关键环节？」→ `answer_type=thematic_research`、6 张证据卡、14 条图记录、答案 578 字
- 提问「紫光股份的液冷业务有哪些风险？」→ `answer_type=risk_analysis`、验证态 `pass`
- 产业链图谱页：**81 节点 / 80 关系 / 48 家公司**（修复前只有 71 节点 / 1 家公司）

截图见 `docs/screenshots/`：

| 文件 | 内容 |
|---|---|
| `01-home.png` | 首屏 |
| `02-answer.png` | 问答结果 + 证据编号 [E1]–[E6] + 证据缺口 |
| `03-graph.png` | 产业链图谱（可见"实体"图例重复 = 已知缺陷） |
| `04-overview.png` | 数据概览 |

### 想接真实大模型

复制 `.env.example` 为 `.env`，填 DeepSeek 的 Key 即可（默认端点已经是 OpenAI 兼容格式）：

```
LLM_API_KEY=sk-xxxx
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

没有 Key 时 `llm_enabled=false`，答案只由图谱与规则生成 —— 能跑通链路，但写不出分析性文字。

---

## 6. 原始代码在 Windows 上的 5 个缺陷（已修）

| # | 位置 | 症状 | 根因 |
|---|---|---|---|
| W1 | `aika/aika_core/backends/sqlite_backend.py` `build_sqlite_index` | `aika build-index` 报 `PermissionError: [WinError 32] ... .sample.sqlite.282832.tmp -> sample.sqlite`，6 个测试连带失败 | `with sqlite3.connect(...)` 只管事务不管文件句柄，句柄没关，Windows 不允许 rename 打开的文件 |
| W2 | `aika/aika_mcp/host_configs.py` | 生成的 MCP 配置里 `command` 变成 `D:\usr\bin\uv` | `Path("/usr/bin/uv").resolve()` 在 Windows 上会把 POSIX 绝对路径改写成本地盘符路径 |
| W3 | `aika/aika_mcp/host_configs.py:18` | 生成的配置写入 `UV_CACHE_DIR=/tmp/uv-cache` | 硬编码 POSIX 临时目录 |
| W4 | `aika/aika_mcp/doctor.py:155,164`、`aika/aika_cli.py:589` | 提示文案让用户去设置 `/tmp/...` | 同上 |
| W5 | `tests/test_aika_core.py` | `query_graph` 断言失败，返回 `[]` | 测试硬编码 `中际旭创`，但 `data/curated` 里根本没有这家公司（整张图只有 1 家 Company） |

另外修了一处"日期炸弹"：`tests/test_report_charts.py` 用 `published_at="2025"` 断言新鲜度为 fresh，
而新鲜窗口是 18 个月 —— 2026 年 10 月跑必然失败。现在 `build_company_coverage_heatmap` 接受 `today` 参数，
测试注入固定日期。

---

## 7. 已知问题（尚未修，属于重构阶段 P2+ 的范围）

1. **curated 图只有 1 家公司**（紫光股份），`data/verified` 有 48 家。
   已修：图谱目录现在由 `aika_core/data_paths.resolve_graph_dir()` 统一解析，优先用 rich 的
   `data/verified`，找不到才退回 `data/curated`（API 与 QA 引擎共用同一个函数）。
   仍存在的隐患：`data/curated` 里那份退化图没有任何代码删除或标注，容易再次被误用。
2. **`data/curated` 里的 claims / evidence_spans / dossiers 重建不出来**：
   两个生成脚本都硬传 `write_outputs=False` 并强制连 PostgreSQL。所以这 592 KB 是"文物"，改不动。
3. **主题研究类问题验证恒为 fail**：`risk_support` 检查在 `thematic_research` 分支下必然失败，
   `risk_analysis` 分支正常。前端会显示"验证未通过"，容易误导。
4. **图谱图例里"实体"重复出现两次**：后端 18 类实体 vs 前端 11 类映射，多出来的类别全掉进同一个 fallback 样式。
5. **`aika eval` 从安装入口不可达**，评测页永远是空态。
6. 无 LLM Key 时答案质量有限（只能堆证据，不能做推理）。

这些问题、以及对应的重构顺序与验收标准，都写在 [REFACTOR_PLAN.md](REFACTOR_PLAN.md) 里。
