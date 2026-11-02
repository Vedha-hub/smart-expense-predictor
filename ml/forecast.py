"""Module 4: Forecasting. Prophet and LSTM are optional; Holt-Winters is the always-available baseline."""
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def forecast_baseline(s: pd.Series, horizon: int) -> pd.Series:
    """Holt-Winters with weekly seasonality (needs >= 2 weeks of data, else moving average)."""
    idx = pd.date_range(s.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    if len(s) < 21:
        return pd.Series(np.full(horizon, s.tail(7).mean()), index=idx)
    model = ExponentialSmoothing(s.clip(lower=0) + 1e-3, trend=None, seasonal="add",
                                 seasonal_periods=7).fit()
    return pd.Series(np.clip(model.forecast(horizon).values, 0, None), index=idx)


def forecast_prophet(s: pd.Series, horizon: int) -> pd.Series:
    from prophet import Prophet                      # pip install prophet
    df = s.reset_index()
    df.columns = ["ds", "y"]
    m = Prophet(weekly_seasonality=True, yearly_seasonality=len(s) > 365, daily_seasonality=False)
    m.fit(df)
    fut = m.make_future_dataframe(periods=horizon)
    pred = m.predict(fut).tail(horizon)
    return pd.Series(np.clip(pred["yhat"].values, 0, None), index=pd.to_datetime(pred["ds"]))


def forecast_lstm(s: pd.Series, horizon: int, window: int = 14, epochs: int = 30) -> pd.Series:
    from ml.lstm_model import lstm_forecast
    return lstm_forecast(s, horizon, window, epochs)


def forecast(s: pd.Series, horizon: int = 30, method: str = "auto") -> tuple[pd.Series, str]:
    """Returns (forecast series, method actually used)."""
    order = {"auto": ["prophet", "baseline"], "prophet": ["prophet"], "lstm": ["lstm"],
             "baseline": ["baseline"]}[method]
    fns = {"prophet": forecast_prophet, "lstm": forecast_lstm, "baseline": forecast_baseline}
    for name in order:
        try:
            return fns[name](s, horizon), name
        except Exception as e:                          # library missing / too little data
            print(f"[forecast] {name} failed ({e}); trying next")
    return forecast_baseline(s, horizon), "baseline"


def evaluate(s: pd.Series, holdout: int = 30, method: str = "baseline") -> dict:
    """Train on all but the last `holdout` days and measure error (use this in your report!)."""
    train, test = s.iloc[:-holdout], s.iloc[-holdout:]
    pred, used = forecast(train, holdout, method)
    mae = float(np.mean(np.abs(test.values - pred.values)))
    wape = float(np.sum(np.abs(test.values - pred.values)) / max(test.sum(), 1e-9) * 100)
    return {"method": used, "MAE": round(mae, 2), "WAPE_%": round(wape, 2)}


def evaluate_weekly(s: pd.Series, weeks: int = 4, method: str = "baseline") -> dict:
    """Daily spend is very noisy; judge the model on weekly totals too (more meaningful for budgeting)."""
    holdout = weeks * 7
    train, test = s.iloc[:-holdout], s.iloc[-holdout:]
    pred, used = forecast(train, holdout, method)
    a = test.values.reshape(weeks, 7).sum(axis=1)
    p = pred.values.reshape(weeks, 7).sum(axis=1)
    return {"method": used, "weekly_WAPE_%": round(float(np.abs(a - p).sum() / a.sum() * 100), 2)}
