"""Generate a realistic synthetic transaction CSV (so the team can start before real data is ready)."""
import random
from datetime import date, timedelta
import pandas as pd

random.seed(42)

MERCHANTS = {
    "Groceries": ["BigBasket", "DMart", "Reliance Fresh", "Zepto", "Blinkit", "More Supermarket"],
    "Food & Dining": ["Zomato", "Swiggy", "Starbucks", "Dominos Pizza", "McDonalds", "Cafe Coffee Day"],
    "Transport": ["Uber", "Ola Cabs", "Pune Metro", "IRCTC", "Indian Oil Petrol", "Rapido"],
    "Utilities": ["MSEDCL Electricity", "Airtel Postpaid", "Jio Recharge", "Mahanagar Gas", "Tata Sky DTH"],
    "Entertainment": ["Netflix", "Spotify", "BookMyShow", "Hotstar", "PVR Cinemas", "Steam Games"],
    "Shopping": ["Amazon", "Flipkart", "Myntra", "Decathlon", "Croma", "Ajio"],
    "Health": ["Apollo Pharmacy", "PharmEasy", "Practo Consult", "Cult Fit"],
    "Education": ["Udemy", "Coursera", "Campus Bookstore", "Xerox Print Shop"],
}
AMOUNT = {
    "Groceries": (650, 250), "Food & Dining": (320, 140), "Transport": (180, 90),
    "Utilities": (900, 350), "Entertainment": (350, 150), "Shopping": (1400, 700),
    "Health": (500, 250), "Education": (700, 300),
}
WEIGHTS = {"Groceries": 5, "Food & Dining": 8, "Transport": 7, "Utilities": 1,
           "Entertainment": 2, "Shopping": 2, "Health": 1, "Education": 1}
MODES = ["UPI", "UPI", "UPI", "Card", "Cash", "NetBanking"]


def messy(name: str) -> str:
    """Mimic noisy bank-statement descriptions."""
    prefix = random.choice(["UPI/", "POS ", "", "NEFT-", "UPI-"])
    suffix = random.choice(["", f" {random.randint(1000, 99999)}", " PVT LTD", "*MUM", " IN"])
    n = name.upper() if random.random() < 0.5 else name
    return f"{prefix}{n}{suffix}"


def generate(months: int = 18, out: str = "data/sample_transactions.csv") -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=30 * months)
    rows, d = [], start
    cats, w = list(WEIGHTS), list(WEIGHTS.values())
    while d <= end:
        n = random.choices([0, 1, 2, 3, 4], weights=[1, 3, 4, 2, 1])[0]
        if d.weekday() >= 5:
            n += 1
        for _ in range(n):
            cat = random.choices(cats, weights=w)[0]
            mu, sd = AMOUNT[cat]
            amt = max(20, random.gauss(mu, sd))
            rows.append([d.isoformat(), messy(random.choice(MERCHANTS[cat])), round(amt, 2),
                         random.choice(MODES), cat])
        if d.day == 1:
            rows.append([d.isoformat(), "UPI/Rent Landlord", 8000.0, "UPI", "Rent"])
        d += timedelta(days=1)
    df = pd.DataFrame(rows, columns=["date", "description", "amount", "payment_mode", "category"])
    idx = df.sample(8, random_state=1).index          # inject anomalies
    df.loc[idx, "amount"] = df.loc[idx, "amount"] * random.choice([8, 10, 12])
    df.loc[df.sample(15, random_state=2).index, "payment_mode"] = None   # missing values
    df = pd.concat([df, df.sample(10, random_state=3)], ignore_index=True)  # duplicates
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} rows -> {out}")
    return df


if __name__ == "__main__":
    generate()
