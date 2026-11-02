import { useState } from "react";

export default function Alerts({ alerts, categories, onSetBudget }) {
  const [cat, setCat] = useState("");
  const [limit, setLimit] = useState("");
  return (
    <div className="card">
      <h3>Budget alerts</h3>
      <div className="row">
        <select value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">Category…</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <input type="number" placeholder="Monthly limit ₹" value={limit} onChange={(e) => setLimit(e.target.value)} />
        <button className="btn" disabled={!cat || !limit}
          onClick={() => { onSetBudget(cat, Number(limit)); setLimit(""); }}>Set budget</button>
      </div>
      {alerts.length === 0 && <div className="muted">No budgets set yet.</div>}
      {alerts.map((a) => (
        <div key={a.category} className={`alert ${a.status}`}>
          <b>{a.category}</b>: spent ₹{Math.round(a.spent)} of ₹{Math.round(a.limit)} ({a.month}) ·
          projected ₹{Math.round(a.projected)} —{" "}
          {a.status === "over" ? "over budget!" : a.status === "warning" ? "on track to exceed" : "on track"}
        </div>
      ))}
    </div>
  );
}
