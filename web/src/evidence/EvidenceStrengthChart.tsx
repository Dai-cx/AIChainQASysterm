// Extracted from App.tsx during the P7b module split.
import type { EvidenceStrengthBarChart } from "../types";
import { ChartEmpty } from "../components/ChartEmpty";

export function EvidenceStrengthChart(props: { chart?: EvidenceStrengthBarChart }) {
  const counts = props.chart?.counts ?? {};
  const entries = Object.entries(counts).filter(([, value]) => Number(value) > 0);
  if (!entries.length) return <ChartEmpty title={props.chart?.title ?? "证据强度柱状图"} message={props.chart?.empty_message} />;
  const max = Math.max(...entries.map(([, value]) => Number(value)), 1);
  const labels: Record<string, string> = {
    direct: "直接证据",
    indirect: "间接证据",
    mentioned: "仅提及",
    unsupported: "未支撑",
    no_evidence: "无证据"
  };
  return (
    <article className="report-chart-card">
      <div className="report-chart-head">
        <strong>{props.chart?.title ?? "证据强度柱状图"}</strong>
        <span>Evidence quality</span>
      </div>
      <div className="evidence-bar-chart">
        {entries.map(([key, value]) => (
          <div className="evidence-bar-row" key={key}>
            <span>{labels[key] ?? key}</span>
            <div>
              <i style={{ width: `${Math.max((Number(value) / max) * 100, 7)}%` }} />
            </div>
            <b>{value}</b>
          </div>
        ))}
      </div>
    </article>
  );
}
