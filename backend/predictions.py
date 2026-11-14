"""
Per-user ML endpoints that connect the web app to the ml/ package.

Covers the abstract's pipeline for every logged-in user:
  CSV import (cleaning + NLP categorisation) -> forecast (Prophet / LSTM / baseline)
  -> anomaly detection -> spending clusters -> budget recommendations,
plus the feedback loop (user re-labels a category -> admin retrains the NLP model)
and a stored prediction cache (the "storage layer" in the architecture diagram).

main.py needs only:
    from backend.predictions import router as predictions_router
    app.include_router(predictions_router)
"""
import hashlib
import io
import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from backend.accounts import CATEGORIES, admin_only, current_user, db
from ml import anomaly, categorizer, clustering, features, forecast
from ml.preprocess import clean_transactions, standardize_merchant

router = APIRouter(prefix="/api")

COLS = ["id", "date", "amount", "category", "merchant"]
METHODS = ("auto", "prophet", "lstm", "baseline")
FIXED = {"Rent", "Education", "Utilities", "Health"}   # costs you cannot easily cut
BASE_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_transactions.csv"


# ---------- one-time schema additions (safe to run every start) ----------
def _migrate():
    with db() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(expenses)")}
        if "corrected" not in cols:
            c.execute("ALTER TABLE expenses ADD COLUMN corrected INTEGER DEFAULT 0")
        c.execute("""CREATE TABLE IF NOT EXISTS prediction_cache(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cat TEXT NOT NULL, horizon INTEGER NOT NULL, method TEXT NOT NULL,
            signature TEXT NOT NULL, payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, cat, horizon, method))""")


_migrate()


def user_df(user_id: int) -> pd.DataFrame:
    with db() as c:
        rows = c.execute(
            "SELECT id, date, amount, category, merchant FROM expenses WHERE user_id=? ORDER BY id",
            (user_id,)).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=COLS)


def norm_mode(text) -> str:
    t = str(text).lower()
    if "card" in t:
        return "Card"
    if "cash" in t:
        return "Cash"
    if "net" in t or "bank" in t:
        return "Net Banking"
    return "UPI"


# ---------- hybrid categoriser: NLP model -> keyword rules -> "Other" ----------
CONFIDENCE = 0.8   # below this the model is guessing, so we do not trust it
RULES = {          # whole-word keywords, used only when the model is not confident
    "Rent": ["rent", "landlord", "lease", "hostel"],
    "Utilities": ["electricity", "electric", "water", "gas", "broadband", "recharge", "postpaid", "prepaid", "wifi", "internet", "dth"],
    "Health": ["pharmacy", "medical", "hospital", "clinic", "doctor", "diagnostic", "dental", "chemist", "gym", "fitness"],
    "Education": ["school", "college", "tuition", "course", "stationery", "exam", "fees", "university", "library"],
    "Transport": ["petrol", "fuel", "diesel", "metro", "cab", "taxi", "railway", "parking", "toll", "flight"],
    "Food & Dining": ["restaurant", "cafe", "coffee", "pizza", "burger", "biryani", "kitchen", "bakery", "dhaba", "food"],
    "Groceries": ["mart", "supermarket", "fresh", "grocery", "groceries", "kirana", "vegetables", "provision", "bazaar"],
    "Entertainment": ["cinema", "cinemas", "movie", "movies", "theatre", "game", "games", "gaming", "concert"],
    "Shopping": ["store", "mall", "fashion", "electronics", "apparel", "mobile", "lifestyle"],
}


def _rule(text: str):
    words = set(re.findall(r"[a-z]+", text))
    best, hits = None, 0
    for cat, kws in RULES.items():
        n = sum(k in words for k in kws)
        if n > hits:
            best, hits = cat, n
    return best


def categorize(merchants, pipe=None):
    """-> list of (category, source, confidence). source is 'model', 'rules' or 'none'."""
    pipe = pipe or categorizer.load()
    texts = [standardize_merchant(m) for m in merchants]
    probs = pipe.predict_proba(texts) if (pipe is not None and texts) else None
    out = []
    for i, t in enumerate(texts):
        conf = 0.0
        if probs is not None:
            j = int(probs[i].argmax())
            conf, cat = float(probs[i][j]), pipe.classes_[j]
            if conf >= CONFIDENCE and cat in CATEGORIES:
                out.append((cat, "model", conf))
                continue
        r = _rule(t)
        out.append((r, "rules", conf) if r else ("Other", "none", conf))
    return out


