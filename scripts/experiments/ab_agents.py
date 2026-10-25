"""A/B harness: single-pass pipeline vs centralized multi-agent, with/without supplement.

Arms
  single   QA_ENABLE_AGENT=false            -> one sequential retrieval pass, no supervisor
  multi_1  multi-agent, max_retrieval_rounds=1 -> supervisor + parallel wave, no supplement
  multi_3  multi-agent, max_retrieval_rounds=3 -> supervisor + parallel wave + reflective re-retrieval

Every arm is scored by the SAME post-hoc judge: EvidenceCoverageChecker over the
returned graph_records / rag_hits / research_hits, so the comparison cannot favour
the arm that happens to expose an internal coverage report.

Usage:
  python .tmp/experiments/ab_agents.py --limit 4 --out .tmp/experiments/smoke.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

QUESTIONS = [
    ("profile_liquid", "紫光股份的液冷业务有哪些优势？"),
    ("profile_products", "紫光股份的服务器产品线主要覆盖哪些场景？"),
    ("risk_main", "紫光股份当前面临的主要风险是什么？"),
    ("risk_liquid", "液冷业务的落地风险有哪些？"),
    ("theme_invest", "液冷产业链的投资逻辑和主要风险是什么？"),
    ("theme_evolve", "液冷散热技术从风冷到液冷的演进路径是什么？"),
    ("bottleneck_liquid", "液冷技术规模商用的瓶颈在哪里？"),
    ("bottleneck_compute", "算力基础设施目前的供给约束是什么？"),
    ("topic_chain", "液冷产业链有哪些关键环节，哪些公司参与？"),
    ("metric_ict", "紫光股份 ICT 基础设施业务的收入结构和毛利率如何？"),
]


def patch_round_budget(rounds: int) -> None:
    import aika.agent_runner as runner

    base = runner.TaskPlanner

    class PatchedPlanner(base):  # type: ignore[misc, valid-type]
        def plan(self, question, plan):
            task_plan = super().plan(question, plan)
            return replace(task_plan, budgets=replace(task_plan.budgets, max_retrieval_rounds=rounds))

    runner.TaskPlanner = PatchedPlanner


def build_engine(arm: str):
    os.environ["QA_ENABLE_AGENT"] = "false" if arm == "single" else "true"
    os.environ.setdefault("QA_DISABLE_POSTGRES", "false")
    os.environ.setdefault("KG_DATA_DIR", "data/verified")

    if arm == "single":
        patch_round_budget(1)
    elif arm == "multi_1":
        patch_round_budget(1)
    else:
        patch_round_budget(3)

    from aika.qa_engine import QAEngine

    return QAEngine.from_env()


def _plan_from_payload(payload):
    """Rebuild the QuestionPlan the arm actually used (result["plan"] is a plain dict)."""
    from dataclasses import fields

    from aika.question_planner import QuestionPlan

    if not isinstance(payload, dict):
        return payload
    allowed = {item.name for item in fields(QuestionPlan)}
    return QuestionPlan(**{key: value for key, value in payload.items() if key in allowed})


def judge_coverage(result: dict) -> dict:
    """Score evidence coverage the same way for every arm."""
    from aika.agents.coverage import EvidenceCoverageChecker
    from aika.agents.planner import TaskPlanner
    from aika.agent_runner import AgentRetrievalState

    raw_plan = result.get("plan")
    if not raw_plan:
        return {"available": False}
    plan = _plan_from_payload(raw_plan)

    task_plan = TaskPlanner(max_steps=4).plan(str(result.get("contextual_question") or ""), plan)
    state = AgentRetrievalState(
        graph_records=list(result.get("graph_records") or []),
        rag_hits=list(result.get("rag_hits") or []),
        research_hits=list(result.get("research_hits") or []),
        semantic_hits=list(result.get("semantic_hits") or []),
    )
    report = EvidenceCoverageChecker().check(plan, task_plan, state, retrieval_round=0)
    required = list(report.required)
    return {
        "available": True,
        "required": required,
        "satisfied": list(report.satisfied),
        "missing": list(report.missing),
        "rate": (len(report.satisfied) / len(required)) if required else 1.0,
    }


def _failed_checks(verification: dict) -> list[str]:
    """Verification checks may be dicts or plain strings depending on the arm."""
    failed: list[str] = []
    for item in verification.get("checks") or []:
        if isinstance(item, dict):
            if str(item.get("status") or "").lower() not in {"pass", "ok", "skipped"}:
                failed.append(str(item.get("name") or item.get("check") or "?"))
        else:
            text = str(item)
            if "fail" in text.lower() or "warn" in text.lower():
                failed.append(text)
    return failed


def _as_dict(card) -> dict:
    if isinstance(card, dict):
        return card
    to_dict = getattr(card, "to_dict", None)
    if callable(to_dict):
        try:
            return dict(to_dict())
        except TypeError:
            pass
    return dict(getattr(card, "__dict__", {}) or {})


def evidence_profile(result: dict) -> dict:
    """How wide the retrieved evidence is: claim types, source documents, topics."""
    cards = [_as_dict(card) for card in (result.get("evidence_cards") or [])]
    claim_types = sorted({str(card.get("claim_type") or "") for card in cards} - {""})
    sources = sorted(
        {
            (str(card.get("source_title") or ""), str(card.get("page") or ""))
            for card in cards
            if card.get("source_title")
        }
    )
    topics = sorted({str(card.get("topic") or "") for card in cards} - {""})
    companies = sorted(
        {str(name) for card in cards for name in (card.get("companies") or []) if name}
    )
    return {
        "claim_types": claim_types,
        "claim_type_count": len(claim_types),
        "source_count": len(sources),
        "topic_count": len(topics),
        "company_count": len(companies),
    }


def extract(arm: str, qid: str, question: str, result: dict, elapsed: float) -> dict:
    diagnostics = result.get("diagnostics") or {}
    answer = str(result.get("answer") or "")
    citations = sorted(set(re.findall(r"\[(E\d+)\]", answer)))
    multi = diagnostics.get("multi_agent") or {}
    rounds = multi.get("rounds") or []
    assignments = [a.get("agent_type") for r in rounds for a in (r.get("assignments") or [])]
    review = (multi.get("review") or {}).get("coverage") or {}
    llm_calls = diagnostics.get("llm_calls") or {}
    verification = result.get("verification") or {}

    return {
        "arm": arm,
        "qid": qid,
        "question": question,
        "answer_type": result.get("answer_type"),
        "latency_s": round(elapsed, 2),
        "llm_calls_total": int(llm_calls.get("total") or 0),
        "cards": len(result.get("evidence_cards") or []),
        "citations": len(citations),
        "answer_chars": len(answer),
        "graph_records": len(result.get("graph_records") or []),
        "rag_hits": len(result.get("rag_hits") or []),
        "research_hits": len(result.get("research_hits") or []),
        "verify_status": verification.get("status") or "",
        "verify_failed": _failed_checks(verification),
        "verify_gap_count": len(verification.get("evidence_gaps") or []),
        "conflict_group_count": len(verification.get("conflict_groups") or []),
        "raw_evidence_count": int((verification.get("checks") or {}).get("raw_evidence_count") or 0),
        "unsupported_terms": list(verification.get("unsupported_terms") or []),
        "evidence": evidence_profile(result),
        "claim_ids": [
            str(_as_dict(card).get("claim_id") or "")
            for card in (result.get("evidence_cards") or [])
        ],
        "research_ids": [
            str((hit or {}).get("claim_id") or "")
            for hit in (result.get("research_hits") or [])
            if isinstance(hit, dict)
        ],
        "coverage": judge_coverage(result),
        "rounds": len(rounds),
        "assignments": assignments,
        "agent_round_coverage": {
            "missing": review.get("missing") or [],
            "stop_reason": review.get("stop_reason") or "",
        },
        "errors": list(result.get("errors") or []),
    }


def aggregate(rows: list[dict]) -> list[dict]:
    out = []
    for arm in sorted({row["arm"] for row in rows}):
        items = [row for row in rows if row["arm"] == arm]
        latencies = sorted(row["latency_s"] for row in items)
        rates = [row["coverage"].get("rate", 0.0) for row in items if row["coverage"].get("available")]
        out.append(
            {
                "arm": arm,
                "n": len(items),
                "coverage_rate": round(statistics.mean(rates), 3) if rates else 0.0,
                "verify_pass_rate": round(
                    sum(1 for row in items if row["verify_status"] == "pass") / len(items), 3
                ),
                "verify_warn_rate": round(
                    sum(1 for row in items if row["verify_status"] == "warn") / len(items), 3
                ),
                "mean_cards": round(statistics.mean(row["cards"] for row in items), 2),
                "mean_citations": round(statistics.mean(row["citations"] for row in items), 2),
                "mean_answer_chars": round(statistics.mean(row["answer_chars"] for row in items), 0),
                "p50_latency_s": latencies[len(latencies) // 2],
                "mean_latency_s": round(statistics.mean(latencies), 2),
                "mean_llm_calls": round(statistics.mean(row["llm_calls_total"] for row in items), 2),
                "mean_agents": round(statistics.mean(len(set(row["assignments"])) for row in items), 2),
                "mean_rounds": round(statistics.mean(row["rounds"] or 0 for row in items), 2),
                "mean_claim_types": round(
                    statistics.mean(row.get("evidence", {}).get("claim_type_count", 0) for row in items), 2
                ),
                "mean_sources": round(
                    statistics.mean(row.get("evidence", {}).get("source_count", 0) for row in items), 2
                ),
                "mean_conflict_groups": round(
                    statistics.mean(row.get("conflict_group_count", 0) for row in items), 2
                ),
                "conflict_questions": sum(1 for row in items if row.get("conflict_group_count", 0) > 0),
                "mean_raw_evidence": round(
                    statistics.mean(row.get("raw_evidence_count", 0) for row in items), 1
                ),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", default="single,multi_1,multi_3")
    parser.add_argument("--limit", type=int, default=0, help="only the first N questions")
    parser.add_argument("--qids", default="", help="comma separated question ids")
    parser.add_argument("--out", default=".tmp/experiments/ab_agents.json")
    args = parser.parse_args()

    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    questions = QUESTIONS[: args.limit] if args.limit else QUESTIONS
    if args.qids:
        wanted = {item.strip() for item in args.qids.split(",") if item.strip()}
        questions = [item for item in QUESTIONS if item[0] in wanted]
    rows: list[dict] = []

    for arm in arms:
        engine = build_engine(arm)
        status = engine.status
        if callable(status):
            status = status()
        print(
            f"[arm {arm}] graph={status.graph_backend} rag={status.rag_enabled} "
            f"research={status.research_enabled} semantic={status.embedding_enabled} llm={status.llm_enabled}",
            flush=True,
        )
        try:
            for qid, question in questions:
                started = time.perf_counter()
                try:
                    result = engine.answer_question(question)
                    elapsed = time.perf_counter() - started
                    row = extract(arm, qid, question, result, elapsed)
                except Exception as exc:  # noqa: BLE001 - the harness must survive one bad question
                    row = {
                        "arm": arm,
                        "qid": qid,
                        "question": question,
                        "error": f"{type(exc).__name__}: {exc}",
                        "latency_s": round(time.perf_counter() - started, 2),
                    }
                rows.append(row)
                if "error" in row:
                    print(f"  {arm:8s} {qid:18s} ERROR {row['error']}", flush=True)
                else:
                    print(
                        f"  {arm:8s} {qid:18s} {row.get('answer_type') or '-':20s} "
                        f"cov={row.get('coverage', {}).get('rate', 0):.2f} "
                        f"verify={row.get('verify_status') or '-':5s} cards={row.get('cards', 0)} "
                        f"t={row.get('latency_s')}s llm={row.get('llm_calls_total', 0)} "
                        f"rounds={row.get('rounds', 0)}",
                        flush=True,
                    )
        finally:
            engine.close()

    summary = aggregate(rows)
    payload = {"config": {"arms": arms, "questions": len(questions)}, "summary": summary, "rows": rows}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== summary ===")
    header = (
        f"{'arm':10s}{'n':>3s}{'cov':>7s}{'pass':>7s}{'warn':>7s}{'cards':>7s}{'cites':>7s}"
        f"{'chars':>8s}{'p50s':>8s}{'llm':>6s}{'agents':>7s}{'rounds':>7s}"
    )
    print(header)
    for item in summary:
        print(
            f"{item['arm']:10s}{item['n']:3d}{item['coverage_rate']:7.2f}{item['verify_pass_rate']:7.2f}"
            f"{item['verify_warn_rate']:7.2f}"
            f"{item['mean_cards']:7.1f}{item['mean_citations']:7.1f}{item['mean_answer_chars']:8.0f}"
            f"{item['p50_latency_s']:8.1f}{item['mean_llm_calls']:6.1f}{item['mean_agents']:7.1f}"
            f"{item['mean_rounds']:7.1f}"
        )
    print(f"\nsaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
