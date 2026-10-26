import numpy as np

from lekha import kpis
from lekha.tables import AS_OF


def test_aging_buckets_partition_open_ar(built):
    t = built["t"]
    o = kpis.ar_open(t, AS_OF)
    ag = kpis.ar_aging(t, AS_OF)
    assert abs(ag["Amount"].sum() - o["NETWR"].sum()) < 0.01
    assert set(ag["Bucket"]) <= set(kpis.BUCKETS)
    for b, lo, hi in [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90)]:
        assert o[o["Bucket"] == b]["DaysOverdue"].between(lo, hi).all()
    assert (o[o["Bucket"] == "90+"]["DaysOverdue"] > 90).all()
    assert (o[o["Bucket"] == "Current"]["FAEDT"] > AS_OF).all()


def test_open_ar_excludes_paid_invoices(built):
    t = built["t"]
    assert not kpis.ar_open(t, AS_OF)["VBELN_VF"].isin(t["BSAD"]["VBELN_VF"]).any()


def test_dso_definition(built):
    d = kpis.dso_monthly(built["t"]).iloc[-1]
    assert abs(d["DSO"] - d["OpenAR"] * 90 / d["Sales90"]) < 0.01
    assert 20 < d["DSO"] < 200


def test_otif_is_on_time_and_in_full(built):
    o = kpis.otif_order(built["t"])
    assert ((o["OnTime"] == 1) == (o["WADAT_IST"] <= o["LFDAT"])).all()
    m = kpis.otif_monthly(built["t"])
    assert (m["OTIFPct"] <= m[["OnTimePct", "InFullPct"]].min(axis=1) + 0.01).all()


def test_cycle_time_legs_add_up(built):
    x = kpis.cycle_order(built["t"])
    assert (x["OrderToDelivery"] + x["DeliveryToInvoice"] + x["InvoiceToCash"] == x["OrderToCash"]).all()


def test_variance_and_pnl_identities(built):
    t = built["t"]
    v = kpis.budget_variance(t)
    assert np.allclose(v["Variance"], v["Actual"] - v["Budget"])
    g = v[v["KOSTL"] == v["KOSTL"].iloc[0]]
    assert np.isclose(g[g["PERIOD"] // 100 == 2024]["Actual"].sum(), g[g["PERIOD"] == 202412]["YtdActual"].iloc[0])
    p = kpis.pnl_period(t)
    assert np.allclose(p["Ebit"], p["Revenue"] - p["Cogs"] - p["Opex"])
