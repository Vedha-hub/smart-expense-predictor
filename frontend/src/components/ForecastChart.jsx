import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function ForecastChart({ forecast, horizon, setHorizon, category, setCategory, categories }) {
  // merge history + forecast into one array with two separate keys so they get two colours
  const rows = [
    ...forecast.history.map((p) => ({ date: p.date, actual: p.amount })),
    ...forecast.forecast.map((p) => ({ date: p.date, predicted: p.amount })),
  ];
  return (
    <div className="card">
      <div className="row">
        <h3>Spending forecast</h3>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
          {[7, 14, 30, 60].map((h) => <option key={h} value={h}>{h} days</option>)}
        </select>
      </div>
      <div className="muted">Model: {forecast.method}
        {forecast.metrics && ` · hold-out WAPE ${forecast.metrics["WAPE_%"]}%`}</div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend />
          <Line type="monotone" dataKey="actual" stroke="#2563eb" dot={false} />
          <Line type="monotone" dataKey="predicted" stroke="#f97316" strokeDasharray="5 4" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
