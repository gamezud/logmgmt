// Top IP/User/Event Type are shown as plain tables, not bar charts —
// Recharts is reserved for the timeline, where a chart adds real value
// (trend over time). For a 10-row ranked list, a table is the more direct,
// unambiguous way to read "value -> count". See docs/DECISIONS.md.
export default function TopNTable({ title, items }) {
  return (
    <div className="top-n-table">
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="empty-state">No data for this range.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Value</th>
              <th>Count</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={item.value}>
                <td>{index + 1}</td>
                <td>{item.value}</td>
                <td>{item.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
