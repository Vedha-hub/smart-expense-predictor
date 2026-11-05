# Smart Expense & Spending Predictor

A personal-finance web app that turns raw transactions into forward-looking insight: it **categorises** expenses with NLP, **forecasts** future spending, **flags unusual transactions**, groups months into **spending clusters**, and **warns users when they overspend**.

> **D. Y. Patil International University** — School of Computer Science Engineering and Applications
> B.Tech CSE (AIML), Third Year, Sem V (2026-27) · Subject: *Foundations of Artificial Intelligence and Machine Learning (CSE3001)*

---

## Features

**For users**
- Sign up / log in, with a profile (monthly income and savings goal)
- Add expenses by hand (date, description, amount, payment mode); the category is **auto-detected** by the NLP model and can be corrected
- Upload a bank/UPI statement as CSV, or load sample data to try the app
- 10 spending categories and **per-category monthly budgets**
- **Overspend alerts**: a warning when you approach a limit and an alert when you exceed it, including a month-end projection
- **Monthly review**: spent so far, projected spend, remaining income and progress toward the savings goal
- Dashboard: KPI cards, category breakdown, spending **forecast** (Prophet, LSTM or baseline, selectable), anomaly list and cluster-based budgeting tips
- Corrections feed back into the classifier ("Retrain" button)

**For admins**
- Admin login with a separate panel: platform stats, users who are over budget, enable / disable / delete accounts

---

## How it works

```
 CSV / manual entry
        │
        ▼
 Preprocessing ──► NLP categorisation ──► Feature engineering
 (clean, dedupe,    (TF-IDF + Logistic      (daily series, rolling
  normalise names)   Regression)             means, lags, weekday)
                                                   │
                  ┌────────────────────────────────┼───────────────────────────┐
                  ▼                                ▼                           ▼
         Forecasting                       Anomaly detection            Spending clusters
   (Prophet / LSTM / Holt-Winters)    (Isolation Forest + z-score)   (K-Means on monthly shares)
                  └────────────────────────────────┼───────────────────────────┘
                                                   ▼
                             SQLite storage ──► FastAPI REST API ──► React dashboard
                                                                       │
                                  user corrections ◄───────────────────┘
```

| Stage | File | Technique |
|---|---|---|
| Preprocessing | `ml/preprocess.py` | parsing, missing values, deduplication, merchant-name normalisation |
| Categorisation | `ml/categorizer.py` | TF-IDF (word + character n-grams) + Logistic Regression |
| Features | `ml/features.py` | daily series, rolling means, lags, weekend flag, category shares |
| Forecasting | `ml/forecast.py`, `ml/lstm_model.py` | Prophet, LSTM, Holt-Winters baseline (automatic fallback) |
| Anomalies | `ml/anomaly.py` | Isolation Forest + per-category z-score |
| Clusters | `ml/clustering.py` | K-Means over monthly category shares, with budget tips |

---

## Tech stack

- **ML:** Python, pandas, NumPy, scikit-learn, statsmodels, Prophet and TensorFlow/Keras (the last two optional)
- **Backend:** FastAPI, Uvicorn, SQLite
- **Frontend:** React 18, Vite, Recharts

---

## Project structure

```
smart-expense-predictor/
├── backend/
│   ├── main.py            # FastAPI app and routes
│   ├── db.py              # SQLite storage for transactions and budgets
│   └── accounts.py        # signup/login, profiles, budgets, monthly review, admin API
├── ml/                    # preprocessing, categoriser, forecasting, anomalies, clustering
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── Accounts.jsx   # login/signup, user dashboard, admin panel
│   │   ├── App.jsx, api.js, styles.css
│   │   └── components/    # charts, alerts, transactions table, etc.
│   └── vite.config.js     # proxies /api to the backend on port 8000
├── data/                  # sample_transactions.csv (databases are git-ignored)
├── models/                # trained model files (git-ignored)
├── tests/
├── docs/GUIDE.md          # full build guide
└── requirements.txt
```

---

## Getting started

