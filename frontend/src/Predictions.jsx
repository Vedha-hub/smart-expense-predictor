import { useEffect, useState } from "react";
import { api, inr, ICONS, CAT_COLORS } from "./ui.jsx";

function Chart({ history, forecast }) {
  const W = 700, H = 250, P = 36;
  const all = [...history, ...forecast];
  const max = Math.max(...all.map((p) => p.amount), 1);
  const x = (i) => P + (i * (W - 2 * P)) / Math.max(all.length - 1, 1);
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const line = (arr, off) => arr.map((p, i) => `${i ? "L" : "M"}${x(i + off)},${y(p.amount)}`).join(" ");
  const last = history.length - 1;
  const histPath = line(history, 0);
  const fcPath = line([history[last], ...forecast], last);
  const areaPath = `${fcPath} L${x(last + forecast.length)},${H - P} L${x(last)},${H - P} Z`;
  const todayX = x(last);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }}>
      <defs>
        <linearGradient id="fcFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f97316" stopOpacity=".35" />
          <stop offset="100%" stopColor="#f97316" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x={todayX} y={P - 10} width={W - P - todayX} height={H - 2 * P + 10} fill="rgba(249,115,22,.07)" />
      <line x1={P} y1={H - P} x2={W - P} y2={H - P} stroke="var(--border)" />
      <line x1={P} y1={P - 10} x2={P} y2={H - P} stroke="var(--border)" />
      <text x={P - 6} y={P - 2} fontSize="12" textAnchor="end" fill="var(--muted)">{inr(max)}</text>
      <text x={P - 6} y={H - P} fontSize="12" textAnchor="end" fill="var(--muted)">0</text>
      <path d={areaPath} fill="url(#fcFill)" />
      <path d={histPath} fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinejoin="round" />
      <path d={fcPath} fill="none" stroke="#f97316" strokeWidth="2.5" strokeDasharray="7 5" strokeLinejoin="round" />
      <line x1={todayX} y1={P - 10} x2={todayX} y2={H - P} stroke="var(--muted)" strokeDasharray="3 3" />
      <text x={todayX} y={H - 12} fontSize="12" textAnchor="middle" fill="var(--muted)">last entry</text>
      <text x={P} y={H - 12} fontSize="12" fill="var(--muted)">{history[0].date}</text>
      <text x={W - P} y={H - 12} fontSize="12" textAnchor="end" fill="var(--muted)">{forecast[forecast.length - 1].date}</text>
    </svg>
  );
}

