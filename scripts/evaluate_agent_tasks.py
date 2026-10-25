#!/usr/bin/env python3
"""Run a small multi-task ResearchAgent evaluation set."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from aika.agents.research_agent import ResearchAgent
from aika.agents.store import AgentTaskStore
from aika.eval.agent_tasks import AGENT_EVAL_CASES, score_task
from aika.qa_engine import QAEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate AIQASYS multi-task ResearchAgent tasks.")
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    parser.add_argument("--use-llm", action="store_true", help="Use configured LLM instead of deterministic fallback answers.")
    parser.add_argument("--use-embedding", action="store_true", help="Use configured embedding index during eval.")
    parser.add_argument("--task-dir", default="data/agent_tasks", help="Directory for JSONL task snapshots.")
    parser.add_argument("--limit", type=int, default=0, help="Limit cases for a quick smoke run.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    os.environ.setdefault("QA_GRAPH_BACKEND", "csv")
    engine = QAEngine.from_env()
    if not args.use_llm:
        engine.llm_client = None
        engine.status.llm_enabled = False
    if not args.use_embedding:
        engine.semantic_index = None
        engine.status.embedding_enabled = False
    store = AgentTaskStore(Path(args.task_dir))
    agent = ResearchAgent(engine, store)
    results = []
    try:
        cases = AGENT_EVAL_CASES[: args.limit] if args.limit and args.limit > 0 else AGENT_EVAL_CASES
        for task_type, goal in cases:
            task = agent.run(task_type=task_type, goal=goal)
            score, failures = score_task(task)
            results.append(
                {
                    "task_type": task_type,
                    "goal": goal,
                    "task_id": task.get("task_id", ""),
                    "status": task.get("status", ""),
                    "score": score,
                    "failures": failures,
                    "evidence_cards": len(task.get("evidence_cards", [])),
                    "evidence_gaps": task.get("final_outputs", {}).get("evidence_gap_count", 0),
                    "report_title": task.get("final_outputs", {}).get("report_title", ""),
                }
            )
    finally:
        engine.close()

    total = sum(item["score"] for item in results)
    max_score = 2 * len(results)
    accuracy = total / max_score if max_score else 0
    summary = {"cases": len(results), "score": total, "max_score": max_score, "accuracy": round(accuracy, 4)}
    if args.json:
        print(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2))
    else:
        print(f"Agent task evaluation: {total}/{max_score} accuracy={accuracy:.1%}")
        for item in results:
            status = "PASS" if item["score"] == 2 else "PARTIAL" if item["score"] == 1 else "FAIL"
            print(f"[{status}] {item['task_type']} | {item['goal']} | failures={','.join(item['failures']) or '-'}")
    return 0 if total >= max_score * 0.6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
