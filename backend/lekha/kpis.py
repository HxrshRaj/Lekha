"""Pandas implementation of every KPI that also exists as a T-SQL view (sql/03_views.sql).

Definitions (all on CLEANED data, as-of date = Params.AsOfDate):
- Open receivable: invoice with FKDAT <= as_of and no payment with AUGDT <= as_of.
- Aging bucket by days past due date (FAEDT): Current (not yet due), 0-30, 31-60, 61-90, 90+.
- DSO (month end M) = open AR at M / credit sales invoiced in (M-90d, M] * 90.
- OTIF (per order with a delivery) = goods issue <= planned date AND total delivered qty >= total ordered qty.
- Order-to-cash = payment date - order date, for paid invoices; also its three legs.
- Variance = actual opex - budget per cost centre and period; YTD = running sum within the calendar year.
- P&L from GL: revenue (acct group REV, credits - debits), COGS, OPEX (debits - credits).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BUCKETS = ["Current", "0-30", "31-60", "61-90", "90+"]


def bucket(days_overdue: pd.Series, due: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    d = days_overdue
    out = np.select([due > as_of, d <= 30, d <= 60, d <= 90], ["Current", "0-30", "31-60", "61-90"], default="90+")
    return pd.Series(out, index=d.index)


def ar_open(t: dict[str, pd.DataFrame], as_of: pd.Timestamp) -> pd.DataFrame:
    v = t["VBRK"].merge(t["KNA1"][["KUNNR", "REGION"]], on="KUNNR")
    v = v[v["FKDAT"] <= as_of]
    paid = t["BSAD"][t["BSAD"]["AUGDT"] <= as_of]["VBELN_VF"]
    v = v[~v["VBELN_VF"].isin(paid)].copy()
    v["DaysOverdue"] = (as_of - v["FAEDT"]).dt.days
    v["Bucket"] = bucket(v["DaysOverdue"], v["FAEDT"], as_of)
    return v


def ar_aging(t, as_of) -> pd.DataFrame:
    o = ar_open(t, as_of)
    g = o.groupby("Bucket").agg(Invoices=("NETWR", "size"), Amount=("NETWR", "sum")).reindex(BUCKETS).dropna().reset_index()
    g["PctOfOpen"] = (100 * g["Amount"] / g["Amount"].sum()).round(2)
    return g


def ap_aging(t, as_of) -> pd.DataFrame:
    r = t["RBKP"]
    r = r[(r["BLDAT"] <= as_of) & (r["AUGDT"].isna() | (r["AUGDT"] > as_of))].copy()
    d = (as_of - r["FAEDT"]).dt.days
    r["Bucket"] = bucket(d, r["FAEDT"], as_of)
    return r.groupby("Bucket").agg(Invoices=("RMWWR", "size"), Amount=("RMWWR", "sum")).reindex(BUCKETS).dropna().reset_index()


def dso_monthly(t, as_of=None) -> pd.DataFrame:
    v, b = t["VBRK"], t["BSAD"][["VBELN_VF", "AUGDT"]]
    vv = v.merge(b, on="VBELN_VF", how="left")
    rows = []
    for me in sorted(v["FKDAT"].dt.to_period("M").unique()):
        end = me.to_timestamp(how="end").normalize()
        issued = vv[vv["FKDAT"] <= end]
        open_ar = issued[issued["AUGDT"].isna() | (issued["AUGDT"] > end)]["NETWR"].sum()
        s90 = v[(v["FKDAT"] > end - pd.Timedelta(days=90)) & (v["FKDAT"] <= end)]["NETWR"].sum()
        rows.append((end, open_ar, s90, round(open_ar * 90.0 / s90, 2) if s90 else np.nan))
    return pd.DataFrame(rows, columns=["MonthEnd", "OpenAR", "Sales90", "DSO"])


def otif_order(t) -> pd.DataFrame:
    ordq = t["VBAP"].groupby("VBELN")["KWMENG"].sum().rename("QtyOrd")
    dl = t["LIKP"].merge(t["LIPS"], on="VBELN_VL").groupby("VBELN")["LFIMG"].sum().rename("QtyDel")
    o = t["VBAK"][["VBELN", "AUDAT"]].merge(t["LIKP"][["VBELN", "LFDAT", "WADAT_IST"]], on="VBELN")
    o = o.merge(ordq, on="VBELN").merge(dl, on="VBELN")
    o["OnTime"] = (o["WADAT_IST"] <= o["LFDAT"]).astype(int)
    o["InFull"] = (o["QtyDel"] >= o["QtyOrd"]).astype(int)
    o["OrderMonth"] = o["AUDAT"].dt.to_period("M").dt.to_timestamp(how="end").dt.normalize()
    return o


def otif_monthly(t) -> pd.DataFrame:
    o = otif_order(t)
    g = o.groupby("OrderMonth").agg(Orders=("VBELN", "size"), OnTimePct=("OnTime", "mean"), InFullPct=("InFull", "mean")).reset_index()
    g["OTIFPct"] = o.assign(x=o["OnTime"] * o["InFull"]).groupby("OrderMonth")["x"].mean().to_numpy()
    for c in ("OnTimePct", "InFullPct", "OTIFPct"):
        g[c] = (100 * g[c]).round(2)
    return g


def cycle_order(t) -> pd.DataFrame:
    x = t["VBRK"][["VBELN_VF", "VBELN", "FKDAT"]].merge(t["VBAK"][["VBELN", "AUDAT"]], on="VBELN")
    x = x.merge(t["LIKP"][["VBELN", "WADAT_IST"]], on="VBELN").merge(t["BSAD"][["VBELN_VF", "AUGDT"]], on="VBELN_VF")
    x["OrderToDelivery"] = (x["WADAT_IST"] - x["AUDAT"]).dt.days
    x["DeliveryToInvoice"] = (x["FKDAT"] - x["WADAT_IST"]).dt.days
    x["InvoiceToCash"] = (x["AUGDT"] - x["FKDAT"]).dt.days
    x["OrderToCash"] = (x["AUGDT"] - x["AUDAT"]).dt.days
    x["OrderMonth"] = x["AUDAT"].dt.to_period("M").dt.to_timestamp(how="end").dt.normalize()
    return x


def cycle_monthly(t) -> pd.DataFrame:
    x = cycle_order(t)
    g = x.groupby("OrderMonth").agg(PaidOrders=("VBELN_VF", "size"), AvgOrderToDelivery=("OrderToDelivery", "mean"),
                                    AvgDeliveryToInvoice=("DeliveryToInvoice", "mean"), AvgInvoiceToCash=("InvoiceToCash", "mean"),
                                    AvgOrderToCash=("OrderToCash", "mean"), MedianOrderToCash=("OrderToCash", "median")).reset_index()
    return g


def _gl(t) -> pd.DataFrame:
    g = t["BSEG"].merge(t["SKA1"][["HKONT", "GRP"]], on="HKONT")
    g["Signed"] = np.where(g["SHKZG"] == "S", g["DMBTR"], -g["DMBTR"])  # debit positive
    return g


def budget_variance(t) -> pd.DataFrame:
    g = _gl(t)
    act = g[(g["GRP"] == "OPEX") & g["KOSTL"].notna()].groupby(["KOSTL", "PERIOD"])["Signed"].sum().rename("Actual").reset_index()
    j = t["BUDG"].rename(columns={"AMT_BUDGET": "Budget"}).merge(act, on=["KOSTL", "PERIOD"], how="left")
    j["Actual"] = j["Actual"].fillna(0.0)
    j = j.sort_values(["KOSTL", "PERIOD"]).reset_index(drop=True)
    j["Variance"] = j["Actual"] - j["Budget"]
    j["VariancePct"] = (100.0 * j["Variance"] / j["Budget"].replace(0, np.nan)).round(2)
    yr = j["PERIOD"] // 100
    j["YtdActual"] = j.groupby(["KOSTL", yr])["Actual"].cumsum()
    j["YtdBudget"] = j.groupby(["KOSTL", yr])["Budget"].cumsum()
    return j


def pnl_period(t) -> pd.DataFrame:
    g = _gl(t)
    p = pd.DataFrame({
        "Revenue": -g[g["GRP"] == "REV"].groupby("PERIOD")["Signed"].sum(),
        "Cogs": g[g["GRP"] == "COGS"].groupby("PERIOD")["Signed"].sum(),
        "Opex": g[g["GRP"] == "OPEX"].groupby("PERIOD")["Signed"].sum()}).fillna(0.0).reset_index()
    p["GrossProfit"] = p["Revenue"] - p["Cogs"]
    p["Ebit"] = p["GrossProfit"] - p["Opex"]
    p["GrossMarginPct"] = (100.0 * p["GrossProfit"] / p["Revenue"].replace(0, np.nan)).round(2)
    return p


def headline(t, as_of: pd.Timestamp) -> dict:
    ag = ar_aging(t, as_of)
    dso = dso_monthly(t)
    ot = otif_order(t)
    cy = cycle_order(t)
    pl = pnl_period(t)
    last12 = pl.tail(12)
    return {
        "as_of": str(as_of.date()),
        "open_ar": float(ag["Amount"].sum()),
        "overdue_90_plus": float(ag.loc[ag["Bucket"] == "90+", "Amount"].sum()),
        "dso_latest": float(dso["DSO"].iloc[-1]),
        "otif_pct": round(100 * float((ot["OnTime"] * ot["InFull"]).mean()), 2),
        "on_time_pct": round(100 * float(ot["OnTime"].mean()), 2),
        "in_full_pct": round(100 * float(ot["InFull"].mean()), 2),
        "avg_order_to_cash_days": round(float(cy["OrderToCash"].mean()), 1),
        "median_order_to_cash_days": float(cy["OrderToCash"].median()),
        "revenue_ltm": float(last12["Revenue"].sum()),
        "ebit_ltm": float(last12["Ebit"].sum()),
        "gross_margin_ltm_pct": round(100 * float(last12["GrossProfit"].sum() / last12["Revenue"].sum()), 2),
    }
