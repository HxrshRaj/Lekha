"""Days-to-pay regression: OLS (statsmodels, for interpretation) + gradient boosting (ML).
Time-based holdout: train on invoices issued 2023-2024, test on 2025-01..2025-09 (later months are
right-censored because many invoices are not yet paid at the as-of date)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

TRAIN_END = pd.Timestamp("2024-12-31")
TEST_END = pd.Timestamp("2025-09-30")
FEATURES = ["log_amount", "terms", "region", "dispute", "q4", "prior_dtp"]


def build_dataset(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    d = t["VBRK"].merge(t["BSAD"][["VBELN_VF", "AUGDT"]], on="VBELN_VF").merge(
        t["KNA1"][["KUNNR", "REGION", "ZTERM_DAYS"]], on="KUNNR")
    d["dtp"] = (d["AUGDT"] - d["FKDAT"]).dt.days
    d["log_amount"] = np.log10(d["NETWR"].clip(lower=10))
    d["terms"] = d["ZTERM_DAYS"]
    d["region"] = d["REGION"]
    d["dispute"] = d["VBELN_VF"].isin(t["TICKETS"]["VBELN_VF"]).astype(int)
    d["q4"] = d["FKDAT"].dt.month.isin([11, 12]).astype(int)
    # prior_dtp: mean days-to-pay of this customer's invoices that were ALREADY paid before this invoice was issued (no leakage)
    d["prior_dtp"] = np.nan
    for _, g in d.groupby("KUNNR"):
        paid = g.sort_values("AUGDT")
        cum = paid["dtp"].cumsum().to_numpy() / np.arange(1, len(paid) + 1)
        idx = np.searchsorted(paid["AUGDT"].to_numpy(), g["FKDAT"].to_numpy(), side="left") - 1
        d.loc[g.index, "prior_dtp"] = np.where(idx >= 0, cum[np.clip(idx, 0, None)], np.nan)
    return d


def run(t: dict[str, pd.DataFrame], seed: int = 42) -> dict:
    d = build_dataset(t)
    train = d[d["FKDAT"] <= TRAIN_END].copy()
    test = d[(d["FKDAT"] > TRAIN_END) & (d["FKDAT"] <= TEST_END)].copy()
    fill = float(train["prior_dtp"].mean())
    for df in (train, test):
        df["prior_dtp"] = df["prior_dtp"].fillna(fill)

    formula = "dtp ~ log_amount + terms + C(region, Treatment('EMEA')) + dispute + q4 + prior_dtp"
    ols = smf.ols(formula, data=train).fit()
    ci = ols.conf_int()
    coefs = [{"term": k.replace("C(region, Treatment('EMEA'))[T.", "region_").replace("]", ""), "coef": float(v),
              "p_value": float(ols.pvalues[k]), "ci_low": float(ci.loc[k, 0]), "ci_high": float(ci.loc[k, 1])}
             for k, v in ols.params.items()]

    X = lambda df: pd.get_dummies(df[FEATURES], columns=["region"], dtype=float)
    Xtr, Xte = X(train), X(test).reindex(columns=X(train).columns, fill_value=0.0)
    gbm = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, random_state=seed).fit(Xtr, train["dtp"])

    pred = {"baseline_terms": test["terms"].to_numpy().astype(float),
            "baseline_train_mean": np.full(len(test), train["dtp"].mean()),
            "ols": ols.predict(test).to_numpy(), "gbm": gbm.predict(Xte)}
    ytest = test["dtp"].to_numpy()

    def metrics(p, y=ytest):
        return {"mae": float(mean_absolute_error(y, p)), "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}

    hold = {k: metrics(v) for k, v in pred.items()}
    # where it does not generalise: error by region and by period
    seg = test.assign(ols=pred["ols"], err_ols=pred["ols"] - ytest, err_gbm=pred["gbm"] - ytest)
    seg["period"] = np.where(seg["FKDAT"] >= pd.Timestamp("2025-07-01"), "2025-07..09", "2025-01..06")
    breakdown = []
    for (reg, per), g in seg.groupby(["region", "period"]):
        breakdown.append({"region": reg, "period": per, "n": int(len(g)), "mean_actual": float(g["dtp"].mean()),
                          "ols_bias": float(g["err_ols"].mean()), "ols_mae": float(g["err_ols"].abs().mean()),
                          "gbm_bias": float(g["err_gbm"].mean()), "gbm_mae": float(g["err_gbm"].abs().mean())})
    return {
        "target": "days_to_pay = payment date - invoice date (paid invoices only)",
        "n_train": int(len(train)), "n_test": int(len(test)),
        "train_window": "invoices issued 2023-01..2024-12", "test_window": "invoices issued 2025-01..2025-09",
        "ols": {"r2": float(ols.rsquared), "adj_r2": float(ols.rsquared_adj), "f_pvalue": float(ols.f_pvalue), "coefficients": coefs},
        "holdout": hold, "holdout_breakdown": breakdown,
        "note": "Test window includes a synthetic regime change (APAC customers pay ~6 days later from 2025-07); "
                "models trained on 2023-24 do not know about it, so APAC 2025-07..09 is biased low.",
    }
