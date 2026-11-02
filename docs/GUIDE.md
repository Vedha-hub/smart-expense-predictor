# Smart Expense & Spending Predictor — Complete Build Guide (3-member team)

Follow this top to bottom. Every command is meant to be copy-pasted.

---
## 0. What you are building (maps 1:1 to your architecture diagram)

| Architecture block | File | What it does |
|---|---|---|
| Data Ingestion & Preprocessing | `ml/preprocess.py` | clean dates/amounts, fill missing, standardise merchant names, drop duplicates |
| NLP Categorization | `ml/categorizer.py` | TF-IDF (word + character n-grams) + Logistic Regression → category |
| Feature Engineering | `ml/features.py` | daily series, rolling means, lags, weekend flag, category ratios |
| Forecasting Model | `ml/forecast.py`, `ml/lstm_model.py` | Prophet / LSTM / Holt-Winters baseline |
| Anomaly Detection | `ml/anomaly.py` | Isolation Forest + per-category z-score |
| Spending Clusters | `ml/clustering.py` | K-Means on monthly category shares → budget tips |
| Storage Layer | `backend/db.py` | SQLite (transactions, budgets, user corrections) |
| Application / API Layer | `backend/main.py` | FastAPI REST endpoints |
| Interactive Dashboard | `frontend/` | React + Recharts |
| Feedback loop | `PATCH /api/transactions/{id}` + `POST /api/retrain` | user re-labels → classifier retrains |

---
## 1. Install prerequisites (every member)
- Python 3.10+ (`python --version`), Node.js 18+ (`node --version`), Git (`git --version`)
- VS Code + a GitHub account each
- Windows: use Git Bash or PowerShell. Activate the venv with `venv\Scripts\activate`.

## 2. Suggested team split (swap as you like)
| Member | Owns | Branch prefix |
|---|---|---|
| **A – Data & NLP** | `generate_data.py`, `preprocess.py`, `categorizer.py`, real dataset, report: data + NLP chapters | `feature/data-*` |
| **B – Forecasting & Analytics** | `features.py`, `forecast.py`, `lstm_model.py`, `anomaly.py`, `clustering.py`, evaluation | `feature/ml-*` |
| **C – Backend & Frontend** | `backend/`, `frontend/`, integration, tests, demo | `feature/app-*` |

Everyone: write your own report section, and review at least one teammate's pull request.

## 3. Folder + Git setup

**One member (the "repo owner") does this:**
```bash
# 1) create GitHub repo "smart-expense-predictor" on github.com (empty, private), then:
unzip smart-expense-predictor.zip && cd smart-expense-predictor
git init
git branch -M main
git add .
git commit -m "chore: initial project structure"
git remote add origin https://github.com/<owner>/smart-expense-predictor.git
git push -u origin main
git checkout -b dev && git push -u origin dev
```
GitHub → Settings → Collaborators → add the other two.

**The other two members:**
```bash
git clone https://github.com/<owner>/smart-expense-predictor.git
cd smart-expense-predictor
git checkout dev
```

**Daily workflow (everyone):**
```bash
git checkout dev && git pull                      # start from latest
git checkout -b feature/ml-anomaly-tuning         # one branch per task
# ... code ...
git add ml/anomaly.py
git commit -m "feat(ml): tune isolation forest contamination"
git push -u origin feature/ml-anomaly-tuning
# open a Pull Request into `dev` on GitHub, a teammate reviews, then "Merge"
```
Rules: never commit directly to `main` or `dev`; merge `dev → main` only when the demo works; commit messages `feat:`, `fix:`, `docs:`, `test:`. If you get a merge conflict, run `git pull origin dev` on your branch, open the files with `<<<<<<<` markers, keep the right lines, then `git add . && git commit`.

## 4. Python environment (every member)
```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
```
Always run Python commands from the **project root** with `export PYTHONPATH=.` (Windows PowerShell: `$env:PYTHONPATH="."`).

## 5. Data
**Option 1 – synthetic (start here):**
```bash
python ml/generate_data.py          # creates data/sample_transactions.csv (~1200 rows, messy names, duplicates, outliers)
```
**Option 2 – real data (do this before submission):** export your own bank/UPI statement to CSV (remove personal info!) or use a public transactions dataset from Kaggle. Required columns: `date, description, amount`. Optional: `payment_mode, category`. If your file has no `category` column, the NLP model labels it — but it first needs a labelled set to train on, so label ~300–500 rows by hand once.

## 6. The ML pipeline, explained

**6.1 Preprocessing** (`ml/preprocess.py`). Parses dates and amounts (strips `₹` and commas), drops rows with missing date/amount, keeps positive amounts only, fills missing `payment_mode` with "Unknown", deduplicates, and creates `merchant` by lower-casing and removing noise like `UPI/`, `PVT LTD` and digits (`UPI/SWIGGY 48213` → `swiggy`).

**6.2 NLP categorization** (`ml/categorizer.py`). Merchant text → TF-IDF features (words **and** 2–4 character n-grams so spelling variants like "dominos"/"domino's" still match) → Logistic Regression. Train it:
```bash
python -m ml.train_all
```
It prints a classification report (precision/recall/F1 per category) and saves `models/categorizer.joblib`.
> ⚠ On the synthetic data you will see ~100% accuracy because there are only ~30 distinct merchants. **Do not report that number.** Report accuracy on your real dataset, using a split where merchants in the test set are unseen if you want to be strict.

**6.3 Feature engineering** (`ml/features.py`). Turns transactions into a continuous daily series (missing days = ₹0), then adds day-of-week, weekend flag, 7/30-day rolling means and lags 1/7/14.

