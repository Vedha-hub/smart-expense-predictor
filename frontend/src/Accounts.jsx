import { useCallback, useEffect, useState } from "react";
import "./theme.css";
import Predictions from "./Predictions.jsx";
import {
  api, inr, today, thisMonth, monthLabel, CAT_COLORS, ICONS, STATUS_COLORS, Ring, Donut, Chip,
} from "./ui.jsx";

/* ================= helpers ================= */
const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

/* Financial health score (0-100): 40 pts savings rate, 40 pts budget discipline, 20 pts trend vs last month */
function healthScore(r) {
  const clamp = (x) => Math.max(0, Math.min(x, 1));
  const savings = r.income > 0 ? clamp(r.saved / r.income / 0.2) * 40 : 20;
  const budgeted = r.categories.filter((c) => c.limit);
  const w = { over: 0, warning: 0.5, at_risk: 0.75, ok: 1 };
  const budget = budgeted.length ? (budgeted.reduce((s, c) => s + (w[c.status] ?? 1), 0) / budgeted.length) * 40 : 20;
  const trend = r.prev_total > 0 ? clamp(1 - Math.max(r.change_vs_prev, 0) / r.prev_total) * 20 : 15;
  return Math.round(savings + budget + trend);
}

function verdict(score) {
  if (score == null) return { emoji: "🌱", label: "Getting started", text: "Add a few expenses and set budgets to unlock your score." };
  if (score >= 80) return { emoji: "🏆", label: "Excellent", text: "You are on top of your money. Keep it up!" };
  if (score >= 60) return { emoji: "👍", label: "Good", text: "Solid month. A few categories need watching." };
  if (score >= 40) return { emoji: "⚠️", label: "Needs attention", text: "Spending is drifting off plan. Check the alerts below." };
  return { emoji: "🚨", label: "At risk", text: "You are overspending. Review your alerts and budgets." };
}

function makeInsights(r) {
  if (!r.total) return ["No expenses recorded for this month yet. Add your first expense to unlock insights."];
  const out = [];
  const top = r.categories[0];
  out.push(`${ICONS[top.category] || "📦"} ${top.category} is your biggest spend: ${inr(top.spent)} (${top.share_of_total}% of the month).`);
  if (r.prev_total > 0) {
    const pct = Math.round((Math.abs(r.change_vs_prev) / r.prev_total) * 100);
    out.push(r.change_vs_prev > 0 ? `📈 You are spending ${pct}% more than last month.` : `📉 Nice! You are spending ${pct}% less than last month.`);
  }
  const heavy = [...r.daily].sort((a, b) => b.total - a.total)[0];
  if (heavy) out.push(`📅 Your heaviest day was ${heavy.date}, with ${inr(heavy.total)} spent.`);
  if (r.income) {
    out.push(r.saved >= 0
      ? `💰 You can still save ${inr(r.saved)} (${Math.round((r.saved / r.income) * 100)}% of your income).`
      : `⚠️ You are ${inr(-r.saved)} over your monthly income.`);
  }
  const risky = r.categories.find((c) => c.status === "at_risk");
  if (risky) out.push(`🔮 At this pace ${risky.category} will reach ${inr(risky.projected)}, above your ${inr(risky.limit)} limit.`);
  return out;
}

function Alerts({ list }) {
  if (!list?.length) return <div className="alert ok"><span>✅</span><span>No alerts. Your spending is on track.</span></div>;
  const icon = { danger: "🚨", warning: "⚠️", info: "💡" };
  return list.map((a, i) => (
    <div key={i} className={`alert ${a.level}`}><span>{icon[a.level]}</span><span>{a.message}</span></div>
  ));
}

function Top({ title, sub, children }) {
  return (
    <div className="top">
      <div><h1>{title}</h1>{sub && <div className="sub">{sub}</div>}</div>
      <div className="row">{children}</div>
    </div>
  );
}