# ---------- forecast / anomalies / clusters ----------
def _build(df: pd.DataFrame, horizon: int, category: Optional[str], method: str) -> dict:
    out = {
        "transactions": len(df), "days_of_data": 0,
        "forecast": None, "forecast_message": None,
        "anomalies": [], "anomaly_message": None,
        "clusters": None, "cluster_message": None,
    }
    if df.empty:
        msg = "Add some expenses first. Predictions need a history to learn from."
        out.update(forecast_message=msg, anomaly_message=msg, cluster_message=msg)
        return out

    dates = pd.to_datetime(df["date"])
    out["days_of_data"] = int((dates.max() - dates.min()).days + 1)

    try:
        if category and category not in set(df["category"]):
            out["forecast_message"] = f"No {category} expenses recorded yet."
        else:
            s = features.daily_series(df, category or None)
            if len(s) < 14:
                out["forecast_message"] = (
                    f"Need at least 14 days of history to forecast (you have {len(s)}). "
                    "Keep logging expenses, or load demo data to try it out.")
            else:
                pred, used = forecast.forecast(s, horizon, method)
                metrics = None
                if len(s) > 90:
                    try:
                        m = used if used in ("baseline", "prophet") else "baseline"
                        metrics = {**forecast.evaluate(s, 30, m), **forecast.evaluate_weekly(s, 4, m)}
                    except Exception:
                        metrics = None
                out["forecast"] = {
                    "method": used, "requested": method, "category": category or "All",
                    "history": [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 2)}
                                for d, v in s.tail(60).items()],
                    "forecast": [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 2)}
                                 for d, v in pred.items()],
                    "predicted_total": round(float(pred.sum()), 2),
                    "metrics": metrics,
                }
    except Exception as e:
        out["forecast_message"] = f"Could not build a forecast: {e}"

    if len(df) < 20:
        out["anomaly_message"] = f"Need at least 20 expenses to spot unusual ones (you have {len(df)})."
    else:
        try:
            flagged = anomaly.detect(df)
            flagged = flagged[flagged["is_anomaly"] == 1].sort_values("anomaly_score", ascending=False)
            out["anomalies"] = [
                {"id": int(r.id), "date": r.date, "merchant": r.merchant,
                 "category": r.category, "amount": round(float(r.amount), 2)}
                for r in flagged.itertuples()]
            if not out["anomalies"]:
                out["anomaly_message"] = "No unusual expenses found. Everything looks normal."
        except Exception as e:
            out["anomaly_message"] = f"Could not run anomaly detection: {e}"

    months = dates.dt.to_period("M").nunique()
    if months < 2:
        out["cluster_message"] = f"Need at least 2 months of data for spending groups (you have {months})."
    else:
        try:
            out["clusters"] = clustering.cluster_months(df)
        except Exception as e:
            out["cluster_message"] = f"Could not build spending groups: {e}"
    return out


@router.get("/my/predictions")
def predictions(horizon: int = 30, category: Optional[str] = None, method: str = "auto",
                user=Depends(current_user)):
    horizon = max(7, min(horizon, 90))
    method = method if method in METHODS else "auto"
    df = user_df(user["id"])
    sig = hashlib.md5(df[["id", "amount", "category"]].to_csv().encode()).hexdigest()
    key = (user["id"], category or "", horizon, method)

    with db() as c:
        row = c.execute("""SELECT signature, payload FROM prediction_cache
                           WHERE user_id=? AND cat=? AND horizon=? AND method=?""", key).fetchone()
    if row and row["signature"] == sig:
        return {**json.loads(row["payload"]), "cached": True}

    out = _build(df, horizon, category, method)
    if not df.empty:
        with db() as c:
            c.execute("""INSERT INTO prediction_cache(user_id,cat,horizon,method,signature,payload)
                         VALUES(?,?,?,?,?,?)
                         ON CONFLICT(user_id,cat,horizon,method) DO UPDATE SET
                         signature=excluded.signature, payload=excluded.payload,
                         created_at=CURRENT_TIMESTAMP""", (*key, sig, json.dumps(out)))
    return {**out, "cached": False}


@router.get("/my/model-comparison")
def model_comparison(user=Depends(current_user)):
    """Accuracy of each forecasting model on this user's own last 4 weeks (for the report)."""
    df = user_df(user["id"])
    s = features.daily_series(df) if not df.empty else []
    if len(s) < 90:
        return {"ready": False, "results": [],
                "message": f"Need at least 90 days of history to compare models (you have {len(s)})."}
    results = []
    for m in ("baseline", "prophet", "lstm"):
        row = {"method": m, "available": False, "MAE": None, "daily_WAPE": None, "weekly_WAPE": None}
        try:
            d = forecast.evaluate(s, 30, m)
            if d["method"] == m:           # forecast() silently falls back if a library is missing
                w = forecast.evaluate_weekly(s, 4, m)
                row.update(available=True, MAE=d["MAE"], daily_WAPE=d["WAPE_%"], weekly_WAPE=w["weekly_WAPE_%"])
        except Exception:
            pass
        results.append(row)
    return {"ready": True, "results": results, "message": None}


