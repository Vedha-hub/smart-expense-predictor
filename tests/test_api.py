from fastapi.testclient import TestClient
from backend.main import app, db


def test_full_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    with TestClient(app) as c:
        assert c.post("/api/seed").status_code == 200
        assert c.get("/api/summary").json()["total_spent"] > 0
        assert len(c.get("/api/forecast?horizon=14&method=baseline").json()["forecast"]) == 14
        assert isinstance(c.get("/api/anomalies").json(), list)
        assert c.get("/api/clusters").json()["clusters"]
        c.post("/api/budgets", json={"category": "Food & Dining", "monthly_limit": 3000})
        assert c.get("/api/alerts").json()[0]["category"] == "Food & Dining"
        tx = c.get("/api/transactions?limit=1").json()[0]
        assert c.patch(f"/api/transactions/{tx['id']}", json={"category": "Health"}).status_code == 200
        assert c.post("/api/retrain").json()["user_corrections"] == 1
