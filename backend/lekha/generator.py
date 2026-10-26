"""Seeded generator for SAP-style (simplified, SYNTHETIC) order-to-cash / procure-to-pay data.

`generate()` returns clean, typed "truth" tables. `staging.make_staging()` turns them into
string-typed staging tables with ~2% injected data-quality defects.
Nothing here is real SAP data or connected to any SAP system.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .textgen import make_tickets

START = pd.Timestamp("2023-01-01")
END = pd.Timestamp("2025-12-31")
REGION_EFFECT = {"EMEA": 0.0, "AMER": -2.0, "APAC": 3.0}
SHIFT_DATE = pd.Timestamp("2025-07-01")  # regime change: APAC customers start paying later
SHIFT_DAYS = 6.0

GL_ACCOUNTS = {
    100000: ("Bank", "BS"),
    140000: ("Trade receivables", "BS"),
    160000: ("Trade payables", "BS"),
    191100: ("GR/IR clearing", "BS"),
    300000: ("Inventory", "BS"),
    400000: ("Sales revenue", "REV"),
    500000: ("Cost of goods sold", "COGS"),
    600000: ("Salaries", "OPEX"),
    610000: ("Rent and facilities", "OPEX"),
    620000: ("Travel", "OPEX"),
    630000: ("Marketing", "OPEX"),
    640000: ("IT and software", "OPEX"),
}
OPEX_ACCOUNTS = [600000, 610000, 620000, 630000, 640000]


def _id(prefix_len: int, n: int) -> list[str]:
    return [str(i).zfill(prefix_len) for i in n]


def _dates_weighted(rng, n, start, end, growth=0.25):
    days = pd.date_range(start, end, freq="D")
    t = np.arange(len(days)) / len(days)
    month_w = np.array([0.9, 0.9, 1.0, 1.0, 1.0, 1.0, 0.85, 0.85, 1.05, 1.1, 1.2, 1.3])[days.month - 1]
    wd = np.where(days.dayofweek < 5, 1.0, np.where(days.dayofweek == 5, 0.15, 0.05))
    w = month_w * wd * (1 + growth * t)
    w = w / w.sum()
    return days[rng.choice(len(days), size=n, p=w)]


def generate(seed: int = 42, scale: float = 1.0) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n_cust = max(30, int(600 * scale))
    n_vend = max(10, int(150 * scale))
    n_base = max(8, int(40 * scale))
    n_orders = max(300, int(30000 * scale))
    n_po = max(100, int(6000 * scale))

    # ---- master data -----------------------------------------------------------------
    regions = rng.choice(list(REGION_EFFECT), size=n_cust, p=[0.4, 0.35, 0.25])
    terms = rng.choice([30, 45, 60], size=n_cust, p=[0.5, 0.3, 0.2])
    kna1 = pd.DataFrame({
        "KUNNR": _id(10, 100000 + np.arange(n_cust)),
        "NAME1": [f"Customer {i:04d} GmbH" if r == "EMEA" else f"Customer {i:04d} Inc" if r == "AMER" else f"Customer {i:04d} Pte"
                  for i, r in enumerate(regions)],
        "LAND1": [{"EMEA": "DE", "AMER": "US", "APAC": "SG"}[r] for r in regions],
        "REGION": regions, "WAERS": "USD", "ZTERM_DAYS": terms,
        "CREDIT_LIMIT": np.round(rng.lognormal(11.5, 0.6, n_cust), -3),
    })
    cust_bias = np.clip(rng.normal(4.0, 5.0, n_cust), -8, None)
    lfa1 = pd.DataFrame({
        "LIFNR": _id(10, 200000 + np.arange(n_vend)),
        "NAME1": [f"Vendor {i:04d} Supplies" for i in range(n_vend)],
        "LAND1": rng.choice(["DE", "CN", "US", "PL"], n_vend),
        "ZTERM_DAYS": rng.choice([30, 45, 60], n_vend),
    })
    vend_slow = rng.lognormal(0, 0.15, n_vend)

    colours, sizes = ["RED", "BLU", "GRN"], ["S", "M", "L"]
    mrows = []
    for b in range(n_base):
        base = f"B{b + 1:04d}"
        cost = float(np.round(rng.lognormal(3.4, 0.7), 2))
        lead = int(rng.integers(5, 40))
        for c in colours[: int(rng.integers(2, 4))]:
            for s in sizes[: int(rng.integers(1, 4))]:
                price = round(cost * float(rng.uniform(1.25, 1.7)) * (1.03 if s == "L" else 1.0), 2)
                mrows.append((f"{base}-{c}-{s}", f"Product {base} {c} {s}", "FERT", base, f"COLOUR={c};SIZE={s}",
                              cost, price, lead))
    mara = pd.DataFrame(mrows, columns=["MATNR", "MAKTX", "MTART", "BASE_MATNR", "CONF_CODE", "STD_COST", "PRICE", "LEAD_DAYS"])
    n_mat = len(mara)
    mat_w = rng.zipf(1.6, n_mat).astype(float).clip(max=60)
    mat_w /= mat_w.sum()

    csks = pd.DataFrame({"KOSTL": [f"CC{i:03d}" for i in range(1, 21)],
                         "KTEXT": [f"Cost centre {i}" for i in range(1, 21)],
                         "ABTEI": rng.choice(["SALES", "LOGISTICS", "FINANCE", "IT", "ADMIN"], 20)})

    # ---- sales orders ----------------------------------------------------------------
    cust_w = rng.zipf(1.4, n_cust).astype(float).clip(max=40)
    cust_w /= cust_w.sum()
    ci = rng.choice(n_cust, n_orders, p=cust_w)
    audat = _dates_weighted(rng, n_orders, START, END - pd.Timedelta(days=3))
    vbeln = _id(10, 5000000 + np.arange(n_orders))
    order_order = np.argsort(audat, kind="stable")
    audat, ci = audat[order_order], ci[order_order]
    n_lines = np.clip(1 + rng.poisson(1.8, n_orders), 1, 6)
    li_order = np.repeat(np.arange(n_orders), n_lines)
    posnr = np.concatenate([np.arange(1, k + 1) * 10 for k in n_lines])
    mi = rng.choice(n_mat, len(li_order), p=mat_w)
    qty = np.maximum(1, rng.lognormal(1.8, 0.7, len(li_order)).astype(int))
    netpr = np.round(mara["PRICE"].to_numpy()[mi] * rng.uniform(0.9, 1.05, len(li_order)), 2)
    vbap = pd.DataFrame({"VBELN": np.array(vbeln)[li_order], "POSNR": posnr, "MATNR": mara["MATNR"].to_numpy()[mi],
                         "KWMENG": qty, "NETPR": netpr, "NETWR": np.round(qty * netpr, 2)})
    ord_net = vbap.groupby("VBELN")["NETWR"].sum().reindex(vbeln).to_numpy()
    lead_req = rng.integers(3, 11, n_orders)
    vbak = pd.DataFrame({"VBELN": vbeln, "KUNNR": kna1["KUNNR"].to_numpy()[ci], "AUDAT": audat,
                         "VDATU": audat + pd.to_timedelta(lead_req, "D"), "WAERK": "USD", "NETWR": np.round(ord_net, 2)})

    # ---- deliveries ------------------------------------------------------------------
    late = rng.random(n_orders) < (0.16 + 0.07 * (kna1["REGION"].to_numpy()[ci] == "APAC"))
    delay = np.where(late, 1 + rng.geometric(0.4, n_orders), -rng.integers(0, 2, n_orders))
    wadat = vbak["VDATU"] + pd.to_timedelta(delay, "D")
    has_del = (wadat <= END).to_numpy()
    likp_all = pd.DataFrame({"VBELN_VL": _id(10, 8000000 + np.arange(n_orders)), "VBELN": vbeln,
                             "LFDAT": vbak["VDATU"], "WADAT_IST": wadat})
    likp = likp_all[has_del].reset_index(drop=True)
    short = rng.random(len(vbap)) < 0.04
    deliv_qty = np.where(short, np.maximum(1, (vbap["KWMENG"] * rng.uniform(0.5, 0.95, len(vbap))).astype(int)), vbap["KWMENG"])
    deliv_qty = np.minimum(deliv_qty, vbap["KWMENG"].to_numpy())
    vbap_del = vbap.assign(VBELN_VL=vbap["VBELN"].map(dict(zip(likp_all["VBELN"], likp_all["VBELN_VL"]))), LFIMG=deliv_qty)
    lips = vbap_del[vbap_del["VBELN"].isin(likp["VBELN"])][["VBELN_VL", "POSNR", "MATNR", "LFIMG"]].reset_index(drop=True)

    # ---- invoices and payments -------------------------------------------------------
    d = likp.merge(vbak[["VBELN", "KUNNR"]], on="VBELN")
    li = vbap_del[vbap_del["VBELN"].isin(d["VBELN"])].copy()
    li["INVAMT"] = li["LFIMG"] * li["NETPR"]
    inv_amt = li.groupby("VBELN")["INVAMT"].sum()
    cust_idx = pd.Series(np.arange(n_cust), index=kna1["KUNNR"])
    d["ci"] = cust_idx[d["KUNNR"]].to_numpy()
    d["FKDAT"] = d["WADAT_IST"] + pd.to_timedelta(rng.integers(0, 4, len(d)), "D")
    d = d[d["FKDAT"] <= END].reset_index(drop=True)
    d["NETWR"] = np.round(inv_amt.reindex(d["VBELN"]).to_numpy(), 2)
    d["ZT"] = kna1["ZTERM_DAYS"].to_numpy()[d["ci"]]
    d["FAEDT"] = d["FKDAT"] + pd.to_timedelta(d["ZT"], "D")
    d["VBELN_VF"] = _id(10, 9000000 + np.arange(len(d)))
    # anomalies: inflated invoices
    anom_inv = rng.random(len(d)) < 0.012
    d.loc[anom_inv, "NETWR"] = np.round(d.loc[anom_inv, "NETWR"] * rng.uniform(4, 9, anom_inv.sum()), 2)
    vbrk = d[["VBELN_VF", "VBELN", "KUNNR", "FKDAT", "FAEDT", "NETWR"]].assign(WAERK="USD")

    disputed = rng.random(len(d)) < 0.08
    region = kna1["REGION"].to_numpy()[d["ci"]]
    reg_eff = np.array([REGION_EFFECT[r] for r in region])
    shift = np.where((region == "APAC") & (d["FKDAT"] >= SHIFT_DATE), SHIFT_DAYS, 0.0)
    q4 = d["FKDAT"].dt.month.isin([11, 12]).to_numpy() * 2.0
    amt_eff = 3.0 * np.log10(np.maximum(d["NETWR"].to_numpy(), 10) / 1000.0)
    noise = rng.exponential(3.0, len(d)) - 3.0 + rng.normal(0, 4.0, len(d))
    delay_days = cust_bias[d["ci"]] + amt_eff + 8.0 * disputed + reg_eff + shift + q4 + noise
    dtp = np.maximum(1, np.round(d["ZT"].to_numpy() + delay_days)).astype(int)
    defaulter = rng.random(len(d)) < 0.015
    augdt = d["FKDAT"] + pd.to_timedelta(dtp, "D")
    paid = (augdt <= END).to_numpy() & ~defaulter
    bsad = pd.DataFrame({"VBELN_VF": d["VBELN_VF"], "AUGDT": augdt, "DMBTR": d["NETWR"].to_numpy()})[paid].reset_index(drop=True)
    anom_pay = rng.random(len(bsad)) < 0.006
    bsad.loc[anom_pay, "DMBTR"] = np.round(bsad.loc[anom_pay, "DMBTR"] * rng.choice([0.4, 1.8], anom_pay.sum()), 2)
    bsad["WAERS"] = "USD"
    truth_anom = pd.concat([
        pd.DataFrame({"KIND": "invoice", "KEY": d.loc[anom_inv, "VBELN_VF"].to_numpy()}),
        pd.DataFrame({"KIND": "payment", "KEY": bsad.loc[anom_pay, "VBELN_VF"].to_numpy()})], ignore_index=True)

    # ---- disputes / tickets ----------------------------------------------------------
    dis_idx = np.flatnonzero(disputed)
    tickets = make_tickets(rng, d.iloc[dis_idx][["VBELN_VF", "FKDAT"]].reset_index(drop=True), seed)

    # ---- purchasing ------------------------------------------------------------------
    po_vend = rng.integers(0, n_vend, n_po)
    bedat = _dates_weighted(rng, n_po, START, END - pd.Timedelta(days=5), growth=0.1).sort_values()
    ebeln = _id(10, 4500000 + np.arange(n_po))
    ekko = pd.DataFrame({"EBELN": ebeln, "LIFNR": lfa1["LIFNR"].to_numpy()[po_vend], "BEDAT": bedat, "WAERS": "USD"})
    po_lines = np.clip(1 + rng.poisson(2.0, n_po), 1, 6)
    pl_order = np.repeat(np.arange(n_po), po_lines)
    pmi = rng.choice(n_mat, len(pl_order), p=mat_w)
    pqty = np.maximum(10, rng.lognormal(4.0, 0.6, len(pl_order)).astype(int))
    pprice = np.round(mara["STD_COST"].to_numpy()[pmi] * rng.uniform(0.95, 1.05, len(pl_order)), 2)
    ekpo = pd.DataFrame({"EBELN": np.array(ebeln)[pl_order], "EBELP": np.concatenate([np.arange(1, k + 1) * 10 for k in po_lines]),
                         "MATNR": mara["MATNR"].to_numpy()[pmi], "MENGE": pqty, "NETPR": pprice})
    plan_lead = mara["LEAD_DAYS"].to_numpy()[pmi]
    act_lead = np.round(plan_lead * vend_slow[po_vend[pl_order]] * rng.lognormal(0, 0.28, len(pl_order))).astype(int)
    act_lead = np.maximum(act_lead, 1)
    budat = bedat.to_numpy()[pl_order] + pd.to_timedelta(act_lead, "D").to_numpy()
    ekbe = pd.DataFrame({"EBELN": ekpo["EBELN"], "EBELP": ekpo["EBELP"], "BUDAT": budat,
                         "MENGE": np.where(rng.random(len(ekpo)) < 0.05, (pqty * 0.8).astype(int), pqty)})
    ekbe = ekbe[ekbe["BUDAT"] <= END].reset_index(drop=True)
    po_full = ekbe.groupby("EBELN").size().reindex(ebeln).fillna(0).to_numpy() == po_lines
    gr_max = ekbe.groupby("EBELN")["BUDAT"].max().reindex(ebeln)
    po_val = (ekpo["MENGE"] * ekpo["NETPR"]).groupby(ekpo["EBELN"]).sum().reindex(ebeln).to_numpy()
    vt = lfa1["ZTERM_DAYS"].to_numpy()[po_vend]
    rb = pd.DataFrame({"BELNR_MM": _id(10, 5100000 + np.arange(n_po)), "EBELN": ebeln, "LIFNR": ekko["LIFNR"],
                       "BLDAT": gr_max.to_numpy() + pd.Timedelta(days=2), "FAEDT": gr_max.to_numpy() + pd.to_timedelta(vt + 2, "D"),
                       "RMWWR": np.round(po_val, 2)})
    rb["AUGDT"] = rb["FAEDT"] + pd.to_timedelta(np.round(rng.normal(2, 5, n_po)).astype(int), "D")
    rbkp = rb[po_full & (rb["BLDAT"] <= END).to_numpy()].reset_index(drop=True)
    rbkp.loc[rbkp["AUGDT"] > END, "AUGDT"] = pd.NaT
    rbkp["WAERS"] = "USD"

    # ---- general ledger --------------------------------------------------------------
    bk, bs = [], []
    n = [0]

    def post(df_dates, lines, blart, ref):
        """lines: list of (account, side, amount_array, kostl_array|None)."""
        k = len(df_dates)
        bel = _id(10, 100000000 + n[0] + np.arange(k))
        n[0] += k
        bk.append(pd.DataFrame({"BELNR": bel, "BUDAT": df_dates, "BLART": blart, "XBLNR": ref}))
        for bz, (acct, side, amt, kostl) in enumerate(lines, start=1):
            bs.append(pd.DataFrame({"BELNR": bel, "BUZEI": bz, "HKONT": acct, "KOSTL": kostl, "SHKZG": side,
                                    "DMBTR": np.round(np.asarray(amt, dtype=float), 2), "BUDAT": df_dates}))

    post(vbrk["FKDAT"].to_numpy(), [(140000, "S", vbrk["NETWR"], None), (400000, "H", vbrk["NETWR"], None)], "RV", vbrk["VBELN_VF"].to_numpy())
    cogs_src = lips.merge(mara[["MATNR", "STD_COST"]], on="MATNR")
    cogs_src["C"] = cogs_src["LFIMG"] * cogs_src["STD_COST"]
    cogs_del = cogs_src.groupby("VBELN_VL")["C"].sum().reset_index().merge(likp[["VBELN_VL", "WADAT_IST"]], on="VBELN_VL")
    cogs_del = cogs_del[cogs_del["WADAT_IST"] <= END]
    post(cogs_del["WADAT_IST"].to_numpy(), [(500000, "S", cogs_del["C"], None), (300000, "H", cogs_del["C"], None)], "WL", cogs_del["VBELN_VL"].to_numpy())
    post(bsad["AUGDT"].to_numpy(), [(100000, "S", bsad["DMBTR"], None), (140000, "H", bsad["DMBTR"], None)], "DZ", bsad["VBELN_VF"].to_numpy())

    periods = pd.period_range(START, END, freq="M")
    base_bud = rng.lognormal(7.6, 0.5, (len(csks), len(OPEX_ACCOUNTS)))
    over_cc = rng.random(len(csks)) < 0.25  # overspending cost centres with drift
    bud_rows, ox = [], []
    for pi, p in enumerate(periods):
        grow = 1 + 0.01 * pi
        season = 1.1 if p.month in (11, 12) else 1.0
        plan = base_bud * grow * season
        drift = 1 + np.where(over_cc, 0.004 * pi, 0.0)[:, None]
        act = plan * rng.normal(1.0, 0.07, plan.shape) * drift
        per = int(p.year * 100 + p.month)
        for c in range(len(csks)):
            bud_rows.append((csks["KOSTL"][c], per, round(float(plan[c].sum()), 2)))
            for a in range(len(OPEX_ACCOUNTS)):
                ox.append((per, p.to_timestamp(how="end").normalize(), csks["KOSTL"][c], OPEX_ACCOUNTS[a], round(float(act[c, a]), 2)))
    budg = pd.DataFrame(bud_rows, columns=["KOSTL", "PERIOD", "AMT_BUDGET"])
    ox = pd.DataFrame(ox, columns=["PERIOD", "BUDAT", "KOSTL", "HKONT", "DMBTR"])
    for per, g in ox.groupby("PERIOD"):
        dt = g["BUDAT"].iloc[0]
        bel = _id(10, [100000000 + n[0]])[0]
        n[0] += 1
        bk.append(pd.DataFrame({"BELNR": [bel], "BUDAT": [dt], "BLART": "SA", "XBLNR": f"OPEX{per}"}))
        lines = pd.DataFrame({"BELNR": bel, "BUZEI": np.arange(1, len(g) + 1), "HKONT": g["HKONT"].to_numpy(), "KOSTL": g["KOSTL"].to_numpy(),
                              "SHKZG": "S", "DMBTR": g["DMBTR"].to_numpy(), "BUDAT": dt})
        credit = pd.DataFrame({"BELNR": [bel], "BUZEI": [len(g) + 1], "HKONT": [160000], "KOSTL": [None], "SHKZG": ["H"],
                               "DMBTR": [round(float(g["DMBTR"].sum()), 2)], "BUDAT": [dt]})
        bs.append(pd.concat([lines, credit], ignore_index=True))
    bkpf = pd.concat(bk, ignore_index=True)
    bkpf["GJAHR"] = bkpf["BUDAT"].dt.year
    bkpf["MONAT"] = bkpf["BUDAT"].dt.month
    bseg = pd.concat(bs, ignore_index=True)
    bseg["PERIOD"] = (bseg["BUDAT"].dt.year * 100 + bseg["BUDAT"].dt.month).astype(int)
    bseg = bseg.drop(columns="BUDAT")
    bseg["KOSTL"] = bseg["KOSTL"].astype(object).where(bseg["KOSTL"].notna(), None)
    bkpf = bkpf[["BELNR", "BUDAT", "GJAHR", "MONAT", "BLART", "XBLNR"]]
    skat = pd.DataFrame([(k, v[0], v[1]) for k, v in GL_ACCOUNTS.items()], columns=["HKONT", "TXT", "GRP"])

    return {"KNA1": kna1, "LFA1": lfa1, "MARA": mara, "CSKS": csks, "SKA1": skat, "VBAK": vbak, "VBAP": vbap, "LIKP": likp,
            "LIPS": lips, "VBRK": vbrk, "BSAD": bsad, "EKKO": ekko, "EKPO": ekpo, "EKBE": ekbe, "RBKP": rbkp,
            "BKPF": bkpf, "BSEG": bseg, "BUDG": budg, "TICKETS": tickets, "TRUTH_ANOMALY": truth_anom}