# ---------- NLP: suggestion, CSV import, corrections ----------
@router.get("/my/suggest-category")
def suggest_category(merchant: str, user=Depends(current_user)):
    cat, src, conf = categorize([merchant])[0]
    if src == "none":
        return {"category": None, "source": "none", "confidence": round(conf * 100)}
    return {"category": cat, "source": src, "confidence": round(conf * 100)}


@router.post("/my/import-csv")
async def import_csv(file: UploadFile = File(...), user=Depends(current_user)):
    """Bank / UPI statement import: clean -> NLP categorise -> skip duplicates -> save."""
    try:
        raw = pd.read_csv(io.BytesIO(await file.read()))
        df = clean_transactions(raw)
    except Exception as e:
        raise HTTPException(400, f"Could not read this CSV: {e}")
    if df.empty:
        raise HTTPException(400, "No valid rows found. The CSV needs date, description and amount columns.")
    df = df.head(5000)

    labelled = df["category"] if "category" in df.columns else pd.Series([None] * len(df), index=df.index)
    use_given = labelled.isin(CATEGORIES)
    cats = categorize(df["merchant"].tolist())
    predicted = pd.Series([c for c, _, _ in cats], index=df.index)
    df["final_category"] = labelled.where(use_given, predicted)
    ai_count = int((~use_given).sum())
    needs_review = int(((~use_given) & (predicted == "Other")).sum())

    with db() as c:
        have = {(r["date"], (r["merchant"] or "").lower(), round(r["amount"], 2))
                for r in c.execute("SELECT date, merchant, amount FROM expenses WHERE user_id=?", (user["id"],))}
    rows, dup = [], 0
    for r in df.itertuples():
        merchant = str(r.merchant).title()
        k = (r.date, merchant.lower(), round(float(r.amount), 2))
        if k in have:
            dup += 1
            continue
        have.add(k)
        rows.append((user["id"], r.date, float(r.amount), r.final_category, merchant, norm_mode(r.payment_mode)))
    with db() as c:
        c.executemany(
            "INSERT INTO expenses(user_id,date,amount,category,merchant,payment_mode) VALUES(?,?,?,?,?,?)", rows)
    return {"rows_in_file": len(raw), "removed_in_cleaning": len(raw) - len(df),
            "duplicates_skipped": dup, "imported": len(rows), "auto_categorised": ai_count,
            "needs_review": needs_review}


class CategoryIn(BaseModel):
    category: str


@router.patch("/my/expenses/{eid}/category")
def correct_category(eid: int, body: CategoryIn, user=Depends(current_user)):
    """User re-labels a transaction. These corrections feed the next NLP retrain."""
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category")
    with db() as c:
        cur = c.execute("UPDATE expenses SET category=?, corrected=1 WHERE id=? AND user_id=?",
                        (body.category, eid, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "Expense not found")
    return {"ok": True}


@router.post("/admin/retrain")
def retrain(_=Depends(admin_only)):
    """Feedback loop: retrain the NLP classifier on the base data + all user expenses,
    with user-corrected labels counted extra. Returns hold-out accuracy for the report."""
    frames = []
    if BASE_CSV.exists():
        try:
            b = clean_transactions(pd.read_csv(BASE_CSV))
            if "category" in b.columns:
                frames.append(b[["merchant", "category"]])
        except Exception:
            pass
    with db() as c:
        rows = c.execute("SELECT merchant, category, corrected FROM expenses WHERE merchant != ''").fetchall()
    u = pd.DataFrame([dict(r) for r in rows], columns=["merchant", "category", "corrected"])
    corrections, fixed = 0, None
    if len(u):
        u["merchant"] = u["merchant"].map(standardize_merchant)
        u = u[u["merchant"] != ""]
        corrections = int(u["corrected"].sum())
        frames.append(u[["merchant", "category"]])
        fixed = u[u["corrected"] == 1][["merchant", "category"]]
    if not frames:
        raise HTTPException(400, "No labelled data available to train on.")
    df = pd.concat(frames, ignore_index=True).dropna()
    df = df[df["category"].isin(CATEGORIES)]
    if len(df) < 30:
        raise HTTPException(400, "Not enough labelled data to retrain yet.")

    strat = df["category"] if df["category"].value_counts().min() >= 2 else None
    Xtr, Xte, ytr, yte = train_test_split(df["merchant"], df["category"], test_size=0.2,
                                          random_state=42, stratify=strat)
    acc = accuracy_score(yte, categorizer.build_pipeline().fit(Xtr, ytr).predict(Xte))

    # harder, more honest test: merchants the model has never seen during training
    unseen = None
    if df["merchant"].nunique() >= 10:
        accs = []
        for seed in range(3):
            tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed)
                          .split(df, groups=df["merchant"]))
            m = categorizer.build_pipeline().fit(df["merchant"].iloc[tr], df["category"].iloc[tr])
            accs.append(accuracy_score(df["category"].iloc[te], m.predict(df["merchant"].iloc[te])))
        unseen = round(float(np.mean(accs)) * 100, 2)

    final = df
    if fixed is not None and len(fixed):
        final = pd.concat([df] + [fixed] * 4, ignore_index=True)   # corrections count 5x
    categorizer.train(final, report=False)
    return {"trained_on": len(df), "unique_merchants": int(df["merchant"].nunique()),
            "user_corrections": corrections, "accuracy": round(acc * 100, 2), "unseen_accuracy": unseen}


