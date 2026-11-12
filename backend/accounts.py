"""
User accounts + expense tracking + admin backend.
Uses its own SQLite file (data/accounts.db) so it does not touch your existing db.py.

Add to backend/main.py:
    from backend.accounts import router as accounts_router
    app.include_router(accounts_router)
"""
import calendar
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "accounts.db")
CATEGORIES = ["Groceries", "Rent", "Food & Dining", "Shopping", "Transport",
              "Utilities", "Entertainment", "Education", "Health", "Other"]
PAYMENT_MODES = ["UPI", "Card", "Cash", "Net Banking"]
WARN_AT = 0.8  # warn when 80% of a category budget is used

FIXED_CATEGORIES = {"Rent", "Education"}

def project(spent, elapsed, days, fixed=False):
    # No extrapolation for fixed costs or in the first week
    if fixed or elapsed < 7 or elapsed >= days:
        return round(spent, 2)
    return round(spent / elapsed * days, 2)

# Change these (or set env vars) before you demo / submit
# Set real values with environment variables (ADMIN_EMAIL / ADMIN_PASSWORD) when deploying
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@expense.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-now")
router = APIRouter(prefix="/api")


# ---------- database ----------
@contextmanager
def db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def hash_password(pw: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${h}"


def check_password(pw: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(pw, salt), stored)


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            monthly_income REAL DEFAULT 0,
            savings_goal REAL DEFAULT 0,
            role TEXT DEFAULT 'user',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions(
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            merchant TEXT DEFAULT '',
            payment_mode TEXT DEFAULT 'UPI',
            note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS budgets(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            monthly_limit REAL NOT NULL,
            PRIMARY KEY(user_id, category)
        );
        CREATE INDEX IF NOT EXISTS idx_exp_user_date ON expenses(user_id, date);
        """)
        if not c.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            c.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')",
                      ("Administrator", ADMIN_EMAIL, hash_password(ADMIN_PASSWORD)))


init_db()


# ---------- schemas ----------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=100)
    monthly_income: float = Field(default=0, ge=0)
    savings_goal: float = Field(default=0, ge=0)


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    monthly_income: float = Field(ge=0)
    savings_goal: float = Field(ge=0)


class ExpenseIn(BaseModel):
    date: str
    amount: float = Field(gt=0)
    category: str
    merchant: str = ""
    payment_mode: str = "UPI"
    note: str = ""


class BudgetIn(BaseModel):
    category: str
    monthly_limit: float = Field(gt=0)


class AdminUserPatch(BaseModel):
    active: Optional[bool] = None
    role: Optional[str] = None


# ---------- auth ----------
def current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not logged in")
    token = authorization[7:]
    with db() as c:
        row = c.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                           WHERE s.token=?""", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "Session expired, please log in again")
    if not row["active"]:
        raise HTTPException(403, "This account has been disabled")
    return dict(row)


def admin_only(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "name", "email", "monthly_income", "savings_goal", "role")}


def new_session(c, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (token, user_id))
    return token


def validate_expense(e: ExpenseIn):
    try:
        datetime.strptime(e.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, "Date must be YYYY-MM-DD")
    if e.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category")


@router.get("/meta")
def meta():
    return {"categories": CATEGORIES, "payment_modes": PAYMENT_MODES}


@router.post("/auth/register")
def register(body: RegisterIn):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email")
    with db() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists")
        cur = c.execute(
            "INSERT INTO users(name,email,password_hash,monthly_income,savings_goal) VALUES(?,?,?,?,?)",
            (body.name.strip(), email, hash_password(body.password), body.monthly_income, body.savings_goal))
        uid = cur.lastrowid
        token = new_session(c, uid)
        u = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    return {"token": token, "user": public_user(u)}


@router.post("/auth/login")
def login(body: LoginIn):
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
        if not row or not check_password(body.password, row["password_hash"]):
            raise HTTPException(401, "Wrong email or password")
        if not row["active"]:
            raise HTTPException(403, "This account has been disabled")
        token = new_session(c, row["id"])
    return {"token": token, "user": public_user(dict(row))}


