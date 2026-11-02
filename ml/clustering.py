"""Module 6: Spending clusters (K-Means on monthly category shares) + budget recommendations."""
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from ml.features import category_ratios

TIPS = {
    "Food & Dining": "Eating out is a big share - try cooking more or set a weekly dining cap.",
    "Shopping": "Shopping dominates - use a 48-hour wait rule for non-essentials.",
    "Entertainment": "Entertainment is high - audit subscriptions you rarely use.",
    "Transport": "Transport is high - consider a monthly pass or ride-sharing.",
    "Groceries": "Groceries are your top spend - plan weekly lists and buy staples in bulk.",
}


def cluster_months(df: pd.DataFrame, k: int = 3) -> dict:
    ratios = category_ratios(df)
    k = max(1, min(k, len(ratios)))
    if len(ratios) < 2:
        return {"months": [], "clusters": []}
    X = StandardScaler().fit_transform(ratios)
    ratios["cluster"] = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(X)
    clusters = []
    for c, grp in ratios.groupby("cluster"):
        mean_share = grp.drop(columns="cluster").mean().sort_values(ascending=False)
        top = mean_share.index[0]
        clusters.append({
            "cluster": int(c), "months": list(grp.index),
            "top_category": top, "top_share_%": round(float(mean_share.iloc[0]) * 100, 1),
            "tip": TIPS.get(top, f"{top} is your largest category - set a monthly limit for it."),
        })
    return {"months": [{"month": m, "cluster": int(c)} for m, c in ratios["cluster"].items()],
            "clusters": clusters}
