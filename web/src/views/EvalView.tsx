// Extracted from App.tsx during the P7b module split.
import { BarChart3, CircleSlash, ClipboardList, FileText, Loader2, Table2 } from "lucide-react";
import { useState } from "react";
import type { EvalCaseResult, EvalRun, EvalRunSummary } from "../types";
import { DataTable } from "../components/DataTable";
import { ResearchList } from "./ResearchOutputsView";
import { StatCard } from "../components/StatCard";
import { arrayRecords, formatMetricValue, formatPercent } from "../lib/format";
import { categoryLabel, metricLabel } from "../lib/labels";

export function EvalView(props: {
  runs: EvalRunSummary[];
  selectedRun: EvalRun | null;
  onSelectRun: (id: string) => void;
  onRefresh: () => Promise<EvalRunSummary[]>;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const run = props.selectedRun;

  async function refresh() {
    setRefreshing(true);
    try {
      await props.onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="page-panel eval-page">
      <div className="page-heading eval-heading">
        <div>
          <span className="eyebrow">Evaluation</span>
          <h2>评测报告</h2>
        </div>
        <button className="eval-refresh" type="button" onClick={refresh} disabled={refreshing}>
          {refreshing ? <Loader2 size={16} className="spin" /> : <BarChart3 size={16} />}
          <span>刷新</span>
        </button>
      </div>
      <div className="eval-layout">
        <aside className="eval-run-list">
          <div className="section-title">
            <ClipboardList size={16} />
            <span>历史 Run</span>
          </div>
          {props.runs.length === 0 && <div className="empty-table">暂无评测报告</div>}
          {props.runs.map((item) => (
            <button
              className={`eval-run-item ${run?.run_id === item.run_id ? "selected" : ""}`}
              type="button"
              key={item.run_id}
              onClick={() => props.onSelectRun(item.run_id)}
            >
              <strong>{item.run_id}</strong>
              <span>{item.dataset_name || "qa_benchmark"} · {item.cases} cases</span>
              <em>{formatPercent(item.overall_score)} · pass {formatPercent((item.passed || 0) / Math.max(item.cases || 1, 1))}</em>
            </button>
          ))}
        </aside>
        <div className="eval-report-panel">
          {!run ? (
            <div className="agent-empty">
              <ClipboardList size={34} />
              <span>暂无可展示的评测报告</span>
            </div>
          ) : (
            <>
              <div className="eval-report-header">
                <div>
                  <span className="task-status completed">{run.dataset.name}</span>
                  <h3>{run.run_id}</h3>
                  <p>{run.created_at} · dataset {run.dataset.hash} · git {String(run.environment.git_commit ?? "") || "unknown"}</p>
                </div>
              </div>
              <div className="agent-stat-grid">
                <StatCard label="总分" value={formatPercent(run.summary.overall_score)} />
                <StatCard label="通过率" value={formatPercent(run.summary.pass_rate)} />
                <StatCard label="用例" value={String(run.summary.cases)} />
                <StatCard label="失败" value={String(run.summary.failed)} />
                <StatCard label="警告" value={String(run.summary.warned)} />
                <StatCard label="K" value={String(run.environment.k ?? 6)} />
              </div>
              <section className="agent-section">
                <div className="research-section-title">
                  <BarChart3 size={16} />
                  <span>分维指标</span>
                </div>
                <div className="eval-metric-grid">
                  {Object.entries(run.summary.metrics).map(([key, value]) => (
                    <StatCard key={key} label={metricLabel(key)} value={formatMetricValue(key, value)} />
                  ))}
                </div>
              </section>
              <section className="agent-section">
                <div className="research-section-title">
                  <Table2 size={16} />
                  <span>分类得分</span>
                </div>
                <div className="eval-category-list">
                  {run.category_scores.map((row) => (
                    <article className="eval-category-row" key={row.category}>
                      <strong>{categoryLabel(row.category)}</strong>
                      <span>{row.cases} cases</span>
                      <b>{formatPercent(row.overall_score)}</b>
                      <em>pass {formatPercent(row.pass_rate)}</em>
                    </article>
                  ))}
                </div>
              </section>
              <section className="agent-section">
                <div className="research-section-title">
                  <CircleSlash size={16} />
                  <span>失败样例</span>
                </div>
                <FailedExamples rows={run.failed_examples} />
              </section>
              <section className="agent-section">
                <div className="research-section-title">
                  <FileText size={16} />
                  <span>Case 明细</span>
                </div>
                <EvalCaseTable rows={run.results} />
              </section>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

export function FailedExamples(props: { rows: EvalRun["failed_examples"] }) {
  if (!props.rows.length) return <div className="empty-table">当前 run 没有失败样例</div>;
  return (
    <div className="failed-example-list">
      {props.rows.map((row) => (
        <article className="failed-example" key={row.case_id}>
          <div>
            <strong>{row.case_id}</strong>
            <span>{categoryLabel(row.category)} · {formatPercent(row.score)}</span>
          </div>
          <p>{row.question}</p>
          <div className="failure-tags">
            {row.failures.map((failure) => (
              <span key={failure}>{failure}</span>
            ))}
          </div>
          <ResearchList rows={arrayRecords(row.evidence_gaps)} primaryKey="gap" secondaryKeys={["priority", "suggested_source"]} empty="未记录证据缺口" />
        </article>
      ))}
    </div>
  );
}

export function EvalCaseTable(props: { rows: EvalCaseResult[] }) {
  if (!props.rows.length) return <div className="empty-table">当前 run 没有 case 明细</div>;
  const rows = props.rows.slice(0, 50).map((row) => ({
    case_id: row.case_id,
    category: categoryLabel(row.category),
    status: row.status,
    score: formatPercent(row.score),
    question: row.question,
    answer_type: row.answer_type || "unknown",
    failures: row.failures.join(", ") || "-"
  }));
  return <DataTable rows={rows} empty="当前 run 没有 case 明细" />;
}
