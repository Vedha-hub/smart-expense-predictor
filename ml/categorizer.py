"""Module 2: NLP-based transaction categorization (TF-IDF + Logistic Regression)."""
import joblib
import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline, FeatureUnion

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "categorizer.joblib"


def build_pipeline() -> Pipeline:
    feats = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2))),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
    ])
    return Pipeline([("tfidf", feats), ("clf", LogisticRegression(max_iter=1000, C=5))])


def train(df: pd.DataFrame, text_col="merchant", label_col="category", report=True) -> Pipeline:
    df = df.dropna(subset=[text_col, label_col])
    strat = df[label_col] if df[label_col].value_counts().min() >= 2 else None
    X_tr, X_te, y_tr, y_te = train_test_split(df[text_col], df[label_col], test_size=0.2,
                                              random_state=42, stratify=strat)
    if report:
        print(classification_report(y_te, build_pipeline().fit(X_tr, y_tr).predict(X_te), zero_division=0))
    pipe = build_pipeline().fit(df[text_col], df[label_col])   # final model uses all data
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(pipe, MODEL_PATH)
    return pipe


def load():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def predict(merchants, pipe=None):
    pipe = pipe or load()
    if pipe is None:
        return ["Uncategorized"] * len(merchants)
    return list(pipe.predict(list(merchants)))
