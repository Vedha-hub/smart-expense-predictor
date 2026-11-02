export default function Insights({ clusters, anomalies }) {
  return (
    <div className="grid2">
      <div className="card">
        <h3>Spending clusters &amp; tips</h3>
        {clusters.clusters.map((c) => (
          <div key={c.cluster} className="insight">
            <b>Group {c.cluster + 1}</b> ({c.months.length} months) — top: {c.top_category} ({c["top_share_%"]}%)
            <div className="muted">{c.tip}</div>
          </div>
        ))}
      </div>
      <div className="card">
        <h3>Anomalies ({anomalies.length})</h3>
        <div className="scroll">
          {anomalies.slice(0, 10).map((a) => (
            <div key={a.id} className="insight">
              {a.date} · {a.description} · <b>₹{Math.round(a.amount)}</b>
              <span className="muted"> ({a.category})</span>
            </div>
          ))}
          {anomalies.length === 0 && <div className="muted">No unusual transactions found.</div>}
        </div>
      </div>
    </div>
  );
}
