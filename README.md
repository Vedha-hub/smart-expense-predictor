# Smart Expense & Spending Predictor

A web app that turns everyday expenses into **forecasts, alerts and monthly reviews**. Users record expenses (by hand or from a bank/UPI statement), see where their money goes, set budgets per category, and get early warnings *before* they overspend. An admin panel monitors users and retrains the NLP model.

Built for **Foundations of AI & ML (CSE3001)**, B.Tech CSE (AIML), D. Y. Patil International University, Akurdi, Pune.

---

## Features

**For users**
- Sign up, create a profile (monthly income, savings goal)
- Record expenses across 10 categories, or **import a bank/UPI statement (CSV)**: rows are cleaned, de-duplicated and auto-categorised
- **AI auto-categorisation** from the merchant name (unsure cases are marked "Other" for review)
- Change any category in the table. Your corrections are stored and used to retrain the model
- **Budgets per category** with live progress rings, plus **personalised budget recommendations** from your own history
- **Monthly review**: spend vs last month, projected month-end, income left, daily spending chart, smart insights
- **Financial health score** (0 to 100)
- **Early overspending alerts** at 80% of a budget, when a limit is exceeded, or when the current pace will exceed it
- **Predictions**: spending forecast (Prophet / LSTM / Holt-Winters baseline), unusual-expense detection, spending groups with tips, and a model comparison table
- Dark and light mode

**For admins**
- Platform stats, users currently over budget, spending by category and month
- Search, view, disable or delete users
- **Retrain the NLP model** from all expenses (user-corrected labels count extra) and see its accuracy

---

## How it works

```
Data sources            Bank/UPI CSV  ·  manual entry  ·  synthetic demo data
      │
Ingestion & cleaning    ml/preprocess.py     dates, amounts (₹ / Rs / INR), missing values,
      │                                      merchant normalisation, de-duplication
NLP categorisation      ml/categorizer.py    TF-IDF (word + character n-grams) + Logistic Regression
      │                 backend/predictions.py   confidence threshold → keyword rules → "Other"
Feature engineering     ml/features.py       daily series, rolling stats, category shares
      │
Modelling (parallel)    ml/forecast.py       Prophet · LSTM (ml/lstm_model.py) · Holt-Winters baseline
                        ml/anomaly.py        Isolation Forest + per-category z-score
                        ml/clustering.py     K-Means on monthly category shares → tips
      │
Storage                 SQLite (data/accounts.db): users, expenses, budgets, cached predictions
      │
API layer               FastAPI (backend/)   REST endpoints, session-token auth
      │
Dashboard               React + Vite (frontend/)   user app and admin panel
      └── user corrections flow back into training data to improve the classifier
```

### Models and rules

| Part | Method | Notes |
|---|---|---|
| Categoriser | TF-IDF + Logistic Regression | Below 80% confidence it falls back to keyword rules, then to "Other" |
| Forecast | Prophet, LSTM, Holt-Winters | `Auto` uses Prophet, then the baseline if unavailable. Needs 14+ days of data |
| Forecast evaluation | 4-week hold-out | MAE and WAPE (total absolute error ÷ total actual spend). Needs 90+ days |
| Anomalies | Isolation Forest + z-score > 2 | Flags unusually *high* expenses. Needs 20+ expenses |
| Spending groups | K-Means (k = 3) | On monthly category shares. Needs 2+ months |
| Budget recommendations | Average of complete months | Fixed costs (Rent, Education, Utilities, Health): usual bill + 10%. Biggest flexible category: 15% lower. Others: 5% lower |
| Health score | 40 pts savings rate · 40 pts budget discipline · 20 pts trend vs last month | Heuristic defined by this project |

---

## Getting started

### Prerequisites
- **Python 3.11** (recommended: Prophet and TensorFlow have wheels for it)
- **Node.js 18+**

### 1. Clone and set up Python
```bash
git clone https://github.com/Vedha-hub/smart-expense-predictor.git
cd smart-expense-predictor

python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# macOS / Linux
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
The app needs: `fastapi uvicorn pandas numpy scikit-learn statsmodels joblib python-multipart prophet`.
**Optional (enables the LSTM model):** `python -m pip install tensorflow`

### 2. Train the categoriser (once)
The trained model file is not committed, so create it from the sample data:
```bash
python -m ml.train_all
```
If `data/sample_transactions.csv` is missing, run `python -m ml.generate_data` first.

### 3. Set the admin account (before the first run)
An admin is created automatically the first time the database is created. Set your own credentials first:
```powershell
# Windows PowerShell
$env:ADMIN_EMAIL = "you@example.com"
$env:ADMIN_PASSWORD = "choose-a-strong-password"
```
```bash
# macOS / Linux
export ADMIN_EMAIL="you@example.com"
export ADMIN_PASSWORD="choose-a-strong-password"
```
If you skip this, the placeholders `admin@expense.local` / `change-me-now` are used. **Change them.** Credentials only apply when the database has no admin yet.

### 4. Run (two terminals)
```bash
# Terminal 1: backend, from the project root
python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2: frontend
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**. Interactive API docs are at **http://localhost:8000/docs**.

