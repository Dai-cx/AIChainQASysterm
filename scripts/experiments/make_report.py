"""Render the single-agent vs multi-agent experiment into a markdown report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PLACEHOLDER = "<!-- ANALYSIS -->"

DESIGN = """## 一、实验设计

| 臂 | 检索编排 | 说明 |
| --- | --- | --- |
| `single` | 单趟顺序检索（`QA_ENABLE_AGENT=false`） | 计划 → 图查询 / 向量 / 研究库各一次 → 组装证据 → 生成 → 校验，没有调度 Agent、没有补检 |
| `multi_1` | 多智能体，补检上限 1 轮 | LLM 调度 Agent 拆任务 → 并行 worker → 审核；审核发现缺口时最多再补 1 轮 |
| `multi_3` | 多智能体，补检上限 3 轮 | 同上，缺口未被填上时最多补 3 轮 |

公平性控制：

1. **同一个引擎、同一份知识库**（`data/verified` 768 实体 / 1,219 关系 + `data/curated` 568 条 claim）、同一个 LLM、同一个问题集。
2. **统一裁判**：每题结束后，对臂的最终检索结果跑同一个 `EvidenceCoverageChecker`，按题目自身的覆盖要求打分；不采信臂内部自报的覆盖结论。
3. **同一套指标**：证据覆盖率、冲突组数、证据卡数、引用数、答案字数、延迟、LLM 调用次数、检索轮数。
4. `multi_1` 是消融臂：它与 `multi_3` 的差别只有补检轮数，用来区分「多智能体架构」和「补检闭环」各自的贡献。
"""


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build(payload: dict) -> str:
    rows = [row for row in payload["rows"] if "error" not in row]
    errors = [row for row in payload["rows"] if "error" in row]
    summary = {item["arm"]: item for item in payload["summary"]}
    arms = [arm for arm in ("single", "multi_1", "multi_3") if arm in summary]

    lines: list[str] = []
    lines.append("# 单智能体 vs 多智能体：同一份语料、同一套裁判的对照实验")
    lines.append("")
    lines.append(
        "本报告的数据由 `scripts/experiments/ab_agents.py` 跑出，表格由 `scripts/experiments/make_report.py` 渲染，"
        "所有数字都可以用文末命令复现。"
    )
    lines.append("")
    lines.append(DESIGN)

    lines.append("## 二、总体指标")
    lines.append("")
    lines.append(
        "| 臂 | 题数 | 证据覆盖率 | 校验通过 | 校验告警 | 冲突组数 | 出现冲突的题 | 证据卡 | 引用 | 答案字数 | 延迟 p50 (s) | LLM 调用 | 检索轮数 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for arm in arms:
        item = summary[arm]
        lines.append(
            "| `{arm}` | {n} | {cov} | {passed} | {warn} | {conflicts} | {cq} | {cards} | {cites} | {chars} | {p50} | {llm} | {rounds} |".format(
                arm=arm,
                n=item["n"],
                cov=_fmt(item["coverage_rate"]),
                passed=_fmt(item["verify_pass_rate"]),
                warn=_fmt(item.get("verify_warn_rate", 0.0)),
                conflicts=_fmt(item.get("mean_conflict_groups", 0.0)),
                cq=f"{item.get('conflict_questions', 0)}/{item['n']}",
                cards=_fmt(item["mean_cards"], 1),
                cites=_fmt(item["mean_citations"], 1),
                chars=_fmt(item["mean_answer_chars"], 0),
                p50=_fmt(item["p50_latency_s"], 1),
                llm=_fmt(item["mean_llm_calls"], 1),
                rounds=_fmt(item["mean_rounds"], 1),
            )
        )
    lines.append("")
    lines.append(
        "> 「校验通过/告警」由 `aika/agents/verification.py::verification_status` 判定：6 项检查全部通过且没有证据缺口时为 `pass`；"
        "只要检出冲突证据或缺口就降级为 `warn`，提示结论需要保守解释。"
    )
    lines.append("")

    required_rows = [
        row
        for row in rows
        if (row.get("coverage") or {}).get("available") and (row.get("coverage") or {}).get("required")
    ]
    lines.append("## 三、分层结果：只统计「有覆盖要求」的题目")
    lines.append("")
    if required_rows:
        lines.append("| 臂 | 题数 | 覆盖率 | 缺口题数 | 平均冲突组 | 平均答案字数 | 平均 LLM 调用 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for arm in arms:
            items = [row for row in required_rows if row["arm"] == arm]
            if not items:
                continue
            covered = sum(1 for row in items if (row.get("coverage") or {}).get("rate", 0) >= 1.0)
            lines.append(
                "| `{arm}` | {n} | {cov} | {missing} | {conflicts} | {chars} | {llm} |".format(
                    arm=arm,
                    n=len(items),
                    cov=_fmt(covered / len(items)),
                    missing=len(items) - covered,
                    conflicts=_fmt(sum(row.get("conflict_group_count", 0) for row in items) / len(items)),
                    chars=_fmt(sum(row["answer_chars"] for row in items) / len(items), 0),
                    llm=_fmt(sum(row["llm_calls_total"] for row in items) / len(items), 1),
                )
            )
        lines.append("")
    else:
        lines.append("本轮没有题目带非空覆盖要求。")
        lines.append("")

    lines.append("## 四、逐题结果")
    lines.append("")
    for qid in dict.fromkeys(row["qid"] for row in rows):
        subset = [row for row in rows if row["qid"] == qid]
        if not subset:
            continue
        lines.append(f"### `{qid}` — {subset[0]['question']}")
        lines.append("")
        lines.append("| 臂 | 答案类型 | 覆盖率 | 缺失项 | 冲突组 | 校验 | 卡/引用 | 轮数 | 延迟 (s) | LLM |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in subset:
            coverage = row.get("coverage") or {}
            missing = coverage.get("missing") or []
            lines.append(
                "| `{arm}` | {atype} | {cov} | {missing} | {conflicts} | {verify} | {cards}/{cites} | {rounds} | {lat} | {llm} |".format(
                    arm=row["arm"],
                    atype=row.get("answer_type") or "-",
                    cov=_fmt(coverage.get("rate")) if coverage.get("available") else "n/a",
                    missing=", ".join(missing) if missing else "-",
                    conflicts=row.get("conflict_group_count", 0),
                    verify=row.get("verify_status") or "-",
                    cards=row.get("cards", 0),
                    cites=row.get("citations", 0),
                    rounds=row.get("rounds", 0),
                    lat=_fmt(row.get("latency_s"), 1),
                    llm=row.get("llm_calls_total", 0),
                )
            )
        lines.append("")

    lines.append("## 五、补检是否被触发")
    lines.append("")
    multi = [row for row in rows if row["arm"] in {"multi_1", "multi_3"}]
    triggered = [row for row in multi if row.get("rounds", 0) > 1]
    if triggered:
        lines.append("| 臂 | 题目 | 轮数 | 参与的 agent | 覆盖率 | 冲突组 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in triggered:
            agents = ", ".join(sorted(set(row.get("assignments") or []))) or "-"
            lines.append(
                "| `{arm}` | `{qid}` | {rounds} | {agents} | {cov} | {conflicts} |".format(
                    arm=row["arm"],
                    qid=row["qid"],
                    rounds=row["rounds"],
                    agents=agents,
                    cov=_fmt((row.get("coverage") or {}).get("rate")),
                    conflicts=row.get("conflict_group_count", 0),
                )
            )
        lines.append("")
    else:
        lines.append("本轮没有任何题目触发补检。")
        lines.append("")

    lines.append(PLACEHOLDER)
    lines.append("")

    lines.append("## 十、复现方式")
    lines.append("")
    lines.append("```powershell")
    lines.append("# 需要 PostgreSQL（paradedb/paradedb:0.24.0-pg17 或自带 pgvector 的实例）与 .env 里的 LLM Key")
    lines.append("$env:QA_DISABLE_POSTGRES='false'; $env:KG_DATA_DIR='data/verified'")
    lines.append("python scripts/experiments/ab_agents.py --out docs/experiments/ab_agents.json")
    lines.append(
        "python scripts/experiments/make_report.py --in docs/experiments/ab_agents.json "
        "--out docs/experiments/single-vs-multi-agent.md"
    )
    lines.append("```")
    lines.append("")
    if errors:
        lines.append("## 附：失败的任务")
        lines.append("")
        for row in errors:
            lines.append(f"- `{row['arm']}` / `{row['qid']}`: {row['error']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="source", default="docs/experiments/ab_agents.json")
    parser.add_argument("--out", dest="target", default="docs/experiments/single-vs-multi-agent.md")
    args = parser.parse_args()

    payload = json.loads(Path(args.source).read_text(encoding="utf-8"))
    text = build(payload)
    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"written: {target} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
