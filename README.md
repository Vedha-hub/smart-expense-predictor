# Smart Expense & Spending Predictor
NLP transaction categorisation + time-series forecasting + anomaly detection + spending clusters, served by FastAPI with a React dashboard.
D. Y. Patil International University — CSE3001 (AIML), 2026-27.

## Quick start
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=.                                  # Windows PS: $env:PYTHONPATH="."
python ml/generate_data.py && python -m ml.train_all
uvicorn backend.main:app --reload --port 8000        # terminal 1  (docs: /docs)
cd frontend && npm install && npm run dev            # terminal 2  (http://localhost:5173)
```
Full step-by-step: [docs/GUIDE.md](docs/GUIDE.md)
