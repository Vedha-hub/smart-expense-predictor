"""Module 3: Feature engineering (time-series ready features)."""
import pandas as pd


def daily_series(df: pd.DataFrame, category: str | None = None) -> pd.Series:
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    if category:
        d = d[d["category"] == category]
    s = d.groupby("date")["amount"].sum()
    full = pd.date_range(s.index.min(), s.index.max(), freq="D")
    return s.reindex(full, fill_value=0.0).rename("spend")


def add_time_features(s: pd.Series) -> pd.DataFrame:
    f = s.to_frame("spend")
    f["dow"] = f.index.dayofweek
    f["is_weekend"] = (f["dow"] >= 5).astype(int)
    f["month"] = f.index.month
    f["roll7"] = f["spend"].rolling(7, min_periods=1).mean()
    f["roll30"] = f["spend"].rolling(30, min_periods=1).mean()
    for lag in (1, 7, 14):
        f[f"lag{lag}"] = f["spend"].shift(lag)
    return f


def category_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly share of spend per category (rows = months)."""
    d = df.copy()
    d["month"] = pd.to_datetime(d["date"]).dt.to_period("M").astype(str)
    pivot = d.pivot_table(index="month", columns="category", values="amount",
                          aggfunc="sum", fill_value=0.0)
    return pivot.div(pivot.sum(axis=1), axis=0)