**6.4 Forecasting** (`ml/forecast.py`). `forecast(series, horizon, method)`:
- `baseline` – Holt-Winters with weekly seasonality (works out of the box, used as a fallback)
- `prophet` – `pip install prophet`; handles weekly/yearly seasonality
- `lstm` – `pip install tensorflow`; 14-day window → next day, applied recursively

`method="auto"` tries Prophet and falls back to the baseline if it is not installed. Evaluate honestly (hold out the last 30 days):
```python
from ml import features, forecast
s = features.daily_series(df)
print(forecast.evaluate(s, 30, "baseline"))       # daily MAE / WAPE
print(forecast.evaluate_weekly(s, 4, "prophet"))  # weekly error — far more meaningful for budgeting
```
On the synthetic data the baseline gets roughly 69% daily WAPE and 34% weekly WAPE — daily spending is very noisy, so **compare models against this baseline** (Prophet vs LSTM vs baseline in a table) rather than claiming a single number is "good". That comparison is a strong results section.

**6.5 Anomaly detection** (`ml/anomaly.py`). Isolation Forest on log-amount, per-category z-score, weekday and category; a transaction is flagged only if the forest calls it an outlier **and** it is unusually *high* for its category (z > 2). Tune `contamination`.

**6.6 Clustering** (`ml/clustering.py`). Each month becomes a vector of category shares; K-Means (k=3) groups similar months; each group gets its top category and a tip. For your report, justify k with the silhouette score (`sklearn.metrics.silhouette_score`).

## 7. Backend (FastAPI)
```bash
export PYTHONPATH=.
uvicorn backend.main:app --reload --port 8000
```
Open http://127.0.0.1:8000/docs — interactive Swagger UI to test every endpoint (great for the demo).

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/upload` | upload CSV → clean → categorize → anomaly → store |
| POST | `/api/seed` | load the sample dataset |
| GET | `/api/transactions` | recent transactions |
| PATCH | `/api/transactions/{id}` | user corrects a category (feedback) |
| POST | `/api/retrain` | retrain classifier on stored (corrected) labels |
| GET | `/api/summary` | totals, by category, by month |
| GET | `/api/forecast?horizon=30&category=Groceries` | history + forecast + metrics |
| GET | `/api/anomalies` | flagged transactions |
| GET | `/api/clusters` | clusters + budget tips |
| POST/GET | `/api/budgets` | set / read monthly limits |
| GET | `/api/alerts` | spent vs limit, projected month-end |

Run the automated test: `python -m pytest -q tests` (covers the whole flow).

## 8. Frontend (React + Vite) and how it connects to the backend
```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```
Keep the backend running in a second terminal. **Integration:** `vite.config.js` proxies every `/api/...` call from port 5173 to FastAPI on 8000, and `src/api.js` is the only place that calls `fetch`. The `CORSMiddleware` in `backend/main.py` also allows `localhost:5173` so either approach works.

Data flow in the browser: `App.jsx` calls `api.summary/forecast/transactions/anomalies/clusters/alerts` in parallel → passes results as props to `SummaryCards`, `ForecastChart`, `CategoryPie`, `Alerts`, `Insights`, `Transactions`. Changing a category dropdown calls `PATCH`, then reloads.

**First demo run:** click *Load sample data* → charts appear. Set a budget in *Budget alerts* → coloured status appears. Change a category → click *Retrain classifier*.

## 9. Optional upgrades (pick after the core works)
- **Prophet / LSTM:** `pip install prophet tensorflow`, then call `/api/forecast?method=prophet` or `method=lstm`.
- **Per-category forecasts:** already supported — choose a category in the chart dropdown.
- **Multi-user + login** (your "future work"): add a `user_id` column and JWT auth.
- **Bank API integration** (future work): Account Aggregator / Plaid-style API → same `_ingest()` function.
- **Deployment:** backend on Render/Railway (`uvicorn backend.main:app --host 0.0.0.0 --port $PORT`), frontend on Vercel/Netlify (`npm run build`, set the API URL via an environment variable and remove the dev proxy).

## 10. Four-week plan
| Week | A | B | C |
|---|---|---|---|
| 1 | repo, data, preprocessing | features + baseline forecast | FastAPI skeleton + DB |
| 2 | categorizer + real data | Prophet/LSTM, evaluation | upload/summary/forecast endpoints, React layout |
| 3 | feedback/retrain loop | anomaly + clustering | charts, alerts, integration |
| 4 | report: data + NLP | report: models + results | tests, demo, README, slides |

## 11. Troubleshooting
| Problem | Fix |
|---|---|
| `ModuleNotFoundError: ml` | run from project root with `PYTHONPATH=.` |
| Frontend says "Request failed" / network error | backend not running on port 8000 |
| "No transactions yet" | click *Load sample data* or upload a CSV |
| CSV rejected | needs `date, description, amount` columns |
| Prophet install fails on Windows | use `method=baseline`/`lstm`, or install in a conda env |
| `git push` rejected | `git pull --rebase origin <branch>` then push |

## 12. Likely viva questions
1. *Why TF-IDF + Logistic Regression instead of BERT?* Small text, few classes, fast, explainable, trains in seconds; BERT is future work.
2. *Why char n-grams?* Robust to spelling variants and noisy statement text.
3. *Why Isolation Forest?* Unsupervised (no fraud labels), efficient, handles mixed features.
4. *Why a Holt-Winters baseline?* Any complex model must beat a simple one to justify itself.
5. *How does the system improve over time?* User corrections are stored and the classifier is retrained.
6. *What are the limitations?* Small personal datasets, daily spend is noisy, one-off big expenses (rent, travel) are unpredictable.
