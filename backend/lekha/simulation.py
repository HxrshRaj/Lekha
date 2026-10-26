"""Monte Carlo simulations (fixed seeds, explicit run counts, convergence tables).

1. 90-day cash collection on today's open receivables (bootstrapped customer payment behaviour,
   conditioned on the invoice already being unpaid at the as-of date).
2. Safety stock / stockout probability for a few materials from simulated demand-during-lead-time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import kpis

CHECKPOINTS = [100, 250, 500, 1000, 2500, 5000, 10000, 20000]


def _convergence(vals: np.ndarray, checkpoints=CHECKPOINTS) -> list[dict]:
    out = []
    for n in checkpoints:
        if n > len(vals):
            break
        v = vals[:n]
        out.append({"runs": n, "mean": float(v.mean()), "std_error": float(v.std(ddof=1) / np.sqrt(n)),
                    "p5": float(np.percentile(v, 5)), "p50": float(np.percentile(v, 50)), "p95": float(np.percentile(v, 95))})
    return out


def cash_collection(t: dict[str, pd.DataFrame], as_of: pd.Timestamp, runs: int = 5000, seed: int = 7, horizon_days: int = 90) -> dict:
    rng = np.random.default_rng(seed)
    open_inv = kpis.ar_open(t, as_of).copy()
    open_inv["age"] = (as_of - open_inv["FKDAT"]).dt.days
    paid = t["VBRK"].merge(t["BSAD"][["VBELN_VF", "AUGDT"]], on="VBELN_VF")
    paid["dtp"] = (paid["AUGDT"] - paid["FKDAT"]).dt.days
    # customer history; fall back to the customer's region pool when fewer than 15 paid invoices
    reg = t["KNA1"].set_index("KUNNR")["REGION"]
    paid["REGION"] = paid["KUNNR"].map(reg)
    pool_region = {r: np.sort(g["dtp"].to_numpy()) for r, g in paid.groupby("REGION")}
    pool_cust = {c: np.sort(g["dtp"].to_numpy()) for c, g in paid.groupby("KUNNR") if len(g) >= 15}
    # p(never pays): share of invoices issued 150-400 days before as-of that are still open (defaulters + lost payment records)
    old = t["VBRK"][(as_of - t["VBRK"]["FKDAT"]).dt.days.between(150, 400)]
    p_default = float(old["VBELN_VF"].isin(open_inv["VBELN_VF"]).mean())
    # common (systemic) payment-speed shock per run: sd of monthly mean delay across history
    paid["delay"] = paid["dtp"] - paid["KUNNR"].map(t["KNA1"].set_index("KUNNR")["ZTERM_DAYS"])
    shock_sd = float(paid.groupby(paid["FKDAT"].dt.to_period("M"))["delay"].mean().std())
    shock = rng.normal(0, shock_sd, runs)
    nweeks = int(np.ceil(horizon_days / 7))
    weekly = np.zeros((runs, nweeks))
    total = np.zeros(runs)
    never = 0
    for cust, g in open_inv.groupby("KUNNR"):
        hist = pool_cust.get(cust, pool_region[reg[cust]])
        age = g["age"].to_numpy()
        # conditional sampling: u ~ U(F(age), 1) then empirical quantile
        lo = np.searchsorted(hist, age, side="right") / len(hist)  # F(age) = P(dtp <= age)
        possible = lo < 1.0
        never += int((~possible).sum())
        u = lo[None, :] + rng.random((runs, len(g))) * (1.0 - lo[None, :])
        q = hist[np.minimum((u * len(hist)).astype(int), len(hist) - 1)]
        days_from_asof = q - age[None, :] + shock[:, None]  # when it pays, relative to as-of date
        pays = possible[None, :] & (rng.random((runs, len(g))) >= p_default)
        amt = g["NETWR"].to_numpy()[None, :] * pays
        in_h = (days_from_asof <= horizon_days) & (days_from_asof > 0)
        total += (amt * in_h).sum(axis=1)
        wk = np.clip((days_from_asof - 1) // 7, 0, nweeks - 1).astype(int)
        for w in range(nweeks):
            weekly[:, w] += (amt * (in_h & (wk == w))).sum(axis=1)
    open_total = float(open_inv["NETWR"].sum())
    return {
        "seed": seed, "runs": runs, "horizon_days": horizon_days, "open_invoices": int(len(open_inv)), "open_ar": open_total,
        "invoices_with_no_possible_payment": never, "p_default_estimate": p_default, "systemic_shock_sd_days": shock_sd,
        "total_cash_in": {"mean": float(total.mean()), "p5": float(np.percentile(total, 5)), "p50": float(np.percentile(total, 50)),
                          "p95": float(np.percentile(total, 95)), "pct_of_open_ar_p50": float(100 * np.percentile(total, 50) / open_total)},
        "weekly": [{"week": w + 1, "p5": float(np.percentile(weekly[:, w], 5)), "p50": float(np.percentile(weekly[:, w], 50)),
                    "p95": float(np.percentile(weekly[:, w], 95))} for w in range(nweeks)],
        "convergence": _convergence(total, [c for c in CHECKPOINTS if c <= runs]),
        "caveat": "Only invoices already open at the as-of date; payment behaviour bootstrapped from paid history, so "
                  "never-paying customers (absent from paid history) make this optimistic.",
    }


def safety_stock(t: dict[str, pd.DataFrame], as_of: pd.Timestamp, n_materials: int = 5, runs: int = 20000, seed: int = 11,
                 service_level: float = 0.95) -> dict:
    rng = np.random.default_rng(seed)
    z = float(__import__("scipy.stats", fromlist=["norm"]).norm.ppf(service_level))
    lines = t["EKPO"].merge(t["EKKO"][["EBELN", "BEDAT"]], on="EBELN").merge(t["EKBE"][["EBELN", "EBELP", "BUDAT"]], on=["EBELN", "EBELP"])
    lines["lead"] = (lines["BUDAT"] - lines["BEDAT"]).dt.days
    sales = t["VBAP"].merge(t["VBAK"][["VBELN", "AUDAT"]], on="VBELN")
    days = pd.date_range("2023-01-01", as_of, freq="D")
    cand = lines.groupby("MATNR").size()
    dem_tot = sales.groupby("MATNR")["KWMENG"].sum()
    score = pd.concat([cand.rename("po"), dem_tot.rename("dem")], axis=1).dropna()
    score = score[score["po"] >= 30].sort_values("dem", ascending=False)
    score = score.iloc[np.unique(np.linspace(0, len(score) - 1, n_materials + 2)[:-2].astype(int))]  # spread across demand ranks
    out = []
    for m in score.index:
        daily = sales[sales["MATNR"] == m].groupby("AUDAT")["KWMENG"].sum().reindex(days, fill_value=0).to_numpy().astype(float)
        lead = lines.loc[lines["MATNR"] == m, "lead"].to_numpy()
        L = rng.choice(lead, size=runs)  # bootstrap lead times
        ddlt = np.empty(runs)
        for i, l in enumerate(L):
            ddlt[i] = rng.choice(daily, size=int(l)).sum()  # bootstrap daily demand over the lead time
        d_mu, d_sd, l_mu, l_sd = daily.mean(), daily.std(ddof=1), lead.mean(), lead.std(ddof=1)
        analytic_ss = z * np.sqrt(l_mu * d_sd ** 2 + d_mu ** 2 * l_sd ** 2)
        rop_analytic = d_mu * l_mu + analytic_ss
        sim_rop = float(np.percentile(ddlt, 100 * service_level))
        sim_ss = sim_rop - float(ddlt.mean())
        p_stockout_at_analytic = float((ddlt > rop_analytic).mean())
        # convergence of the stockout-probability estimate
        conv = []
        for n in [c for c in CHECKPOINTS if c <= runs]:
            p = float((ddlt[:n] > rop_analytic).mean())
            conv.append({"runs": n, "p_stockout": p, "std_error": float(np.sqrt(p * (1 - p) / n))})
        out.append({"material": m, "po_lead_observations": int(len(lead)), "daily_demand_mean": float(d_mu), "daily_demand_sd": float(d_sd),
                    "lead_time_mean_days": float(l_mu), "lead_time_sd_days": float(l_sd),
                    "safety_stock_analytic": float(analytic_ss), "safety_stock_simulated": float(sim_ss),
                    "reorder_point_analytic": float(rop_analytic), "reorder_point_simulated": sim_rop,
                    "stockout_prob_at_analytic_rop": p_stockout_at_analytic, "convergence": conv})
    return {"seed": seed, "runs": runs, "service_level": service_level, "materials": out,
            "method": "Bootstrap lead times from PO/goods-receipt history; bootstrap daily demand over each simulated lead time. "
                      "Analytic = z*sqrt(L*sd_d^2 + d^2*sd_L^2) (normal approx.); simulated = empirical percentile of demand during lead time."}
