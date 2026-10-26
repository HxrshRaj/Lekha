"""Weekly forecasting with rolling-origin backtests: naive baselines vs ETS vs gradient boosting."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from statsmodels.tsa.holtwinters import ExponentialSmoothing

HORIZON = 4
MIN_TRAIN = 104  # two full years
STEP = 4


def weekly_series(t: dict[str, pd.DataFrame]) -> dict[str, pd.Series]:
    """Weeks end on Sunday; incomplete first/last weeks are dropped."""
    demand = t["VBAK"][["VBELN", "AUDAT"]].merge(t["VBAP"][["VBELN", "KWMENG"]], on="VBELN").set_index("AUDAT")["KWMENG"]
    cash = t["BSAD"].set_index("AUGDT")["DMBTR"]
    out = {}
    for name, s in (("demand_units", demand), ("cash_in_usd", cash)):
        w = s.resample("W-SUN").sum().iloc[1:-1]
        out[name] = w.astype(float)
    return out


def wape(y, f) -> float:
    return float(np.abs(y - f).sum() / np.abs(y).sum())


def mape(y, f) -> float:
    m = y != 0
    return float(np.mean(np.abs((y[m] - f[m]) / y[m])))


def _feat(y: np.ndarray, origin: int, h: int, dates: pd.DatetimeIndex) -> list[float]:
    """Features known at `origin` (last observed index) for target index origin+h."""
    tgt = origin + h
    woy = (dates[0] + pd.Timedelta(weeks=tgt)).isocalendar().week
    return [y[origin], y[origin - 1], y[origin - 2], y[origin - 3], y[origin - 3:origin + 1].mean(), y[tgt - 52],
            np.sin(2 * np.pi * woy / 52), np.cos(2 * np.pi * woy / 52)]


def _gbm_forecast(y: np.ndarray, origin: int, dates, seed=0) -> np.ndarray:
    preds = []
    for h in range(1, HORIZON + 1):
        Xs, ys = [], []
        for o in range(55, origin - h + 1):
            Xs.append(_feat(y, o, h, dates))
            ys.append(y[o + h])
        m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150, random_state=seed).fit(np.array(Xs), np.array(ys))
        preds.append(float(m.predict(np.array([_feat(y, origin, h, dates)]))[0]))
    return np.array(preds)


def _forecast(model: str, y: np.ndarray, origin: int, dates) -> np.ndarray:
    hist = y[: origin + 1]
    if model == "naive":
        return np.repeat(hist[-1], HORIZON)
    if model == "seasonal_naive":
        return np.array([hist[len(hist) - 52 + h] for h in range(HORIZON)])
    if model == "moving_avg_4":
        return np.repeat(hist[-4:].mean(), HORIZON)
    if model == "ets":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(hist, trend="add", damped_trend=True, seasonal="add", seasonal_periods=52,
                                       initialization_method="estimated").fit()
        return np.maximum(fit.forecast(HORIZON), 0)
    if model == "gbm":
        return np.maximum(_gbm_forecast(y, origin, dates), 0)
    raise ValueError(model)


MODELS = ["naive", "seasonal_naive", "moving_avg_4", "ets", "gbm"]


def backtest(s: pd.Series) -> dict:
    y = s.to_numpy()
    origins = list(range(MIN_TRAIN - 1, len(y) - HORIZON, STEP))
    rows = {m: ([], []) for m in MODELS}
    for o in origins:
        actual = y[o + 1:o + 1 + HORIZON]
        for m in MODELS:
            rows[m][0].append(actual)
            rows[m][1].append(_forecast(m, y, o, s.index))
    res = []
    for m in MODELS:
        a, f = np.concatenate(rows[m][0]), np.concatenate(rows[m][1])
        res.append({"model": m, "wape": wape(a, f), "mape": mape(a, f), "bias": float((f - a).sum() / a.sum())})
    res.sort(key=lambda r: r["wape"])
    return {"n_weeks": int(len(y)), "folds": len(origins), "horizon_weeks": HORIZON, "min_train_weeks": MIN_TRAIN, "models": res,
            "best": res[0]["model"], "beats_naive": res[0]["model"] not in ("naive",), "naive_wape": next(r["wape"] for r in res if r["model"] == "naive")}


def future(s: pd.Series, model: str, weeks: int = 13) -> pd.DataFrame:
    """Recursive-free multi-step future (>HORIZON) for the chosen model: refit and extend in blocks of HORIZON."""
    y = list(s.to_numpy())
    idx = list(s.index)
    out = []
    for _ in range(int(np.ceil(weeks / HORIZON))):
        arr = np.array(y)
        dates = pd.DatetimeIndex(idx)
        f = _forecast(model, arr, len(arr) - 1, dates)
        for v in f:
            idx.append(idx[-1] + pd.Timedelta(weeks=1))
            y.append(float(v))
            out.append((idx[-1], float(v)))
    return pd.DataFrame(out[:weeks], columns=["week_end", "forecast"])
