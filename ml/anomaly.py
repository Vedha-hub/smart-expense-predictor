"""Module 5: Anomaly detection (Isolation Forest + per-category z-score)."""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def detect(df: pd.DataFrame, contamination: float = 0.02) -> pd.DataFrame:
    df = df.copy()
    if len(df) < 20:
        df["is_anomaly"] = 0
        df["anomaly_score"] = 0.0
        return df
    g = df.groupby("category")["amount"]
    df["z"] = (df["amount"] - g.transform("mean")) / g.transform("std").replace(0, 1).fillna(1)
    X = pd.DataFrame({
        "log_amount": np.log1p(df["amount"]),
        "z": df["z"].fillna(0),
        "dow": pd.to_datetime(df["date"]).dt.dayofweek,
        "cat": df["category"].astype("category").cat.codes,
    })
    iso = IsolationForest(contamination=contamination, random_state=42).fit(X)
    df["anomaly_score"] = -iso.score_samples(X)               # higher = weirder
    df["is_anomaly"] = ((iso.predict(X) == -1) & (df["z"] > 2)).astype(int)  # unusually HIGH only
    return df.drop(columns=["z"])
