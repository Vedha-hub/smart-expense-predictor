"""Storage layer (SQLite). One file DB: data/expenses.db"""
import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "expenses.db"


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, description TEXT, merchant TEXT, amount REAL,
            payment_mode TEXT, category TEXT,
            is_anomaly INTEGER DEFAULT 0, anomaly_score REAL DEFAULT 0,
            user_corrected INTEGER DEFAULT 0,
            UNIQUE(date, description, amount));
        CREATE TABLE IF NOT EXISTS budgets(
            category TEXT PRIMARY KEY, monthly_limit REAL);
        """)


def insert_transactions(df: pd.DataFrame) -> int:
    cols = ["date", "description", "merchant", "amount", "payment_mode", "category",
            "is_anomaly", "anomaly_score"]
    with conn() as c:
        before = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        c.executemany(
            f"INSERT OR IGNORE INTO transactions({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
            df[cols].values.tolist())
        return c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] - before


def all_transactions() -> pd.DataFrame:
    with conn() as c:
        return pd.read_sql_query("SELECT * FROM transactions ORDER BY date", c)


def update_category(tx_id: int, category: str) -> bool:
    with conn() as c:
        cur = c.execute("UPDATE transactions SET category=?, user_corrected=1 WHERE id=?",
                        (category, tx_id))
        return cur.rowcount > 0


def save_anomalies(df: pd.DataFrame):
    with conn() as c:
        c.executemany("UPDATE transactions SET is_anomaly=?, anomaly_score=? WHERE id=?",
                      df[["is_anomaly", "anomaly_score", "id"]].values.tolist())


def set_budget(category: str, limit: float):
    with conn() as c:
        c.execute("INSERT INTO budgets VALUES(?,?) ON CONFLICT(category) DO UPDATE SET monthly_limit=?",
                  (category, limit, limit))


def get_budgets() -> dict:
    with conn() as c:
        return {r["category"]: r["monthly_limit"] for r in c.execute("SELECT * FROM budgets")}


def clear_all():
    with conn() as c:
        c.execute("DELETE FROM transactions")
