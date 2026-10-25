// Extracted from App.tsx during the P7b module split.

export function DataTable(props: { rows: Record<string, unknown>[]; empty: string }) {
  if (!props.rows.length) return <div className="empty-table">{props.empty}</div>;
  const columns = Object.keys(props.rows[0]).slice(0, 7);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.slice(0, 24).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{String(row[column] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
