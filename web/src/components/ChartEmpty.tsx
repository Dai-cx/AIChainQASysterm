// Extracted from App.tsx during the P7b module split.

export function ChartEmpty(props: { title: string; message?: string }) {
  return (
    <article className="report-chart-card empty">
      <div className="report-chart-head">
        <strong>{props.title}</strong>
        <span>No chart data</span>
      </div>
      <div className="empty-table">{props.message || "当前证据不足"}</div>
    </article>
  );
}
