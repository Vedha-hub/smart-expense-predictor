"""Run once: python -m ml.train_all  -> trains categorizer & prints forecast accuracy."""
import pandas as pd
from ml import categorizer, features, forecast
from ml.preprocess import clean_transactions

if __name__ == "__main__":
    raw = pd.read_csv("data/sample_transactions.csv")
    df = clean_transactions(raw)
    categorizer.train(df)
    s = features.daily_series(df)
    print("Daily  :", forecast.evaluate(s, 30, "baseline"))
    print("Weekly :", forecast.evaluate_weekly(s, 4, "baseline"))