@router.post("/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (authorization[7:],))
    return {"ok": True}


# ---------- profile ----------
@router.get("/me")
def me(user=Depends(current_user)):
    return public_user(user)


@router.put("/me")
def update_me(body: ProfileIn, user=Depends(current_user)):
    with db() as c:
        c.execute("UPDATE users SET name=?, monthly_income=?, savings_goal=? WHERE id=?",
                  (body.name.strip(), body.monthly_income, body.savings_goal, user["id"]))
        u = dict(c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
    return public_user(u)


# ---------- expenses ----------
@router.post("/my/expenses")
def add_expense(body: ExpenseIn, user=Depends(current_user)):
    validate_expense(body)
    with db() as c:
        cur = c.execute(
            "INSERT INTO expenses(user_id,date,amount,category,merchant,payment_mode,note) VALUES(?,?,?,?,?,?,?)",
            (user["id"], body.date, body.amount, body.category, body.merchant.strip(),
             body.payment_mode, body.note.strip()))
        eid = cur.lastrowid
    return {"id": eid, **body.model_dump()}


@router.get("/my/expenses")
def list_expenses(month: Optional[str] = None, category: Optional[str] = None,
                  user=Depends(current_user)):
    sql, args = "SELECT * FROM expenses WHERE user_id=?", [user["id"]]
    if month:
        sql += " AND substr(date,1,7)=?"
        args.append(month)
    if category:
        sql += " AND category=?"
        args.append(category)
    sql += " ORDER BY date DESC, id DESC LIMIT 500"
    with db() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


@router.put("/my/expenses/{eid}")
def edit_expense(eid: int, body: ExpenseIn, user=Depends(current_user)):
    validate_expense(body)
    with db() as c:
        cur = c.execute(
            """UPDATE expenses SET date=?,amount=?,category=?,merchant=?,payment_mode=?,note=?
               WHERE id=? AND user_id=?""",
            (body.date, body.amount, body.category, body.merchant.strip(), body.payment_mode,
             body.note.strip(), eid, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "Expense not found")
    return {"id": eid, **body.model_dump()}


@router.delete("/my/expenses/{eid}")
def delete_expense(eid: int, user=Depends(current_user)):
    with db() as c:
        cur = c.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (eid, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(404, "Expense not found")
    return {"ok": True}


# ---------- budgets ----------
@router.get("/my/budgets")
def get_budgets(user=Depends(current_user)):
    with db() as c:
        rows = c.execute("SELECT category, monthly_limit FROM budgets WHERE user_id=?",
                         (user["id"],)).fetchall()
    return {r["category"]: r["monthly_limit"] for r in rows}


@router.put("/my/budgets")
def set_budget(body: BudgetIn, user=Depends(current_user)):
    if body.category not in CATEGORIES:
        raise HTTPException(422, "Unknown category")
    with db() as c:
        c.execute("""INSERT INTO budgets(user_id,category,monthly_limit) VALUES(?,?,?)
                     ON CONFLICT(user_id,category) DO UPDATE SET monthly_limit=excluded.monthly_limit""",
                  (user["id"], body.category, body.monthly_limit))
    return {"ok": True}


@router.delete("/my/budgets/{category}")
def remove_budget(category: str, user=Depends(current_user)):
    with db() as c:
        c.execute("DELETE FROM budgets WHERE user_id=? AND category=?", (user["id"], category))
    return {"ok": True}


# ---------- monthly review + alerts ----------
def build_review(user: dict, month: str) -> dict:
    try:
        y, m = map(int, month.split("-"))
        first = date(y, m, 1)
    except Exception:
        raise HTTPException(422, "Month must be YYYY-MM")
    days_in_month = calendar.monthrange(y, m)[1]
    prev_last = first - timedelta(days=1)
    prev_month = prev_last.strftime("%Y-%m")

    with db() as c:
        def totals(mon):
            rows = c.execute("""SELECT category, SUM(amount) t, COUNT(*) n FROM expenses
                                WHERE user_id=? AND substr(date,1,7)=? GROUP BY category""",
                             (user["id"], mon)).fetchall()
            return {r["category"]: (r["t"], r["n"]) for r in rows}
        cur_t, prev_t = totals(month), totals(prev_month)
        budgets = {r["category"]: r["monthly_limit"] for r in c.execute(
            "SELECT category, monthly_limit FROM budgets WHERE user_id=?", (user["id"],))}
        daily = [dict(r) for r in c.execute(
            """SELECT date, SUM(amount) total FROM expenses
               WHERE user_id=? AND substr(date,1,7)=? GROUP BY date ORDER BY date""",
            (user["id"], month))]
        top = [dict(r) for r in c.execute(
            """SELECT date, merchant, category, amount FROM expenses
               WHERE user_id=? AND substr(date,1,7)=? ORDER BY amount DESC LIMIT 5""",
            (user["id"], month))]

    total = sum(t for t, _ in cur_t.values())
    prev_total = sum(t for t, _ in prev_t.values())

    today = date.today()
    if first.strftime("%Y-%m") == today.strftime("%Y-%m"):
        elapsed = today.day
    elif first > today:
        elapsed = 0
    else:
        elapsed = days_in_month
    fixed_total = sum(t for cat, (t, _) in cur_t.items() if cat in FIXED_CATEGORIES)
    projected = round(fixed_total + project(total - fixed_total, elapsed, days_in_month), 2)

    categories, alerts = [], []
    for cat in CATEGORIES:
        spent = cur_t.get(cat, (0, 0))[0]
        count = cur_t.get(cat, (0, 0))[1]
        if spent == 0 and cat not in budgets:
            continue
        limit = budgets.get(cat)
        prev = prev_t.get(cat, (0, 0))[0]
        status, proj = "none", None
        if limit:
            pct = spent / limit
            proj = project(spent, elapsed, days_in_month, cat in FIXED_CATEGORIES)
            if pct > 1:
                status = "over"
                alerts.append({"level": "danger", "category": cat,
                               "message": f"{cat}: you have overspent. ₹{spent:,.0f} spent against a limit of ₹{limit:,.0f} (₹{spent - limit:,.0f} over)."})
            elif pct >= WARN_AT:
                status = "warning"
                alerts.append({"level": "warning", "category": cat,
                               "message": f"{cat}: {pct*100:.0f}% of your ₹{limit:,.0f} budget is used."})
            elif proj > limit:
                status = "at_risk"
                alerts.append({"level": "info", "category": cat,
                               "message": f"{cat}: at this pace you will spend about ₹{proj:,.0f}, above your ₹{limit:,.0f} limit."})
            else:
                status = "ok"
        categories.append({
            "category": cat, "spent": round(spent, 2), "count": count, "limit": limit,
            "percent_of_limit": round(spent / limit * 100, 1) if limit else None,
            "share_of_total": round(spent / total * 100, 1) if total else 0,
            "prev_month": round(prev, 2),
            "change_vs_prev": round(spent - prev, 2),
            "projected": proj, "status": status,
        })
    categories.sort(key=lambda r: r["spent"], reverse=True)

    income = user["monthly_income"] or 0
    if income and total > income:
        alerts.insert(0, {"level": "danger", "category": None,
                          "message": f"Total spending ₹{total:,.0f} is higher than your monthly income ₹{income:,.0f}."})
    saved = income - total if income else None
    goal = user["savings_goal"] or 0
    if income and goal and saved < goal and elapsed >= days_in_month:
        alerts.append({"level": "warning", "category": None,
                       "message": f"You saved ₹{max(saved,0):,.0f}, below your goal of ₹{goal:,.0f}."})
    elif income and goal and projected > income - goal:
        alerts.append({"level": "info", "category": None,
                       "message": f"At this pace you will miss your savings goal of ₹{goal:,.0f}."})
    order = {"danger": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order[a["level"]])

    return {
        "month": month, "prev_month": prev_month, "total": round(total, 2),
        "prev_total": round(prev_total, 2), "change_vs_prev": round(total - prev_total, 2),
        "income": income, "saved": round(saved, 2) if saved is not None else None,
        "savings_goal": goal, "projected_total": projected,
        "days_elapsed": elapsed, "days_in_month": days_in_month,
        "categories": categories, "daily": daily, "top_expenses": top, "alerts": alerts,
    }


@router.get("/my/review")
def my_review(month: Optional[str] = None, user=Depends(current_user)):
    return build_review(user, month or date.today().strftime("%Y-%m"))


@router.get("/my/alerts")
def my_alerts(user=Depends(current_user)):
    return build_review(user, date.today().strftime("%Y-%m"))["alerts"]


# ---------- admin ----------
@router.get("/admin/stats")
def admin_stats(_=Depends(admin_only)):
    with db() as c:
        one = lambda q: c.execute(q).fetchone()[0]
        return {
            "users": one("SELECT COUNT(*) FROM users WHERE role='user'"),
            "active_users": one("SELECT COUNT(*) FROM users WHERE role='user' AND active=1"),
            "expenses": one("SELECT COUNT(*) FROM expenses"),
            "total_spent": round(one("SELECT COALESCE(SUM(amount),0) FROM expenses"), 2),
            "by_category": [dict(r) for r in c.execute(
                "SELECT category, ROUND(SUM(amount),2) total, COUNT(*) n FROM expenses GROUP BY category ORDER BY total DESC")],
            "by_month": [dict(r) for r in c.execute(
                "SELECT substr(date,1,7) month, ROUND(SUM(amount),2) total FROM expenses GROUP BY month ORDER BY month DESC LIMIT 12")],
        }


@router.get("/admin/users")
def admin_users(_=Depends(admin_only)):
    with db() as c:
        rows = c.execute("""
            SELECT u.id,u.name,u.email,u.role,u.active,u.monthly_income,u.created_at,
                   COUNT(e.id) expense_count, COALESCE(SUM(e.amount),0) total_spent
            FROM users u LEFT JOIN expenses e ON e.user_id=u.id
            GROUP BY u.id ORDER BY u.created_at DESC""").fetchall()
    return [dict(r) for r in rows]


@router.patch("/admin/users/{uid}")
def admin_patch_user(uid: int, body: AdminUserPatch, admin=Depends(admin_only)):
    if uid == admin["id"]:
        raise HTTPException(400, "You cannot change your own account here")
    with db() as c:
        if body.active is not None:
            c.execute("UPDATE users SET active=? WHERE id=?", (int(body.active), uid))
            if not body.active:
                c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        if body.role in ("user", "admin"):
            c.execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
    return {"ok": True}


@router.delete("/admin/users/{uid}")
def admin_delete_user(uid: int, admin=Depends(admin_only)):
    if uid == admin["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    with db() as c:
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    return {"ok": True}


@router.get("/admin/users/{uid}/review")
def admin_user_review(uid: int, month: Optional[str] = None, _=Depends(admin_only)):
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return build_review(dict(row), month or date.today().strftime("%Y-%m"))


@router.get("/admin/overspenders")
def admin_overspenders(_=Depends(admin_only)):
    """Users currently over budget this month, for the admin alert panel."""
    month = date.today().strftime("%Y-%m")
    out = []
    with db() as c:
        users = [dict(r) for r in c.execute("SELECT * FROM users WHERE role='user' AND active=1")]
    for u in users:
        rev = build_review(u, month)
        danger = [a for a in rev["alerts"] if a["level"] == "danger"]
        if danger:
            out.append({"id": u["id"], "name": u["name"], "email": u["email"],
                        "total": rev["total"], "alerts": [a["message"] for a in danger]})
    return out
