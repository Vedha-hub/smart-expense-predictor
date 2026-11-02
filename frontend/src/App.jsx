import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import SummaryCards from "./components/SummaryCards";
import ForecastChart from "./components/ForecastChart";
import CategoryPie from "./components/CategoryPie";
import Alerts from "./components/Alerts";
import Transactions from "./components/Transactions";
import Insights from "./components/Insights";

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [horizon, setHorizon] = useState(30);
  const [category, setCategory] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [summary, forecast, transactions, anomalies, clusters, alerts] = await Promise.all([
        api.summary(), api.forecast(horizon, category), api.transactions(),
        api.anomalies(), api.clusters(), api.alerts(),
      ]);
      setData({ summary, forecast, transactions, anomalies, clusters, alerts });
    } catch (e) {
      setData(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [horizon, category]);

  useEffect(() => { load(); }, [load]);

  const run = async (fn) => {
    setLoading(true);
    try { await fn(); await load(); } catch (e) { setError(e.message); setLoading(false); }
  };

  return (
    <div className="container">
      <header>
        <h1>Smart Expense &amp; Spending Predictor</h1>
        <div className="actions">
          <label className="btn">
            Upload CSV
            <input type="file" accept=".csv" hidden
              onChange={(e) => e.target.files[0] && run(() => api.upload(e.target.files[0]))} />
          </label>
          <button className="btn" onClick={() => run(api.seed)}>Load sample data</button>
          <button className="btn ghost" onClick={() => run(api.reset)}>Reset</button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}
      {loading && <div className="muted">Loading…</div>}

      {data && (
        <>
          <SummaryCards summary={data.summary} predicted={data.forecast.predicted_total} horizon={horizon} />
          <Alerts alerts={data.alerts} onSetBudget={(c, v) => run(() => api.setBudget(c, v))}
            categories={data.summary.by_category.map((c) => c.category)} />
          <div className="grid2">
            <ForecastChart forecast={data.forecast} horizon={horizon} setHorizon={setHorizon}
              category={category} setCategory={setCategory}
              categories={data.summary.by_category.map((c) => c.category)} />
            <CategoryPie data={data.summary.by_category} />
          </div>
          <Insights clusters={data.clusters} anomalies={data.anomalies} />
          <Transactions rows={data.transactions}
            categories={data.summary.by_category.map((c) => c.category)}
            onCorrect={(id, cat) => run(() => api.correct(id, cat))}
            onRetrain={() => run(api.retrain)} />
        </>
      )}
    </div>
  );
}