# ---------- budget recommendations (based on history + spending clusters) ----------
@router.get("/my/budget-suggestions")
def budget_suggestions(user=Depends(current_user)):
    df = user_df(user["id"])
    if df.empty:
        return {"ready": False, "suggestions": [], "message": "Add some expenses first so we can learn your pattern."}
    df["month"] = df["date"].str[:7]
    months = sorted(df["month"].unique())
    now = datetime.now().strftime("%Y-%m")
    use = [m for m in months if m != now]            # the current month is still incomplete
    if use and df["date"].min()[8:10] != "01" and use[0] == df["date"].min()[:7]:
        use = use[1:]                                 # data starts mid-month, so the first month is partial
    use = use or [m for m in months if m != now] or months
    monthly = (df[df["month"].isin(use)]
               .pivot_table(index="month", columns="category", values="amount", aggfunc="sum", fill_value=0.0))
    avg, med = monthly.mean(), monthly.median()

    # the user's behaviour group (K-Means on monthly category shares) decides which category to trim hardest
    focus = None
    if len(months) >= 2:
        try:
            cl = clustering.cluster_months(df)
            cid = next((m["cluster"] for m in cl["months"] if m["month"] == months[-1]), None)
            grp = next((c for c in cl["clusters"] if c["cluster"] == cid), None)
            if grp and grp["top_category"] not in FIXED:
                focus = grp["top_category"]
        except Exception:
            pass
    flex = avg[[c for c in avg.index if c not in FIXED]]
    if focus is None and len(flex):
        focus = flex.idxmax()

    out = []
    for cat, a in avg.sort_values(ascending=False).items():
        if a < 50 or cat not in CATEGORIES:
            continue
        if cat in FIXED:
            a = max(a, float(med.get(cat, a)))        # typical bill, not dragged down by an odd month
            factor, why = 1.10, "Fixed cost: your usual monthly bill plus a 10% buffer."
        elif cat == focus:
            factor = 0.85
            why = clustering.TIPS.get(cat, f"{cat} is your biggest flexible spend.") + " Target: 15% lower."
        else:
            factor, why = 0.95, "Flexible spend: a small 5% trim keeps you on track."
        out.append({"category": cat, "avg_monthly": round(float(a)),
                    "suggested": int(math.ceil(a * factor / 100.0) * 100), "reason": why})
    return {"ready": True, "basis_months": len(use), "suggestions": out, "message": None}


# ---------- demo data ----------
@router.post("/my/demo-data")
def demo_data(user=Depends(current_user)):
    """Insert ~6 months of realistic synthetic expenses for this user (for demos/testing)."""
    with db() as c:
        n = c.execute("SELECT COUNT(*) FROM expenses WHERE user_id=?", (user["id"],)).fetchone()[0]
    if n >= 200:
        return {"added": 0, "message": "Demo data already loaded"}

    from ml.generate_data import generate
    tmp = os.path.join(tempfile.gettempdir(), "demo_expenses.csv")
    raw = generate(months=6, out=tmp)
    df = clean_transactions(raw)
    df = df[df["category"].isin(CATEGORIES)]
    rows = [(user["id"], r.date, float(r.amount), r.category, str(r.merchant).title(), norm_mode(r.payment_mode))
            for r in df.itertuples()]
    with db() as c:
        c.executemany(
            "INSERT INTO expenses(user_id,date,amount,category,merchant,payment_mode) VALUES(?,?,?,?,?,?)",
            rows)
    return {"added": len(rows)}