---

## Trying it out
1. Sign up as a new user (income ₹50,000, savings goal ₹5,000).
2. **Predictions → Load demo data** (about 6 months of realistic expenses, loaded once per account).
3. **Budgets → Recommend budgets for me → Apply all**.
4. **Add expense**: type `Zomato` and click out of the box to see auto-categorisation. Try importing a CSV with `date`, `description`, `amount` columns.
5. Log in as admin to see platform stats and retrain the model.

---

## Tests
```bash
python tests/test_abstract.py
```
Runs **26 checks** covering every claim in the project abstract (import and cleaning, categorisation, budgets and alerts, forecasting with Prophet and LSTM, anomalies, clusters, recommendations, the corrections loop, admin and security). It uses a temporary database and a temporary copy of the model, so your real data is never touched.
`tests/test_api.py` covers the original single-dataset API.

---

## API overview
All user endpoints need `Authorization: Bearer <token>` from `/api/auth/login`.

| Area | Endpoints |
|---|---|
| Auth and profile | `POST /api/auth/register` · `POST /api/auth/login` · `POST /api/auth/logout` · `GET/PUT /api/me` |
| Expenses | `GET/POST /api/my/expenses` · `PUT/DELETE /api/my/expenses/{id}` · `PATCH /api/my/expenses/{id}/category` · `POST /api/my/import-csv` |
| Budgets and review | `GET/PUT /api/my/budgets` · `DELETE /api/my/budgets/{category}` · `GET /api/my/review` · `GET /api/my/alerts` · `GET /api/my/budget-suggestions` |
| ML | `GET /api/my/predictions` · `GET /api/my/model-comparison` · `GET /api/my/suggest-category` · `POST /api/my/demo-data` |
| Admin | `GET /api/admin/stats` · `GET /api/admin/users` · `PATCH/DELETE /api/admin/users/{id}` · `GET /api/admin/users/{id}/review` · `GET /api/admin/overspenders` · `POST /api/admin/retrain` |

The original single-dataset endpoints (`/api/upload`, `/api/summary`, `/api/forecast`, and so on) are still in `backend/main.py`. They power the first version of the dashboard (`frontend/src/App.jsx`), which is no longer the app's entry point.

---

## Project structure
```
backend/      FastAPI app: main.py, accounts.py (auth, expenses, budgets, review, admin),
              predictions.py (ML endpoints, CSV import, corrections, recommendations), db.py
ml/           preprocess · categorizer · features · forecast · lstm_model · anomaly · clustering
              generate_data · train_all
frontend/src/ Accounts.jsx (app shell, user and admin pages) · Predictions.jsx · ui.jsx · theme.css
data/         sample_transactions.csv (SQLite databases are created here, git-ignored)
models/       trained categoriser (git-ignored, created by ml.train_all)
tests/        test_abstract.py · test_api.py
docs/         project notes
```

---

## Results and honest limitations

- **Categoriser accuracy.** On the synthetic dataset it scores **100% on merchants it has seen** but only about **27% on merchants it has never seen** (the dataset has just 44 distinct merchants, so the model largely memorises names). The confidence threshold, keyword rules and the user-correction retraining loop exist to cover new merchants. Real bank data will need a larger and more varied training set.
- **Forecast accuracy.** Personal spending is lumpy (rent, one-off purchases), so error stays high. On one synthetic demo account the weekly WAPE was about **44% (Prophet), 46% (baseline) and 51% (LSTM)**. The models are close, so none clearly wins. Results vary by account.
- **Synthetic data.** Demo data is generated, not real transactions.
- **Security.** Passwords are hashed (PBKDF2) but session tokens do not expire, CORS allows only `localhost:5173`, and SQLite is a single local file. This is a college prototype, not production-hardened. Use HTTPS, token expiry and a real database before any real deployment.
- **Optional models.** LSTM needs TensorFlow, and Prophet needs its own install. The app falls back to the baseline and says so on screen.

## Future work
- Direct bank API / account-aggregator integration
- Mobile app
- Train the categoriser on a larger corpus of real merchant data
- Token expiry, HTTPS and a managed database for deployment

---

## Team
Vedhavathi Chennupati · Payal Mahajan · Sanika Nikam
School of Computer Science Engineering and Applications, D. Y. Patil International University, Akurdi, Pune.
