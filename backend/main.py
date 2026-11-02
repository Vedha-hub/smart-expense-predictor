"""Application / API layer (FastAPI). Run: uvicorn backend.main:app --reload"""
import io
from contextlib import asynccontextmanager
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import db
from ml import anomaly, categorizer, clustering, features, forecast
from ml.preprocess import clean_transactions

@asynccontextmanager
async def lifespan(_):
    db.init_db()
    yield


app = FastAPI(title="Smart Expense & Spending Predictor", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class CategoryUpdate(BaseModel):
    category: str


class Budget(BaseModel):
    category: str
    monthly_limit: float


def _df() -> pd.DataFrame:
    df = db.all_transactions()
    if df.empty:
        raise HTTPException(404, "No transactions yet. Upload a CSV first.")
    return df


def _ingest(raw: pd.DataFrame) -> dict:
    df = clean_transactions(raw)
    # use the CSV's own labels if present, otherwise let the NLP model categorize
    if "category" in df.columns and df["category"].notna().all():
        if categorizer.load() is None:
            categorizer.train(df, report=False)
    else:
        df["category"] = categorizer.predict(df["merchant"])
    df = anomaly.detect(df)
    added = db.insert_transactions(df)
    # re-run anomaly detection over the whole history
    full = db.all_transactions()
    db.save_anomalies(anomaly.detect(full)[["id", "is_anomaly", "anomaly_score"]])
    return {"rows_in_file": len(raw), "after_cleaning": len(df), "new_rows_saved": added}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    try:
        raw = pd.read_csv(io.BytesIO(await file.read()))
        return _ingest(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/seed")
def seed():
    """Load the synthetic sample dataset (great for demos)."""
    return _ingest(pd.read_csv("data/sample_transactions.csv"))


@app.delete("/api/transactions")
def reset():
    db.clear_all()
    return {"ok": True}


@app.get("/api/transactions")
def transactions(limit: int = 200):
    df = _df().sort_values("date", ascending=False).head(limit)
    return df.to_dict("records")


@app.patch("/api/transactions/{tx_id}")
def correct(tx_id: int, body: CategoryUpdate):
    if not db.update_category(tx_id, body.category):
        raise HTTPException(404, "Transaction not found")
    return {"ok": True}


@app.post("/api/retrain")
def retrain():
    """Feedback loop: retrain the NLP classifier using user-corrected labels."""
    df = _df()
    categorizer.train(df, report=False)
    return {"trained_on": len(df), "user_corrections": int(df["user_corrected"].sum())}


@app.get("/api/summary")
def summary():
    df = _df()
    df["month"] = df["date"].str[:7]
    by_cat = df.groupby("category")["amount"].sum().round(2).sort_values(ascending=False)
    by_month = df.groupby("month")["amount"].sum().round(2)
    return {
        "total_spent": round(float(df["amount"].sum()), 2),
        "transactions": len(df),
        "avg_per_day": round(float(features.daily_series(df).mean()), 2),
        "by_category": [{"category": k, "amount": v} for k, v in by_cat.items()],
        "by_month": [{"month": k, "amount": v} for k, v in by_month.items()],
    }


@app.get("/api/forecast")
def get_forecast(horizon: int = 30, category: str | None = None, method: str = "auto"):
    df = _df()
    s = features.daily_series(df, category)
    if len(s) < 14:
        raise HTTPException(400, "Need at least 14 days of data to forecast.")
    pred, used = forecast.forecast(s, horizon, method)
    hist = s.tail(60)
    return {
        "method": used, "category": category or "All",
        "history": [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 2)} for d, v in hist.items()],
        "forecast": [{"date": d.strftime("%Y-%m-%d"), "amount": round(float(v), 2)} for d, v in pred.items()],
        "predicted_total": round(float(pred.sum()), 2),
        "metrics": forecast.evaluate(s, 30, "baseline") if len(s) > 90 else None,
    }


@app.get("/api/anomalies")
def anomalies():
    df = _df()
    out = df[df["is_anomaly"] == 1].sort_values("anomaly_score", ascending=False)
    return out.to_dict("records")


@app.get("/api/clusters")
def clusters():
    return clustering.cluster_months(_df())


@app.post("/api/budgets")
def set_budget(b: Budget):
    db.set_budget(b.category, b.monthly_limit)
    return {"ok": True}


@app.get("/api/budgets")
def budgets():
    return db.get_budgets()


@app.get("/api/alerts")
def alerts():
    """Budget alerts: compare this month's spend (and projected month-end) to limits."""
    df = _df()
    df["month"] = df["date"].str[:7]
    latest = df["month"].max()
    cur = df[df["month"] == latest]
    last_day = pd.Timestamp(latest + "-01").days_in_month
    days_seen = max(pd.to_datetime(cur["date"]).dt.day.max(), 1)
    out = []
    for cat, limit in db.get_budgets().items():
        spent = float(cur.loc[cur["category"] == cat, "amount"].sum())
        projected = spent / days_seen * last_day
        status = "over" if spent > limit else "warning" if projected > limit else "ok"
        out.append({"category": cat, "limit": limit, "spent": round(spent, 2),
                    "projected": round(projected, 2), "status": status, "month": latest})
    return out