**Requirements:** Python 3.10 – 3.12 (3.11 recommended), Node.js 18+, Git.

### 1. Clone

```bash
git clone https://github.com/Vedha-hub/smart-expense-predictor.git
cd smart-expense-predictor
git checkout dev
```

### 2. Backend

```powershell
# Windows PowerShell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "."
python -m ml.train_all
python -m uvicorn backend.main:app --reload --port 8000
```

```bash
# macOS / Linux
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=.
python -m ml.train_all
python -m uvicorn backend.main:app --reload --port 8000
```

Interactive API docs: <http://127.0.0.1:8000/docs>

> Run `uvicorn` as `python -m uvicorn` from the activated `venv`. Otherwise Windows may pick up a different Python that lacks the packages.

### 3. Frontend (second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Keep the backend running at the same time.

### 4. Optional: Prophet and LSTM forecasting

```bash
pip install prophet tensorflow
```

Both are optional. Without them the app automatically falls back to the Holt-Winters baseline, and the chart shows which model was actually used.

### 5. Run the tests

```bash
python -m pytest -q tests
```

---

## Using the app

1. **Sign up** (or log in), then fill in your income and savings goal under your profile.
2. **Add expenses**, or click **Load sample data** to see the full dashboard immediately.
3. **Set budgets** per category. Add an expense that pushes you past the limit and the alert appears.
4. Open the **forecast** and pick a model and horizon.
5. **Correct** any wrong category in the transactions table, then press **Retrain** so the classifier learns from you.

**Admin:** the project ships with a default admin account for demos.

| | |
|---|---|
| Email | `weasadmin123@gmail.com` |
| Password | `admin@123` |

---

## Results and limitations

Numbers below come from the **synthetic sample dataset** (`data/sample_transactions.csv`). Replace them with results on real, labelled data before reporting them.

| Component | Result on sample data | Notes |
|---|---|---|
| Categoriser | ~100% accuracy (random split) | Optimistic: the same ~30 merchants appear in train and test. When whole merchants were held out in a one-off test, accuracy fell to roughly 47%, so a real labelled dataset is needed for honest numbers |
| Forecast (Holt-Winters baseline) | Daily WAPE ≈ 69%, weekly WAPE ≈ 34% | Daily spending is very spiky, so weekly totals are the more meaningful measure |
| Prophet / LSTM | *add your measured values here* | Compare against the baseline above |

Other limitations:
- Small personal datasets limit what a forecaster can learn, and one-off large purchases are unpredictable.
- Sessions and authentication are intended for a coursework demo, not production use.
- Never commit real bank statements. `data/*.db`, `venv/` and `node_modules/` are git-ignored.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'ml'` | Run from the project root with `PYTHONPATH` set to `.` |
| `ModuleNotFoundError: numpy` (or pandas) | The wrong Python is running. Activate `venv` and use `python -m uvicorn ...` |
| Dashboard shows "Request failed" | The backend is not running on port 8000 |
| `npm` is not recognised | Install Node.js LTS, then restart the terminal or VS Code |
| PowerShell blocks `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Forecast says the baseline was used | Prophet or TensorFlow is not installed in the active environment |

---

## Team

| Name | Contribution |
|---|---|
| Vedhavathi Chennupati |  *data and NLP* |
| Payal Mahajan |  *forecasting and analytics* |
| Sanika Nikam | *backend and frontend* |

## Roadmap

- Bank / Account Aggregator API integration
- Per-user personalised classifier and forecasts
- Mobile-friendly layout and notifications
- Stronger authentication (hashed credentials, token expiry, password reset)

## Contributing (team workflow)

- Never commit directly to `main` or `dev`.
- Create a branch per task: `git checkout -b feature/<short-name>`.
- Commit messages: `feat:`, `fix:`, `docs:`, `test:`.
- Open a pull request into `dev` and get a teammate to review it. Merge `dev` into `main` only when the demo works.

## License

Academic project. Add a licence (for example MIT) if you plan to share the code publicly.