function DailyBars({ r }) {
  const map = Object.fromEntries(r.daily.map((d) => [d.date, d.total]));
  const days = Array.from({ length: r.days_in_month }, (_, i) => {
    const date = `${r.month}-${String(i + 1).padStart(2, "0")}`;
    return { day: i + 1, date, v: map[date] || 0 };
  });
  const max = Math.max(...days.map((d) => d.v), 1);
  const W = 700, H = 170, bw = W / days.length;
  return (
    <svg viewBox={`0 0 ${W} ${H + 22}`} style={{ width: "100%", height: "auto" }}>
      {days.map((d) => {
        const h = d.v ? Math.max((d.v / max) * H, 3) : 3;
        return (
          <g key={d.day}>
            <rect x={(d.day - 1) * bw + 2} y={H - h} width={bw - 4} height={h} rx="3"
              fill={d.v && d.v === max ? "var(--bad)" : "var(--accent)"} opacity={d.v ? 1 : 0.18}>
              <title>{`${d.date}: ${inr(d.v)}`}</title>
            </rect>
            {(d.day === 1 || d.day % 5 === 0) && (
              <text x={(d.day - 1) * bw + bw / 2} y={H + 16} fontSize="11" textAnchor="middle" fill="var(--muted)">{d.day}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/* ================= login / signup ================= */
function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [f, setF] = useState({ name: "", email: "", password: "", monthly_income: "", savings_goal: "" });
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const data = mode === "login"
        ? await api("/auth/login", { method: "POST", body: { email: f.email, password: f.password } })
        : await api("/auth/register", { method: "POST", body: { ...f, monthly_income: +f.monthly_income || 0, savings_goal: +f.savings_goal || 0 } });
      onAuth(data);
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <div className="auth">
      <div className="auth-art">
        <div className="logo big">₹</div>
        <h1>Know where your money goes, before it goes.</h1>
        <p>Smart Expense &amp; Spending Predictor turns your daily expenses into forecasts, alerts and clear monthly reviews.</p>
        <ul>
          <li>🧠 NLP model auto-categorises every expense</li>
          <li>🔮 30-day spending forecast with Prophet / LSTM</li>
          <li>🚨 Instant overspending alerts per category</li>
          <li>🔍 Anomaly detection for unusual transactions</li>
          <li>📊 Monthly review with a financial health score</li>
        </ul>
      </div>
      <div className="auth-form">
        <form className="card" onSubmit={submit}>
          <h2 style={{ margin: "0 0 4px", fontSize: 26 }}>{mode === "login" ? "Welcome back" : "Create your profile"}</h2>
          <p className="sub" style={{ marginTop: 0 }}>{mode === "login" ? "Log in to see your dashboard." : "Set up in under a minute."}</p>
          {err && <div className="alert danger"><span>🚨</span><span>{err}</span></div>}
          <div style={{ display: "grid", gap: 14 }}>
            {mode === "register" && <div className="field full"><label>Full name</label><input value={f.name} onChange={set("name")} required /></div>}
            <div className="field full"><label>Email</label><input type="email" value={f.email} onChange={set("email")} required /></div>
            <div className="field full"><label>Password (min 6 characters)</label><input type="password" value={f.password} onChange={set("password")} required minLength={6} /></div>
            {mode === "register" && (
              <div className="row">
                <div className="field full" style={{ flex: 1 }}><label>Monthly income (₹)</label><input type="number" min="0" value={f.monthly_income} onChange={set("monthly_income")} /></div>
                <div className="field full" style={{ flex: 1 }}><label>Savings goal (₹)</label><input type="number" min="0" value={f.savings_goal} onChange={set("savings_goal")} /></div>
              </div>
            )}
            <button className="btn">{mode === "login" ? "Log in" : "Sign up"}</button>
          </div>
          <p className="sub" style={{ marginBottom: 0 }}>
            {mode === "login" ? "New here? " : "Already have an account? "}
            <button type="button" className="link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
              {mode === "login" ? "Create a profile" : "Log in"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}

/* ================= shell (sidebar) ================= */
function Shell({ user, nav, tab, setTab, onLogout, theme, setTheme, children }) {
  return (
    <div className="fx" data-theme={theme}>
      <aside className="side">
        <div className="brand"><div className="logo">₹</div><div>Smart Expense<small>Spending Predictor</small></div></div>
        {nav.map(([k, icon, label]) => (
          <button key={k} className={`nav ${tab === k ? "on" : ""}`} onClick={() => setTab(k)}><span>{icon}</span>{label}</button>
        ))}
        <div className="spacer" />
        <button className="nav" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          <span>{theme === "dark" ? "☀️" : "🌙"}</span>{theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        <div className="usercard">
          <div className="avatar">{user.name[0]?.toUpperCase()}</div>
          <div><b>{user.name}</b><div className="sub">{user.role === "admin" ? "Administrator" : user.email}</div></div>
        </div>
        <button className="nav" onClick={onLogout}><span>🚪</span>Log out</button>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

/* ================= user: overview ================= */
function Overview({ token, user, refreshKey, go }) {
  const [month, setMonth] = useState(thisMonth());
  const [r, setR] = useState(null);
  useEffect(() => { api(`/my/review?month=${month}`, { token }).then(setR).catch(() => {}); }, [token, month, refreshKey]);
  if (!r) return <div className="card">Loading your dashboard…</div>;

  const score = r.total ? healthScore(r) : null;
  const v = verdict(score);
  const donut = r.categories.filter((c) => c.spent > 0).map((c) => ({ label: c.category, value: c.spent, color: CAT_COLORS[c.category] || "#94a3b8" }));
  const budgeted = r.categories.filter((c) => c.limit);
  const diff = r.change_vs_prev;
  const avg = r.days_elapsed ? r.total / r.days_elapsed : 0;

  return (
    <>
      <Top title={`${greeting()}, ${user.name.split(" ")[0]} 👋`} sub={`Your money at a glance for ${monthLabel(month)}`}>
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        <button className="btn" onClick={() => go("add")}>＋ Add expense</button>
      </Top>

      <div className="card hero">
        <Ring pct={score ?? 0} size={132} stroke={13} color="#fff" track="rgba(255,255,255,.25)">
          <div><div style={{ fontSize: 36, fontWeight: 800, lineHeight: 1 }}>{score ?? "–"}</div><div style={{ fontSize: 11, opacity: 0.8 }}>out of 100</div></div>
        </Ring>
        <div style={{ flex: 1, minWidth: 240 }}>
          <div className="sub">Financial health score</div>
          <h2 style={{ margin: "4px 0 6px", fontSize: 28 }}>{v.emoji} {v.label}</h2>
          <div className="sub">{v.text}</div>
        </div>
        <div className="hero-stats">
          <div><span className="sub">Daily average</span><b>{inr(avg)}</b></div>
          <div><span className="sub">Savings rate</span><b>{r.income ? `${Math.round((r.saved / r.income) * 100)}%` : "–"}</b></div>
        </div>
      </div>

      <h3 style={{ margin: "20px 0 10px" }}>🔔 Alerts</h3>
      <Alerts list={r.alerts} />

      <div className="grid g4" style={{ marginTop: 16 }}>
        <div className="card kpi"><div className="ico">💸</div><div><div className="lbl">Spent this month</div><div className="val">{inr(r.total)}</div></div></div>
        <div className="card kpi"><div className="ico">{diff > 0 ? "📈" : "📉"}</div><div><div className="lbl">Vs last month</div>
          <div className="val">{diff >= 0 ? "+" : "-"}{inr(Math.abs(diff)).replace("-", "")}</div>
          <div className={`delta ${diff > 0 ? "up" : "down"}`}>{r.prev_total ? `${diff > 0 ? "▲" : "▼"} ${Math.round((Math.abs(diff) / r.prev_total) * 100)}% vs ${inr(r.prev_total)}` : "No data last month"}</div></div></div>
        <div className="card kpi"><div className="ico">🔮</div><div><div className="lbl">Projected month-end</div><div className="val">{inr(r.projected_total)}</div></div></div>
        <div className="card kpi"><div className="ico">💰</div><div><div className="lbl">Income left</div><div className="val" style={{ color: r.saved < 0 ? "var(--bad)" : undefined }}>{r.income ? inr(r.saved) : "Set income"}</div></div></div>
      </div>

      <div className="grid g2">
        <div className="card">
          <h3>Where your money went</h3>
          {donut.length === 0 ? <div className="note">No expenses this month yet.</div> : (
            <div className="row" style={{ gap: 24, flexWrap: "wrap" }}>
              <Donut data={donut} center={<div><div className="sub">Total</div><div style={{ fontSize: 22, fontWeight: 800 }}>{inr(r.total)}</div></div>} />
              <div style={{ flex: 1, minWidth: 200 }}>
                {r.categories.filter((c) => c.spent > 0).map((c) => (
                  <div key={c.category} className="legend-row">
                    <span className="dot" style={{ background: CAT_COLORS[c.category] }} />
                    <span className="grow">{ICONS[c.category]} {c.category}</span>
                    <b>{inr(c.spent)}</b><span className="sub" style={{ width: 44, textAlign: "right" }}>{c.share_of_total}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="card">
          <h3>Daily spending</h3>
          <DailyBars r={r} />
          <div className="sub">Red bar = your heaviest day. Hover a bar for details.</div>
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <h3>🎯 Budget tracker</h3>
          {budgeted.length === 0 ? (
            <div className="note">No budgets yet. <button className="link" onClick={() => go("budgets")}>Set your first budget →</button></div>
          ) : (
            <div className="grid g3" style={{ marginBottom: 0 }}>
              {budgeted.map((c) => (
                <div key={c.category} className="budget-card">
                  <Ring pct={c.percent_of_limit} size={74} stroke={8} color={STATUS_COLORS[c.status]}>
                    <b style={{ fontSize: 14 }}>{Math.round(c.percent_of_limit)}%</b>
                  </Ring>
                  <div><b>{ICONS[c.category]} {c.category}</b><div className="sub">{inr(c.spent)} of {inr(c.limit)}</div></div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="card">
          <h3>💡 Smart insights</h3>
          {makeInsights(r).map((t, i) => <div key={i} className="insight">{t}</div>)}
        </div>
      </div>

      {r.top_expenses.length > 0 && (
        <div className="card">
          <h3>Biggest expenses this month</h3>
          <table className="tbl"><tbody>
            {r.top_expenses.map((t, i) => (
              <tr key={i}><td>{t.date}</td><td>{t.merchant || "-"}</td><td><Chip cat={t.category} /></td><td className="num">{inr(t.amount)}</td></tr>
            ))}
          </tbody></table>
        </div>
      )}
    </>
  );
}

/* ================= user: add expense ================= */
function Transactions({ token, meta, refreshKey, bump }) {
  const [month, setMonth] = useState(thisMonth());
  const [rows, setRows] = useState([]);
  useEffect(() => { api(`/my/expenses?month=${month}`, { token }).then(setRows).catch(() => {}); }, [token, month, refreshKey]);
  const del = async (id) => {
    if (!confirm("Delete this expense?")) return;
    await api(`/my/expenses/${id}`, { method: "DELETE", token });
    bump();
  };
  const relabel = async (id, category) => {
    await api(`/my/expenses/${id}/category`, { method: "PATCH", token, body: { category } });
    bump();
  };
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <div>
          <h3 style={{ margin: 0 }}>My expenses</h3>
          <div className="sub">Wrong category? Change it in the dropdown. The AI learns from your corrections.</div>
        </div>
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th>Paid via</th><th style={{ textAlign: "right" }}>Amount</th><th /></tr></thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.id}>
                <td>{x.date}</td><td>{x.merchant || "-"}</td>
                <td>
                  <select className="mini" value={x.category} onChange={(e) => relabel(x.id, e.target.value)}>
                    {meta.categories.map((c) => <option key={c} value={c}>{ICONS[c]} {c}</option>)}
                  </select>
                  {x.corrected ? <span className="ai-badge" title="You corrected this"> ✎</span> : null}
                </td>
                <td>{x.payment_mode}</td>
                <td className="num">{inr(x.amount)}</td>
                <td><button className="link bad" onClick={() => del(x.id)}>Delete</button></td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="sub">Nothing recorded for this month.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ImportCard({ token, bump }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const upload = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true); setErr(""); setRes(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch("/api/my/import-csv", { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Upload failed");
      setRes(d); bump();
    } catch (ex) { setErr(ex.message); }
    setBusy(false);
  };
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h3 style={{ margin: 0 }}>📄 Import a bank / UPI statement</h3>
          <div className="sub">CSV with date, description and amount columns. We clean it, remove duplicates and auto-categorise every row.</div>
        </div>
        <label className="btn" style={{ opacity: busy ? 0.6 : 1 }}>
          {busy ? "Importing…" : "Choose CSV file"}
          <input type="file" accept=".csv" onChange={upload} disabled={busy} style={{ display: "none" }} />
        </label>
      </div>
      {err && <div className="alert danger" style={{ marginTop: 12 }}><span>🚨</span><span>{err}</span></div>}
      {res && (
        <div className="alert ok" style={{ marginTop: 12 }}>
          <span>✅</span>
          <span>
            Imported <b>{res.imported}</b> of {res.rows_in_file} rows. Cleaned out {res.removed_in_cleaning} invalid, skipped {res.duplicates_skipped} duplicates,
            auto-categorised {res.auto_categorised}{res.needs_review ? `, and ${res.needs_review} marked "Other" for you to review below` : ""}.
          </span>
        </div>
      )}
    </div>
  );
}

function AddPage({ token, meta, refreshKey, bump }) {
  const blank = { date: today(), amount: "", category: "Groceries", merchant: "", payment_mode: "UPI" };
  const [f, setF] = useState(blank);
  const [touched, setTouched] = useState(false);
  const [ai, setAi] = useState(null);
  const [err, setErr] = useState("");
  const [flash, setFlash] = useState(null);

  const suggest = async () => {
    if (!f.merchant.trim() || touched) return;
    try {
      const d = await api(`/my/suggest-category?merchant=${encodeURIComponent(f.merchant)}`, { token });
      if (d.category) {
        setF((x) => ({ ...x, category: d.category }));
        setAi(d.source === "rules" ? `auto-categorised as ${d.category} (keyword match)` : `auto-categorised as ${d.category} (${d.confidence}% sure)`);
      } else setAi("not sure about this one, please pick a category");
    } catch {}
  };
  const pick = (c) => { setF({ ...f, category: c }); setTouched(true); setAi(null); };

  const save = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      await api("/my/expenses", { method: "POST", token, body: { ...f, amount: +f.amount } });
      const rev = await api(`/my/review?month=${f.date.slice(0, 7)}`, { token });
      const hit = rev.alerts.find((a) => a.category === f.category && a.level !== "info");
      setFlash(hit ? { level: hit.level, message: hit.message } : { level: "ok", message: `Added ${inr(+f.amount)} to ${f.category}.` });
      setF({ ...blank, date: f.date });
      setTouched(false); setAi(null);
      bump();
      setTimeout(() => setFlash(null), 7000);
    } catch (ex) { setErr(ex.message); }
  };

  return (
    <>
      <Top title="Add an expense" sub="Log it in seconds. The AI will suggest a category from the merchant name." />
      {flash && <div className={`alert ${flash.level}`}><span>{flash.level === "ok" ? "✅" : flash.level === "danger" ? "🚨" : "⚠️"}</span><span>{flash.message}</span></div>}
      <form className="card" onSubmit={save} style={{ marginBottom: 16 }}>
        {err && <div className="alert danger"><span>🚨</span><span>{err}</span></div>}
        <div className="grid g2" style={{ marginBottom: 0 }}>
          <div style={{ display: "grid", gap: 16 }}>
            <div className="field full"><label>Amount (₹)</label>
              <input className="amount-input" type="number" min="1" step="0.01" placeholder="0" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} required /></div>
            <div className="field full"><label>Merchant / description {ai && <span className="ai-badge">✨ {ai}</span>}</label>
              <input placeholder="e.g. Zomato, Uber, Netflix" value={f.merchant} onChange={(e) => setF({ ...f, merchant: e.target.value })} onBlur={suggest} /></div>
            <div className="row">
              <div className="field full" style={{ flex: 1 }}><label>Date</label><input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} required /></div>
            </div>
            <div className="field"><label>Paid via</label>
              <div className="seg">{meta.payment_modes.map((m) => <button type="button" key={m} className={f.payment_mode === m ? "on" : ""} onClick={() => setF({ ...f, payment_mode: m })}>{m}</button>)}</div></div>
          </div>
          <div className="field"><label>Category</label>
            <div className="cats">
              {meta.categories.map((c) => (
                <button type="button" key={c} className={`catbtn ${f.category === c ? "on" : ""}`} onClick={() => pick(c)}><span>{ICONS[c]}</span>{c}</button>
              ))}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 18 }}><button className="btn">Save expense</button></div>
      </form>
      <ImportCard token={token} bump={bump} />
      <Transactions token={token} meta={meta} refreshKey={refreshKey} bump={bump} />
    </>
  );
}

/* ================= user: budgets ================= */
function BudgetsPage({ token, meta, refreshKey, bump }) {
  const [budgets, setBudgets] = useState({});
  const [r, setR] = useState(null);
  const [draft, setDraft] = useState({});
  const load = useCallback(async () => {
    setBudgets(await api("/my/budgets", { token }));
    setR(await api(`/my/review?month=${thisMonth()}`, { token }));
  }, [token]);
  useEffect(() => { load(); }, [load, refreshKey]);

  const spent = (c) => r?.categories.find((x) => x.category === c)?.spent || 0;
  const save = async (c) => {
    const v = +draft[c];
    if (!v || v <= 0) return;
    await api("/my/budgets", { method: "PUT", token, body: { category: c, monthly_limit: v } });
    setDraft((d) => ({ ...d, [c]: undefined }));
    await load(); bump();
  };
  const remove = async (c) => {
    await api(`/my/budgets/${encodeURIComponent(c)}`, { method: "DELETE", token });
    await load(); bump();
  };

  const [sug, setSug] = useState(null);
  const [sugBusy, setSugBusy] = useState(false);
  const recommend = async () => {
    setSugBusy(true);
    try { setSug(await api("/my/budget-suggestions", { token })); } catch {}
    setSugBusy(false);
  };
  const apply = async (items) => {
    for (const x of items) await api("/my/budgets", { method: "PUT", token, body: { category: x.category, monthly_limit: x.suggested } });
    setSug(null);
    await load(); bump();
  };

  return (
    <>
      <Top title="Budgets" sub="Set a monthly limit per category. You get alerts at 80% and when you go over.">
        <button className="btn" onClick={recommend} disabled={sugBusy}>{sugBusy ? "Thinking…" : "✨ Recommend budgets for me"}</button>
      </Top>
      {sug && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <h3 style={{ margin: 0 }}>Personalised recommendations</h3>
              <div className="sub">{sug.ready ? `Based on your average of ${sug.basis_months} month(s) and your spending group.` : sug.message}</div>
            </div>
            {sug.ready && <div className="row"><button className="btn" onClick={() => apply(sug.suggestions)}>Apply all</button><button className="btn ghost" onClick={() => setSug(null)}>Dismiss</button></div>}
          </div>
          {sug.ready && (
            <table className="tbl" style={{ marginTop: 10 }}>
              <thead><tr><th>Category</th><th>Your monthly average</th><th>Suggested limit</th><th>Why</th></tr></thead>
              <tbody>
                {sug.suggestions.map((x) => (
                  <tr key={x.category}><td>{ICONS[x.category]} {x.category}</td><td>{inr(x.avg_monthly)}</td><td><b>{inr(x.suggested)}</b></td><td className="sub">{x.reason}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div className="grid g3">
        {meta.categories.map((c) => {
          const lim = budgets[c];
          const pct = lim ? (spent(c) / lim) * 100 : 0;
          const color = !lim ? "var(--muted)" : pct > 100 ? "var(--bad)" : pct >= 80 ? "var(--warn)" : "var(--good)";
          return (
            <div key={c} className="card">
              <div className="budget-card" style={{ marginBottom: 14 }}>
                <Ring pct={pct} size={78} stroke={9} color={color}><b>{lim ? `${Math.round(pct)}%` : "–"}</b></Ring>
                <div><b style={{ fontSize: 16 }}>{ICONS[c]} {c}</b><div className="sub">{inr(spent(c))} spent this month</div>{lim && <div className="sub">Limit {inr(lim)}</div>}</div>
              </div>
              <div className="row">
                <input type="number" min="1" placeholder="Monthly limit ₹" style={{ flex: 1 }}
                  value={draft[c] ?? lim ?? ""} onChange={(e) => setDraft({ ...draft, [c]: e.target.value })} />
                <button className="btn small" onClick={() => save(c)}>Save</button>
                {lim && <button className="btn danger small" onClick={() => remove(c)}>✕</button>}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

/* ================= user: profile ================= */
function ProfilePage({ user, token, onUpdate }) {
  const [f, setF] = useState({ name: user.name, monthly_income: user.monthly_income, savings_goal: user.savings_goal });
  const [msg, setMsg] = useState("");
  const save = async (e) => {
    e.preventDefault();
    const u = await api("/me", { method: "PUT", token, body: { ...f, monthly_income: +f.monthly_income, savings_goal: +f.savings_goal } });
    onUpdate(u); setMsg("Profile saved ✅");
  };
  return (
    <>
      <Top title="My profile" sub="Your income and savings goal power the health score and alerts." />
      <form className="card" onSubmit={save} style={{ maxWidth: 560 }}>
        <div style={{ display: "grid", gap: 16 }}>
          <div className="field full"><label>Email</label><input value={user.email} disabled /></div>
          <div className="field full"><label>Name</label><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
          <div className="field full"><label>Monthly income (₹)</label><input type="number" min="0" value={f.monthly_income} onChange={(e) => setF({ ...f, monthly_income: e.target.value })} /></div>
          <div className="field full"><label>Monthly savings goal (₹)</label><input type="number" min="0" value={f.savings_goal} onChange={(e) => setF({ ...f, savings_goal: e.target.value })} /></div>
          <div className="row"><button className="btn">Save changes</button>{msg && <span className="sub">{msg}</span>}</div>
        </div>
      </form>
    </>
  );
}

/* ================= user app ================= */
const USER_NAV = [["overview", "📊", "Overview"], ["add", "➕", "Add expense"], ["budgets", "🎯", "Budgets"], ["predictions", "🔮", "Predictions"], ["profile", "👤", "Profile"]];

function UserApp({ user, token, setUser, onLogout, theme, setTheme }) {
  const [tab, setTab] = useState("overview");
  const [meta, setMeta] = useState(null);
  const [key, setKey] = useState(0);
  const bump = () => setKey((k) => k + 1);
  useEffect(() => { api("/meta").then(setMeta); }, []);
  if (!meta) return <div className="fx" data-theme={theme} />;

  return (
    <Shell user={user} nav={USER_NAV} tab={tab} setTab={setTab} onLogout={onLogout} theme={theme} setTheme={setTheme}>
      {tab === "overview" && <Overview token={token} user={user} refreshKey={key} go={setTab} />}
      {tab === "add" && <AddPage token={token} meta={meta} refreshKey={key} bump={bump} />}
      {tab === "budgets" && <BudgetsPage token={token} meta={meta} refreshKey={key} bump={bump} />}
      {tab === "predictions" && <Predictions token={token} categories={meta.categories} />}
      {tab === "profile" && <ProfilePage user={user} token={token} onUpdate={setUser} />}
    </Shell>
  );
}

/* ================= admin ================= */
function RetrainCard({ token }) {
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const run = async () => {
    setBusy(true); setErr(""); setRes(null);
    try { setRes(await api("/admin/retrain", { method: "POST", token })); } catch (ex) { setErr(ex.message); }
    setBusy(false);
  };
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h3 style={{ margin: 0 }}>🧠 NLP feedback loop</h3>
          <div className="sub">Retrain the transaction classifier using all user expenses. Categories users corrected count extra.</div>
        </div>
        <button className="btn" onClick={run} disabled={busy}>{busy ? "Training…" : "Retrain model"}</button>
      </div>
      {err && <div className="alert danger" style={{ marginTop: 12 }}><span>🚨</span><span>{err}</span></div>}
      {res && (
        <div className="grid g4" style={{ marginTop: 14, marginBottom: 0 }}>
          <div className="insight"><div className="sub">Trained on</div><b>{res.trained_on} rows · {res.unique_merchants} merchants</b></div>
          <div className="insight"><div className="sub">User corrections used</div><b>{res.user_corrections}</b></div>
          <div className="insight"><div className="sub">Accuracy, known merchants</div><b>{res.accuracy}%</b></div>
          <div className="insight"><div className="sub">Accuracy, never-seen merchants</div><b>{res.unseen_accuracy ?? "n/a"}{res.unseen_accuracy != null ? "%" : ""}</b></div>
        </div>
      )}
    </div>
  );
}

function AdminOverview({ token }) {
  const [stats, setStats] = useState(null);
  const [over, setOver] = useState([]);
  useEffect(() => {
    api("/admin/stats", { token }).then(setStats).catch(() => {});
    api("/admin/overspenders", { token }).then(setOver).catch(() => {});
  }, [token]);
  if (!stats) return <div className="card">Loading…</div>;
  const maxC = Math.max(...stats.by_category.map((c) => c.total), 1);
  const months = [...stats.by_month].reverse();
  const maxM = Math.max(...months.map((m) => m.total), 1);

  return (
    <>
      <Top title="Admin overview" sub="Platform-wide activity across all users" />
      <div className="grid g4">
        {[["👥", "Users", stats.users], ["✅", "Active users", stats.active_users], ["🧾", "Expenses logged", stats.expenses], ["💸", "Total tracked", inr(stats.total_spent)]].map(([i, l, v]) => (
          <div key={l} className="card kpi"><div className="ico">{i}</div><div><div className="lbl">{l}</div><div className="val">{v}</div></div></div>
        ))}
      </div>
      <RetrainCard token={token} />
      <div className="card" style={{ marginTop: 16 }}>
        <h3>🚨 Users over budget this month ({over.length})</h3>
        {over.length === 0 && <div className="alert ok"><span>✅</span><span>No users are overspending right now.</span></div>}
        {over.map((o) => (
          <div key={o.id} className="alert danger" style={{ display: "block" }}>
            <b>{o.name}</b> <span className="sub">({o.email})</span> spent {inr(o.total)}
            {o.alerts.map((a, i) => <div key={i} className="sub">{a}</div>)}
          </div>
        ))}
      </div>
      <div className="grid g2">
        <div className="card">
          <h3>Spending by category (all users)</h3>
          {stats.by_category.map((c) => (
            <div key={c.category} style={{ marginBottom: 12 }}>
              <div className="row" style={{ justifyContent: "space-between" }}><span>{ICONS[c.category]} {c.category}</span><b>{inr(c.total)}</b></div>
              <div className="hbar"><div style={{ width: `${(c.total / maxC) * 100}%`, background: CAT_COLORS[c.category] || "var(--accent)" }} /></div>
            </div>
          ))}
        </div>
        <div className="card">
          <h3>Monthly totals</h3>
          {months.map((m) => (
            <div key={m.month} style={{ marginBottom: 12 }}>
              <div className="row" style={{ justifyContent: "space-between" }}><span>{monthLabel(m.month)}</span><b>{inr(m.total)}</b></div>
              <div className="hbar"><div style={{ width: `${(m.total / maxM) * 100}%`, background: "var(--accent)" }} /></div>
            </div>
          ))}
          {months.length === 0 && <div className="note">No data yet.</div>}
        </div>
      </div>
    </>
  );
}

function AdminUsers({ token }) {
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [detail, setDetail] = useState(null);
  const load = useCallback(() => api("/admin/users", { token }).then(setUsers), [token]);
  useEffect(() => { load(); }, [load]);

  const toggle = async (u) => { await api(`/admin/users/${u.id}`, { method: "PATCH", token, body: { active: !u.active } }); load(); };
  const del = async (u) => {
    if (!confirm(`Delete ${u.name} and all their expenses?`)) return;
    await api(`/admin/users/${u.id}`, { method: "DELETE", token }); setDetail(null); load();
  };
  const view = async (u) => setDetail({ user: u, review: await api(`/admin/users/${u.id}/review`, { token }) });
  const shown = users.filter((u) => (u.name + u.email).toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <Top title="Manage users" sub="View reviews, disable accounts or remove users">
        <input placeholder="Search name or email…" value={q} onChange={(e) => setQ(e.target.value)} />
      </Top>
      <div className="card" style={{ overflowX: "auto" }}>
        <table className="tbl">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Expenses</th><th>Total spent</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {shown.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name}</b></td><td>{u.email}</td><td>{u.role}</td><td>{u.expense_count}</td><td>{inr(u.total_spent)}</td>
                <td><span className="chip"><i style={{ background: u.active ? "var(--good)" : "var(--bad)" }} />{u.active ? "Active" : "Disabled"}</span></td>
                <td>{u.role !== "admin" && (<>
                  <button className="link" onClick={() => view(u)}>View</button>
                  <button className="link" onClick={() => toggle(u)}>{u.active ? "Disable" : "Enable"}</button>
                  <button className="link bad" onClick={() => del(u)}>Delete</button>
                </>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0 }}>{detail.user.name} · {monthLabel(detail.review.month)}</h3>
            <button className="btn ghost small" onClick={() => setDetail(null)}>Close</button>
          </div>
          <p className="sub">Spent {inr(detail.review.total)} · projected {inr(detail.review.projected_total)}</p>
          <Alerts list={detail.review.alerts} />
          {detail.review.categories.map((c) => (
            <div key={c.category} className="legend-row">
              <span className="dot" style={{ background: CAT_COLORS[c.category] }} /><span className="grow">{ICONS[c.category]} {c.category}</span>
              <b>{inr(c.spent)}</b>{c.limit && <span className="sub"> / {inr(c.limit)}</span>}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

const ADMIN_NAV = [["a-overview", "📊", "Overview"], ["a-users", "👥", "Users"]];

function AdminApp({ user, token, onLogout, theme, setTheme }) {
  const [tab, setTab] = useState("a-overview");
  return (
    <Shell user={user} nav={ADMIN_NAV} tab={tab} setTab={setTab} onLogout={onLogout} theme={theme} setTheme={setTheme}>
      {tab === "a-overview" && <AdminOverview token={token} />}
      {tab === "a-users" && <AdminUsers token={token} />}
    </Shell>
  );
}

/* ================= root ================= */
export default function Accounts() {
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem("theme") || "dark");
  useEffect(() => { localStorage.setItem("theme", theme); }, [theme]);

  useEffect(() => {
    if (!token) return setUser(null);
    api("/me", { token }).then(setUser).catch(() => { localStorage.removeItem("token"); setToken(null); });
  }, [token]);

  const onAuth = ({ token, user }) => { localStorage.setItem("token", token); setToken(token); setUser(user); };
  const logout = async () => {
    try { await api("/auth/logout", { method: "POST", token }); } catch {}
    localStorage.removeItem("token"); setToken(null); setUser(null);
  };

  if (!token) return <div className="fx" data-theme={theme}><AuthScreen onAuth={onAuth} /></div>;
  if (!user) return <div className="fx" data-theme={theme} />;
  const common = { user, token, onLogout: logout, theme, setTheme };
  return user.role === "admin" ? <AdminApp {...common} /> : <UserApp {...common} setUser={setUser} />;
}
