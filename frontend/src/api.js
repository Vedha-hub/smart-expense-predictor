// All backend calls live here (single place to change if the API changes).
async function req(path, options) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  seed: () => req("/seed", { method: "POST" }),
  upload: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return req("/upload", { method: "POST", body: fd });
  },
  reset: () => req("/transactions", { method: "DELETE" }),
  summary: () => req("/summary"),
  forecast: (horizon, category) =>
    req(`/forecast?horizon=${horizon}${category ? `&category=${encodeURIComponent(category)}` : ""}`),
  transactions: () => req("/transactions?limit=50"),
  correct: (id, category) => req(`/transactions/${id}`, json("PATCH", { category })),
  retrain: () => req("/retrain", { method: "POST" }),
  anomalies: () => req("/anomalies"),
  clusters: () => req("/clusters"),
  alerts: () => req("/alerts"),
  setBudget: (category, monthly_limit) => req("/budgets", json("POST", { category, monthly_limit })),
};
