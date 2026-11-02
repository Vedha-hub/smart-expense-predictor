"""Optional LSTM forecaster (pip install tensorflow). Recursive multi-step prediction."""
import numpy as np
import pandas as pd


def lstm_forecast(s: pd.Series, horizon: int, window: int = 14, epochs: int = 30) -> pd.Series:
    import tensorflow as tf
    from tensorflow.keras import layers, models

    vals = s.values.astype("float32").reshape(-1, 1)
    lo, hi = vals.min(), vals.max()
    scaled = (vals - lo) / max(hi - lo, 1e-6)

    X = np.array([scaled[i:i + window] for i in range(len(scaled) - window)])
    y = np.array([scaled[i + window] for i in range(len(scaled) - window)])
    model = models.Sequential([layers.Input((window, 1)), layers.LSTM(32), layers.Dense(1)])
    model.compile(optimizer="adam", loss="mse")
    model.fit(X, y, epochs=epochs, batch_size=16, verbose=0, shuffle=False)

    buf, preds = scaled[-window:].copy(), []
    for _ in range(horizon):
        p = model.predict(buf.reshape(1, window, 1), verbose=0)[0, 0]
        preds.append(p)
        buf = np.vstack([buf[1:], [[p]]])
    out = np.clip(np.array(preds) * (hi - lo) + lo, 0, None)
    idx = pd.date_range(s.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    return pd.Series(out, index=idx)
