// Extracted from App.tsx during the P7b module split.
import type { FlowMapChart } from "../types";
import { ChartEmpty } from "../components/ChartEmpty";
import { flowNodes, shortSvgLabel } from "../lib/format";

export function FlowMapChartView(props: { chart?: FlowMapChart }) {
  const chart = props.chart;
  const links = (chart?.links ?? []).slice(0, 8);
  if (!links.length) return <ChartEmpty title={chart?.title ?? "Evidence-weighted supply chain map"} message={chart?.empty_message} />;
  const max = Math.max(...links.map((link) => Number(link.value)), 1);
  const nodes = flowNodes(links);
  return (
    <article className="report-chart-card wide">
      <div className="report-chart-head">
        <strong>{chart?.title ?? "Evidence-weighted supply chain map"}</strong>
        <span>Evidence weighted</span>
      </div>
      <div className="flow-map-chart">
        <svg viewBox="0 0 760 260" role="img" aria-label={chart?.title ?? "Evidence-weighted supply chain map"}>
          {links.map((link, index) => {
            const source = nodes.get(link.source) ?? { x: 40, y: 40 };
            const target = nodes.get(link.target) ?? { x: 720, y: 220 };
            const width = 2 + (Number(link.value) / max) * 8;
            return (
              <path
                d={`M ${source.x + 112} ${source.y} C ${source.x + 230} ${source.y}, ${target.x - 150} ${target.y}, ${target.x - 14} ${target.y}`}
                key={`${link.source}-${link.target}-${index}`}
                strokeWidth={width}
              />
            );
          })}
          {Array.from(nodes.entries()).map(([id, point]) => (
            <g className="flow-node" key={id}>
              <rect x={point.x} y={point.y - 18} width="132" height="36" rx="8" />
              <text x={point.x + 10} y={point.y + 4}>{shortSvgLabel(id)}</text>
            </g>
          ))}
        </svg>
        <div className="flow-link-list">
          {links.slice(0, 5).map((link) => (
            <span key={`${link.source}-${link.target}`}>
              {`${link.source} -> ${link.target} · ${link.value}`}
            </span>
          ))}
        </div>
        <p>{chart?.caption ?? "线条粗细代表 AIKA 本地证据数量/强度，不代表市场规模或收入占比。"}</p>
      </div>
    </article>
  );
}
