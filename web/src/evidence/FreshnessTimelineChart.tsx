// Extracted from App.tsx during the P7b module split.
import type { FreshnessTimelineChart } from "../types";
import { ChartEmpty } from "../components/ChartEmpty";
import { freshnessLabel } from "../lib/format";

export function FreshnessTimelineChartView(props: { chart?: FreshnessTimelineChart }) {
  const items = props.chart?.items ?? [];
  if (!items.length) return <ChartEmpty title={props.chart?.title ?? "Source freshness timeline"} message={props.chart?.empty_message} />;
  const max = Math.max(...items.map((item) => Number(item.count)), 1);
  return (
    <article className="report-chart-card">
      <div className="report-chart-head">
        <strong>{props.chart?.title ?? "Source freshness timeline"}</strong>
        <span>Source age</span>
      </div>
      <div className="freshness-timeline-chart">
        {items.map((item) => (
          <div className={`freshness-year ${item.freshness || "unknown"}`} key={item.year}>
            <span>{item.year}</span>
            <div>
              <i style={{ height: `${Math.max((Number(item.count) / max) * 100, 12)}%` }} />
            </div>
            <b>{item.count}</b>
            <em>{freshnessLabel(item.freshness)}</em>
          </div>
        ))}
      </div>
    </article>
  );
}
