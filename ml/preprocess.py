"""Module 1: Data ingestion & preprocessing."""
import re
import pandas as pd

REQUIRED = ["date", "description", "amount"]


def standardize_merchant(text: str) -> str:
    """'UPI/SWIGGY 48213 PVT LTD' -> 'swiggy'"""
    t = str(text).lower()
    t = re.sub(r"\b(upi|pos|neft|imps|pvt|ltd|in|mum)\b", " ", t)
    t = re.sub(r"[^a-z\s&]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"].astype(str).str.replace(r"[₹,\s]", "", regex=True),
                                 errors="coerce")
    df = df.dropna(subset=["date", "amount", "description"])
    df = df[df["amount"] > 0]
    if "payment_mode" not in df.columns:
        df["payment_mode"] = "Unknown"
    df["payment_mode"] = df["payment_mode"].fillna("Unknown").astype(str).str.strip().str.title()
    df["description"] = df["description"].astype(str).str.strip()
    df["merchant"] = df["description"].map(standardize_merchant)
    df = df.drop_duplicates(subset=["date", "description", "amount"]).reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df
