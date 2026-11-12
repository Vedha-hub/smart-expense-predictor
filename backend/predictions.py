"""
Per-user ML endpoints: forecast, anomalies, spending clusters, category suggestion, demo data.
Reuses the existing ml/ modules unchanged, but feeds them the logged-in user's own expenses.

Add to backend/main.py (next to the accounts router):
    from backend.predictions import router as predictions_router
    app.include_router(predictions_router)
"""
import os
import tempfile
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends

from backend.accounts import CATEGORIES, current_user, db
from ml import anomaly, categorizer, clustering, features, forecast
from ml.preprocess import clean_transactions, standardize_merchant

router = APIRouter(prefix="/api/my")

COLS = ["id", "date", "amount", "category", "merchant"]


def user_df(user_id: int) -> pd.DataFrame:
    with db() as c:
        rows = c.execute(
            "SELECT id, date, amount, category, merchant FROM expenses WHERE user_id=?",
            (user_id,)).fetchall()
    return pd.DataFrame([dict(r) for r in rows], columns=COLS)


@router.get("/predictions")
def predictions(horizon: int = 30, category: Optional[str] = None, user=Depends(current_user)):
    horizon = max(7, min(horizon, 90))
    df = user_df(user["id"])
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

    # ----- forecast -----
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
                pred, used = forecast.forecast(s, horizon, "auto")
                metrics = None
                if len(s) > 90:
                    try:
                        metrics = {**forecast.evaluate(s, 30, used if used != "lstm" else "baseline"),
                                   **forecast.evaluate_weekly(s, 4, "baseline")}
                    except Exception:
                        metrics = None
                out["forecast"] = {
                    "method": used, "category": category or "All",
                    "history": [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 2)}
                                for d, v in s.tail(60).items()],
                    "forecast": [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 2)}
                                 for d, v in pred.items()],
                    "predicted_total": round(float(pred.sum()), 2),
                    "metrics": metrics,
                }
    except Exception as e:
        out["forecast_message"] = f"Could not build a forecast: {e}"

    # ----- anomalies -----
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

    # ----- spending clusters / tips -----
    months = dates.dt.to_period("M").nunique()
    if months < 2:
        out["cluster_message"] = f"Need at least 2 months of data for spending groups (you have {months})."
    else:
        try:
            out["clusters"] = clustering.cluster_months(df)
        except Exception as e:
            out["cluster_message"] = f"Could not build spending groups: {e}"

    return out


@router.get("/suggest-category")
def suggest_category(merchant: str, user=Depends(current_user)):
    """NLP categorizer suggestion for the add-expense form."""
    pipe = categorizer.load()
    text = standardize_merchant(merchant)
    if pipe is None or not text:
        return {"category": None}
    cat = categorizer.predict([text], pipe)[0]
    return {"category": cat if cat in CATEGORIES else None}


@router.post("/demo-data")
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
    rows = [(user["id"], r.date, float(r.amount), r.category, r.merchant,
             "UPI" if r.payment_mode == "Unknown" else r.payment_mode.replace("Netbanking", "Net Banking"))
            for r in df.itertuples()]
    with db() as c:
        c.executemany(
            "INSERT INTO expenses(user_id,date,amount,category,merchant,payment_mode) VALUES(?,?,?,?,?,?)",
            rows)
    return {"added": len(rows)}
