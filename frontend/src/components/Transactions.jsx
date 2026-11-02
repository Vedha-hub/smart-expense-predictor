export default function Transactions({ rows, categories, onCorrect, onRetrain }) {
  return (
    <div className="card">
      <div className="row">
        <h3>Recent transactions</h3>
        <button className="btn" onClick={onRetrain}>Retrain classifier with my corrections</button>
      </div>
      <div className="scroll">
        <table>
          <thead><tr><th>Date</th><th>Description</th><th>Amount</th><th>Category (editable)</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={r.is_anomaly ? "anom" : ""}>
                <td>{r.date}</td>
                <td>{r.description}</td>
                <td>₹{Math.round(r.amount)}</td>
                <td>
                  <select value={r.category} onChange={(e) => onCorrect(r.id, e.target.value)}>
                    {[...new Set([...categories, r.category])].map((c) => <option key={c}>{c}</option>)}
                  </select>
                </td>
                <td>{r.is_anomaly ? "⚠️" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
