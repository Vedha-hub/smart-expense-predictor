/* Shared helpers + small chart components (no extra libraries needed). */

export async function api(path, { method = "GET", body, token } = {}) {
  const res = await fetch("/api" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = "Something went wrong";
    try {
      const d = (await res.json()).detail;
      msg = Array.isArray(d) ? d.map((x) => x.msg).join(", ") : d || msg;
    } catch {}
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const inr = (n) => (n < 0 ? "-₹" : "₹") + Math.abs(Math.round(n || 0)).toLocaleString("en-IN");
export const today = () => new Date().toISOString().slice(0, 10);
export const thisMonth = () => new Date().toISOString().slice(0, 7);
export const monthLabel = (m) =>
  new Date(m + "-01T00:00:00").toLocaleDateString("en-IN", { month: "long", year: "numeric" });

export const CAT_COLORS = {
  Groceries: "#22c55e", Rent: "#6366f1", "Food & Dining": "#f97316", Shopping: "#a855f7",
  Transport: "#ef4444", Utilities: "#06b6d4", Entertainment: "#eab308", Education: "#64748b",
  Health: "#ec4899", Other: "#94a3b8",
};
export const ICONS = {
  Groceries: "🛒", Rent: "🏠", "Food & Dining": "🍔", Shopping: "🛍️", Transport: "🚕",
  Utilities: "💡", Entertainment: "🎬", Education: "🎓", Health: "💊", Other: "📦",
};
export const STATUS_COLORS = {
  ok: "var(--good)", at_risk: "var(--accent)", warning: "var(--warn)", over: "var(--bad)", none: "var(--muted)",
};

export function Chip({ cat }) {
  return (
    <span className="chip">
      <i style={{ background: CAT_COLORS[cat] || "#94a3b8" }} />
      {ICONS[cat] || "📦"} {cat}
    </span>
  );
}

/* circular progress ring */
export function Ring({ pct = 0, size = 96, stroke = 10, color = "var(--accent)", track = "var(--surface2)", children }) {
  const r = (size - stroke) / 2;
  const C = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(pct, 100));
  return (
    <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={`${(C * p) / 100} ${C}`}
          style={{ transition: "stroke-dasharray .9s ease" }}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
        {children}
      </div>
    </div>
  );
}

/* donut chart: data = [{label, value, color}] */
export function Donut({ data, size = 210, stroke = 30, center }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  const r = (size - stroke) / 2;
  const C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface2)" strokeWidth={stroke} />
        {total > 0 &&
          data.map((d) => {
            const len = (C * d.value) / total;
            const seg = Math.max(len - 3, 0);
            const el = (
              <circle
                key={d.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={d.color} strokeWidth={stroke}
                strokeDasharray={`${seg} ${C - seg}`} strokeDashoffset={-acc}
              >
                <title>{`${d.label}: ${inr(d.value)}`}</title>
              </circle>
            );
            acc += len;
            return el;
          })}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
        {center}
      </div>
    </div>
  );
}
