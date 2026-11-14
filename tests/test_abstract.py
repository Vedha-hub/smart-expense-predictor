"""
Verifies every claim in the project abstract against the real code.
Run from the project root:   python tests/test_abstract.py

Safe to run: it uses a temporary database and a temporary copy of the NLP model,
so your real users, expenses and trained model are never touched.
"""
import logging, os, shutil, sys, tempfile, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

import backend.accounts as acc
tmp = tempfile.mkdtemp()
acc.DB_PATH = os.path.join(tmp, "test.db")          # temporary database
acc.init_db()

from ml import categorizer
real_model = categorizer.MODEL_PATH
categorizer.MODEL_PATH = type(real_model)(os.path.join(tmp, "categorizer.joblib"))   # temporary model copy
if real_model.exists():
    shutil.copy(real_model, categorizer.MODEL_PATH)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.predictions import router as predictions_router

app = FastAPI()
app.include_router(acc.router)
app.include_router(predictions_router)
c = TestClient(app)

results = []
def check(claim, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + claim + (f"   [{detail}]" if detail else ""))

def hdr(token): return {"Authorization": f"Bearer {token}"}

print("\n=== Smart Expense & Spending Predictor: abstract verification ===\n")

# -- users & data collection
r = c.post("/api/auth/register", json={"name": "Test", "email": "t@test.com", "password": "secret1",
                                       "monthly_income": 50000, "savings_goal": 5000})
H = hdr(r.json()["token"])
check("Users can sign up and create a profile", r.status_code == 200)

csv = ("Date,Description,Amount,Payment Mode\n"
       "2026-10-02,UPI/SWIGGY 12345 PVT LTD,\"Rs 450\",UPI\n"
       "2026-10-03,POS DMART,1200,Debit Card\n"
       "2026-10-03,POS DMART,1200,Debit Card\n"
       "2026-10-04,UBER INDIA,-50,UPI\n"
       ",,,\n"
       "2026-10-06,Some Unknown Shop 123,999,Cash\n")
r = c.post("/api/my/import-csv", files={"file": ("s.csv", csv, "text/csv")}, headers=H).json()
check("Collection: bank/UPI statements (CSV) can be imported", r.get("imported", 0) >= 2, str(r))
check("Preprocessing: invalid rows and duplicates are cleaned", r.get("removed_in_cleaning", 0) >= 2, f"removed {r.get('removed_in_cleaning')}")
again = c.post("/api/my/import-csv", files={"file": ("s.csv", csv, "text/csv")}, headers=H).json()
check("Preprocessing: re-importing the same file adds no duplicates", again.get("imported") == 0, str(again))
rows = c.get("/api/my/expenses", headers=H).json()
check("Preprocessing: merchant names and payment modes are normalised",
      all(x["payment_mode"] in ("UPI", "Card", "Cash", "Net Banking") for x in rows) and any(x["merchant"] == "Swiggy" for x in rows),
      str(sorted({x['merchant'] for x in rows})))

# -- NLP categorisation
s = c.get("/api/my/suggest-category", params={"merchant": "UPI/NETFLIX 48213 PVT LTD"}, headers=H).json()
check("NLP: noisy merchant text is categorised automatically", s.get("category") == "Entertainment", str(s))
unk = c.get("/api/my/suggest-category", params={"merchant": "xyz traders"}, headers=H).json()
check("NLP: unknown merchants are NOT guessed (marked for review)", unk.get("category") is None, str(unk))
dm = [x for x in rows if x["merchant"] == "Some Unknown Shop"]
check("NLP: low-confidence CSV rows are marked 'Other' for the user", bool(dm) and dm[0]["category"] == "Other", str(dm and dm[0]["category"]))

# -- manual entry, categories, budgets, alerts
c.post("/api/my/demo-data", headers=H)
check("Users record expenses across separate categories", len({x["category"] for x in c.get("/api/my/expenses", headers=H).json()}) >= 8)
c.put("/api/my/budgets", json={"category": "Groceries", "monthly_limit": 100}, headers=H)
rev = c.get("/api/my/review", headers=H).json()
check("Early warning: overspending alert raised against a budget",
      any(a["level"] == "danger" and a["category"] == "Groceries" for a in rev["alerts"]))
check("Monthly breakdown with last-month comparison and projection", all(k in rev for k in ("categories", "prev_total", "projected_total")))

# -- forecasting (category + aggregate level)
agg = c.get("/api/my/predictions", headers=H).json()
check("Forecasting: aggregate spending forecast", agg["forecast"] is not None, f"model={agg['forecast'] and agg['forecast']['method']}")
cat = c.get("/api/my/predictions", params={"category": "Groceries"}, headers=H).json()
check("Forecasting: per-category forecast", cat["forecast"] is not None and cat["forecast"]["category"] == "Groceries")
check("Forecasting: error is measured (MAE / WAPE)", bool(agg["forecast"] and agg["forecast"]["metrics"]), str(agg["forecast"] and agg["forecast"]["metrics"]))
cmp_ = c.get("/api/my/model-comparison", headers=H).json()
avail = {x["method"]: x["available"] for x in cmp_["results"]}
check("Forecasting: Prophet model is available", avail.get("prophet") is True, str(avail))
check("Forecasting: LSTM model is available", avail.get("lstm") is True, str(avail) + "  (install with: python -m pip install tensorflow)")

# -- anomaly detection, clusters
check("Anomaly detection flags unusual transactions", len(agg["anomalies"]) > 0, f"{len(agg['anomalies'])} flagged")
check("Spending clusters produce behaviour groups with tips", bool(agg["clusters"] and agg["clusters"]["clusters"]))
sug = c.get("/api/my/budget-suggestions", headers=H).json()
check("Personalised budget recommendations", sug["ready"] and len(sug["suggestions"]) > 0)
rent = next((x for x in sug["suggestions"] if x["category"] == "Rent"), None)
check("Budget recommendations never go below a fixed bill (Rent stays >= 8000)", bool(rent) and rent["suggested"] >= 8000, str(rent and rent["suggested"]))

# -- feedback loop
eid = rows[0]["id"]
r = c.patch(f"/api/my/expenses/{eid}/category", json={"category": "Health"}, headers=H)
check("Feedback loop: user can correct a category", r.status_code == 200)
admin = c.post("/api/auth/login", json={"email": acc.ADMIN_EMAIL, "password": acc.ADMIN_PASSWORD})
HA = hdr(admin.json()["token"]) if admin.status_code == 200 else {}
rt = c.post("/api/admin/retrain", headers=HA)
check("Feedback loop: admin retrains the NLP model from corrections", rt.status_code == 200, str(rt.json()))

# -- admin & security
check("Admin dashboard: platform stats", c.get("/api/admin/stats", headers=HA).status_code == 200)
check("Admin dashboard: users currently over budget", c.get("/api/admin/overspenders", headers=HA).status_code == 200)
check("Security: normal users cannot call admin endpoints", c.get("/api/admin/stats", headers=H).status_code == 403)
check("Security: requests without login are rejected", c.get("/api/my/review").status_code == 401)

passed = sum(results)
print(f"\n{passed}/{len(results)} checks passed")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if passed == len(results) else 1)
