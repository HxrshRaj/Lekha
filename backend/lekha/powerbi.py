"""Star-schema CSV export for Power BI: python -m lekha.powerbi [--out ../powerbi/data]
Power BI was NOT used to build or validate anything in this repo; these files + powerbi/measures.dax are 'ready to import'."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from . import kpis
from .tables import AS_OF, build


def star(t: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    days = pd.date_range("2023-01-01", "2025-12-31", freq="D")
    dim_date = pd.DataFrame({"DateKey": days.strftime("%Y%m%d").astype(int), "Date": days, "Year": days.year, "Quarter": days.quarter,
                             "Month": days.month, "MonthName": days.strftime("%b"), "YearMonth": (days.year * 100 + days.month),
                             "WeekEnding": (days + pd.to_timedelta((6 - days.dayofweek) % 7, "D"))})
    dim_customer = t["KNA1"][["KUNNR", "NAME1", "LAND1", "REGION", "ZTERM_DAYS", "CREDIT_LIMIT"]]
    dim_material = t["MARA"][["MATNR", "MAKTX", "BASE_MATNR", "CONF_CODE", "STD_COST", "PRICE", "LEAD_DAYS"]]
    dim_cc = t["CSKS"]
    dim_acct = t["SKA1"]
    open_ids = set(kpis.ar_open(t, AS_OF)["VBELN_VF"])
    inv = t["VBRK"].merge(t["BSAD"][["VBELN_VF", "AUGDT", "DMBTR"]], on="VBELN_VF", how="left")
    inv["DaysToPay"] = (inv["AUGDT"] - inv["FKDAT"]).dt.days
    inv["IsOpen"] = inv["VBELN_VF"].isin(open_ids).astype(int)
    ob = kpis.ar_open(t, AS_OF).set_index("VBELN_VF")
    inv["DaysOverdue"] = inv["VBELN_VF"].map(ob["DaysOverdue"])
    inv["Bucket"] = inv["VBELN_VF"].map(ob["Bucket"])
    inv["InvoiceDateKey"] = inv["FKDAT"].dt.strftime("%Y%m%d").astype(int)
    inv["DueDateKey"] = inv["FAEDT"].dt.strftime("%Y%m%d").astype(int)
    inv["PaidDateKey"] = inv["AUGDT"].dt.strftime("%Y%m%d").astype("Int64").where(inv["AUGDT"].notna())
    fact_inv = inv[["VBELN_VF", "VBELN", "KUNNR", "InvoiceDateKey", "DueDateKey", "PaidDateKey", "NETWR", "DMBTR", "DaysToPay", "IsOpen", "DaysOverdue", "Bucket"]]
    o = kpis.otif_order(t)
    fact_otif = o[["VBELN", "AUDAT", "LFDAT", "WADAT_IST", "QtyOrd", "QtyDel", "OnTime", "InFull"]].merge(t["VBAK"][["VBELN", "KUNNR"]], on="VBELN")
    fact_otif["OTIF"] = fact_otif["OnTime"] * fact_otif["InFull"]
    fact_gl = t["BSEG"].merge(t["BKPF"][["BELNR", "BUDAT", "BLART"]], on="BELNR")
    fact_gl["DateKey"] = fact_gl["BUDAT"].dt.strftime("%Y%m%d").astype(int)
    fact_gl["SignedAmount"] = np.where(fact_gl["SHKZG"] == "S", fact_gl["DMBTR"], -fact_gl["DMBTR"])
    fact_gl = fact_gl[["BELNR", "BUZEI", "DateKey", "PERIOD", "HKONT", "KOSTL", "SHKZG", "DMBTR", "SignedAmount", "BLART"]]
    budget = t["BUDG"].copy()
    budget["DateKey"] = budget["PERIOD"].map(lambda p: pd.Period(f"{p // 100}-{p % 100:02d}").end_time.strftime("%Y%m%d")).astype(int)
    return {"dim_date": dim_date, "dim_customer": dim_customer, "dim_material": dim_material, "dim_cost_centre": dim_cc,
            "dim_account": dim_acct, "fact_invoice": fact_inv, "fact_otif_order": fact_otif, "fact_gl": fact_gl,
            "fact_budget": budget}


def main(out: Path, scale: float) -> None:
    t = build(42, scale)[0]
    out.mkdir(parents=True, exist_ok=True)
    for name, df in star(t).items():
        df.to_csv(out / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"{name}: {len(df):,} rows")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "powerbi" / "data"))
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    main(Path(a.out), a.scale)