export default function Predictions({ token, categories }) {
  const [category, setCategory] = useState("");
  const [horizon, setHorizon] = useState(30);
  const [method, setMethod] = useState("auto");
  const [cmp, setCmp] = useState(null);
  const [cmpBusy, setCmpBusy] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    setLoading(true);
    setErr("");
    const q = `/my/predictions?horizon=${horizon}&method=${method}` + (category ? `&category=${encodeURIComponent(category)}` : "");
    api(q, { token })
      .then(setData)
      .catch(() => setErr("Could not load predictions. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [token, category, horizon, method, reload]);

  const compare = async () => {
    setCmpBusy(true);
    try { setCmp(await api("/my/model-comparison", { token })); } catch {}
    setCmpBusy(false);
  };

  const loadDemo = async () => {
    await api("/my/demo-data", { method: "POST", token });
    setReload((n) => n + 1);
  };

  if (err) return <div className="alert danger"><span>🚨</span><span>{err}</span></div>;
  if (loading && !data) return <div className="card">🧠 Training models on your data… this can take a few seconds.</div>;
  if (!data) return null;

  const f = data.forecast;
  return (
    <>
      <div className="top">
        <div>
          <h1>Predictions 🔮</h1>
          <div className="sub">Based on {data.transactions} expenses over {data.days_of_data} days</div>
        </div>
        <div className="row">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{ICONS[c]} {c}</option>)}
          </select>
          <select value={horizon} onChange={(e) => setHorizon(+e.target.value)}>
            {[7, 14, 30, 60].map((h) => <option key={h} value={h}>Next {h} days</option>)}
          </select>
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="auto">Model: Auto</option>
            <option value="prophet">Model: Prophet</option>
            <option value="lstm">Model: LSTM</option>
            <option value="baseline">Model: Baseline</option>
          </select>
          <button className="btn ghost" onClick={loadDemo}>Load demo data</button>
        </div>
      </div>

      <div style={{ opacity: loading ? 0.5 : 1, transition: "opacity .2s" }}>
        {f ? (
          <>
            <div className="card hero">
              <div style={{ flex: 1, minWidth: 220 }}>
                <div className="sub">Predicted spending, next {horizon} days ({f.category})</div>
                <div style={{ fontSize: 44, fontWeight: 800, letterSpacing: -1 }}>{inr(f.predicted_total)}</div>
              </div>
              <div className="hero-stats">
                <div><span className="sub">Daily average</span><b>{inr(f.predicted_total / horizon)}</b></div>
                <div><span className="sub">Model</span><b style={{ textTransform: "capitalize" }}>{f.method}</b></div>
                {f.metrics?.["weekly_WAPE_%"] != null && <div><span className="sub">Weekly error (WAPE)</span><b>{f.metrics["weekly_WAPE_%"]}%</b></div>}
              </div>
            </div>
            <div className="card" style={{ marginBottom: 16 }}>
              <h3>Spending forecast</h3>
              {f.requested !== "auto" && f.requested !== f.method && (
                <div className="alert warning"><span>⚠️</span><span>{f.requested.toUpperCase()} is not available on this server, so the {f.method} model was used instead.</span></div>
              )}
              <Chart history={f.history} forecast={f.forecast} />
              <div className="sub">
                Blue = actual spending, orange dashed = predicted. Error is measured on your last 4 weeks, so it appears once you have 90+ days of data.
              </div>
            </div>
          </>
        ) : (
          <div className="card" style={{ marginBottom: 16 }}>
            <h3>Spending forecast</h3>
            <div className="note">{data.forecast_message}</div>
          </div>
        )}

        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h3 style={{ margin: 0 }}>⚖️ Model comparison</h3>
              <div className="sub">Each model predicts your last 4 weeks, then we measure the error. Lower is better.</div>
            </div>
            <button className="btn" onClick={compare} disabled={cmpBusy}>{cmpBusy ? "Evaluating…" : "Compare models"}</button>
          </div>
          {cmp && !cmp.ready && <div className="note" style={{ marginTop: 12 }}>{cmp.message}</div>}
          {cmp && cmp.ready && (
            <table className="tbl" style={{ marginTop: 10 }}>
              <thead><tr><th>Model</th><th>Weekly error (WAPE)</th><th>Daily error (WAPE)</th><th>Avg daily miss (MAE)</th></tr></thead>
              <tbody>
                {cmp.results.map((r) => (
                  <tr key={r.method}>
                    <td style={{ textTransform: "capitalize" }}><b>{r.method}</b></td>
                    {r.available
                      ? <><td><b>{r.weekly_WAPE}%</b></td><td>{r.daily_WAPE}%</td><td>{inr(r.MAE)}</td></>
                      : <td colSpan={3} className="sub">Not installed on this server{r.method === "lstm" ? " (needs: python -m pip install tensorflow)" : r.method === "prophet" ? " (needs: python -m pip install prophet)" : ""}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="grid g2">
          <div className="card">
            <h3>🔍 Unusual expenses ({data.anomalies.length})</h3>
            {data.anomalies.length === 0 && <div className="note">{data.anomaly_message}</div>}
            {data.anomalies.map((a) => (
              <div key={a.id} className="legend-row">
                <span className="dot" style={{ background: CAT_COLORS[a.category] || "#94a3b8" }} />
                <span className="grow">{a.date} · {a.merchant || "-"} <span className="sub">({a.category})</span></span>
                <b style={{ color: "var(--bad)" }}>{inr(a.amount)}</b>
              </div>
            ))}
          </div>

          <div className="card">
            <h3>🧩 Spending groups &amp; tips</h3>
            {data.clusters?.clusters?.length ? (
              data.clusters.clusters.map((c) => (
                <div key={c.cluster} className="insight">
                  <b>Group {c.cluster + 1}</b> · {c.months.length} month{c.months.length === 1 ? "" : "s"} · top: {ICONS[c.top_category]} {c.top_category} ({c["top_share_%"]}%)
                  <div className="sub" style={{ marginTop: 4 }}>{c.tip}</div>
                </div>
              ))
            ) : (
              <div className="note">{data.cluster_message}</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
