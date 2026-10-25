# Legacy archive

Files under this directory are kept for history only. Nothing here is shipped in the
wheel, imported by the package, or run by CI.

## Design notes and plans

| File | What it is |
|---|---|
| `direction.md` | The earlier strategy note that moved the project from a public web SaaS towards a local MCP server + skill. Its conclusions are now the shipped mainline, so the note is history. |
| `plan-v0.0.0-v0.0.1plan.md` | The original v0.0.0 → v0.0.1 build plan. |
| `plan-p0-p6-report-ia.md` | The report information-architecture plan (P0–P6: report spec, charts, evidence folding). P2/P3 shipped; P0/P4/P5 did not. |
| `log.md` | Short development log from the original author. |

## Audits from the refactor

These were written at the start of the refactor, against the pre-refactor code, and
describe problems that have mostly been fixed since. They are the evidence trail for
`REFACTOR_PLAN.md`, not a description of the current code.

| File | Scope |
|---|---|
| `audit-data-layer.md` | Storage backends, data paths, curated/verified artefacts, layered-import violations. |
| `audit-qa-report-layer.md` | `qa_engine.py`, the report layer, claims review, eval wiring, duplicate implementations. |
| `audit-agent-layer.md` | Agent runners, tool registries, task types, budgets. |

## One-off scripts

`scripts/` holds the operators that were used once and are no longer referenced by code
or CI (`benchmark_qa_speed.py`, `validate_postgres_cutover.py`, `auto_judge_review.py`,
`apply_judgments.py`).
