// Extracted from App.tsx during the P7b module split.
import type { CompanyCoverageHeatmapChart } from "../types";
import { ChartEmpty } from "../components/ChartEmpty";
import { clampNumber } from "../lib/format";

export function CompanyHeatmapChart(props: { chart?: CompanyCoverageHeatmapChart }) {
  const chart = props.chart;
  const rows = chart?.rows ?? [];
  const columns = chart?.columns ?? [];
  const cells = chart?.cells ?? [];
  if (!rows.length || !columns.length || !cells.length) return <ChartEmpty title={chart?.title ?? "公司覆盖热力图"} message={chart?.empty_message} />;
  const cellMap = new Map(cells.map((cell) => [`${cell.company}\u0000${cell.segment}`, cell]));
  return (
    <article className="report-chart-card wide">
      <div className="report-chart-head">
        <strong>{chart?.title ?? "公司覆盖热力图"}</strong>
        <span>0 无证据 · 5 高覆盖</span>
      </div>
      <div className="heatmap-wrap">
        <table className="coverage-heatmap">
          <thead>
            <tr>
              <th>公司</th>
              {columns.map((column) => <th key={column}>{column}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row}>
                <th>{row}</th>
                {columns.map((column) => {
                  const cell = cellMap.get(`${row}\u0000${column}`);
                  const score = clampNumber(Number(cell?.score ?? 0), 0, 5);
                  return (
                    <td key={column}>
                      <span className={`heatmap-score score-${score}`} title={`${cell?.reason || "无证据"} ${cell?.evidence_ids?.join("、") || ""}`}>
                        {score}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}
