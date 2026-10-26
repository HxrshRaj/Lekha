"""T-SQL layer vs pandas reference. Needs a real SQL Server (Docker locally, service container in CI).
Enable with LEKHA_RUN_SQL=1 (+ LEKHA_SQL_HOST/PORT/PASSWORD); skipped otherwise, and the skip is visible in the pytest summary."""
import os

import numpy as np
import pandas as pd
import pytest

from lekha import kpis, sqlserver
from lekha.staging import STAGED, clean_pandas, typed
from lekha.tables import AS_OF, DIRECT

pytestmark = pytest.mark.skipif(os.environ.get("LEKHA_RUN_SQL") != "1", reason="set LEKHA_RUN_SQL=1 with a reachable SQL Server")

SCALE = float(os.environ.get("LEKHA_SQL_SCALE", "0.1"))


@pytest.fixture(scope="module")
def db():
    from lekha.tables import build
    t, truth, stg, q, _ = build(42, SCALE)
    conn = sqlserver.connect("master")
    sqlserver.build_database(conn, stg, truth, str(AS_OF.date()))
    c = sqlserver.connect("lekha")
    yield {"c": c, "t": t, "stg": stg, "q": q}
    c.close()


def q(db, sql):
    return sqlserver.query(db["c"], sql)


def close(a, b, tol=0.011):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    assert a.shape == b.shape, (a.shape, b.shape)
    assert np.all(np.abs(a - b) <= tol), np.abs(a - b).max()


def test_core_row_counts_match_pandas(db):
    for t in STAGED:
        n = q(db, f"SELECT COUNT(*) n FROM dbo.{t}")["n"][0]
        assert n == len(db["t"][t]), t


def test_quarantine_matches_pandas_by_table_and_reason(db):
    sql = q(db, "SELECT SRC_TABLE, REASON, COUNT(*) n FROM dbo.Quarantine GROUP BY SRC_TABLE, REASON").set_index(["SRC_TABLE", "REASON"])["n"]
    pdq = db["q"].groupby(["SRC_TABLE", "REASON"]).size()
    pd.testing.assert_series_equal(sql.sort_index(), pdq.rename("n").sort_index(), check_dtype=False, check_names=False)
    # the very same staging rows (not just counts) are rejected
    rows = q(db, "SELECT SRC_TABLE, SRC_SEQ, REASON FROM dbo.Quarantine")
    a = rows.sort_values(["SRC_TABLE", "SRC_SEQ"]).reset_index(drop=True)
    b = db["q"][["SRC_TABLE", "SRC_SEQ", "REASON"]].sort_values(["SRC_TABLE", "SRC_SEQ"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)
    raw = q(db, "SELECT TOP 1 RAW_ROW FROM dbo.Quarantine")["RAW_ROW"][0]
    assert raw.startswith("{") and "SEQ" in raw  # raw row preserved as JSON


def test_ar_aging_matches(db):
    s = q(db, "SELECT Bucket, Invoices, Amount, PctOfOpen FROM dbo.vw_AR_Aging").set_index("Bucket")
    p = kpis.ar_aging(db["t"], AS_OF).set_index("Bucket")
    assert set(s.index) == set(p.index)
    s = s.loc[p.index]
    assert list(s["Invoices"]) == list(p["Invoices"])
    close(s["Amount"], p["Amount"])
    close(s["PctOfOpen"], p["PctOfOpen"], 0.011)


def test_ap_aging_matches(db):
    s = q(db, "SELECT Bucket, Invoices, Amount FROM dbo.vw_AP_Aging").set_index("Bucket")
    p = kpis.ap_aging(db["t"], AS_OF).set_index("Bucket")
    s = s.loc[p.index]
    assert list(s["Invoices"]) == list(p["Invoices"])
    close(s["Amount"], p["Amount"])


def test_dso_matches(db):
    s = q(db, "SELECT MonthEnd, OpenAR, Sales90, DSO FROM dbo.vw_DSO_Monthly ORDER BY MonthEnd")
    p = kpis.dso_monthly(db["t"])
    assert len(s) == len(p)
    close(s["OpenAR"], p["OpenAR"])
    close(s["Sales90"], p["Sales90"])
    close(s["DSO"], p["DSO"])


def test_otif_matches(db):
    s = q(db, "SELECT OrderMonth, Orders, OnTimePct, InFullPct, OTIFPct FROM dbo.vw_OTIF_Monthly ORDER BY OrderMonth")
    p = kpis.otif_monthly(db["t"]).sort_values("OrderMonth")
    assert list(s["Orders"]) == list(p["Orders"])
    for c in ("OnTimePct", "InFullPct", "OTIFPct"):
        close(s[c], p[c])


def test_cycle_time_matches_including_median(db):
    s = q(db, "SELECT * FROM dbo.vw_CycleTime_Monthly ORDER BY OrderMonth")
    p = kpis.cycle_monthly(db["t"]).sort_values("OrderMonth")
    assert list(s["PaidOrders"]) == list(p["PaidOrders"])
    for c in ("AvgOrderToDelivery", "AvgDeliveryToInvoice", "AvgInvoiceToCash", "AvgOrderToCash", "MedianOrderToCash"):
        close(s[c], p[c], 1e-6)


def test_budget_variance_matches_with_ytd(db):
    s = q(db, "SELECT KOSTL, PERIOD, Actual, Budget, Variance, VariancePct, YtdActual, YtdBudget FROM dbo.vw_BudgetVariance ORDER BY KOSTL, PERIOD")
    p = kpis.budget_variance(db["t"]).sort_values(["KOSTL", "PERIOD"]).reset_index(drop=True)
    assert list(s["KOSTL"]) == list(p["KOSTL"]) and list(s["PERIOD"]) == list(p["PERIOD"])
    for c in ("Actual", "Budget", "Variance", "YtdActual", "YtdBudget"):
        close(s[c], p[c])
    close(s["VariancePct"].fillna(0), p["VariancePct"].fillna(0))


def test_pnl_matches(db):
    s = q(db, "SELECT PERIOD, Revenue, Cogs, GrossProfit, Opex, Ebit, GrossMarginPct FROM dbo.vw_PnL_Period ORDER BY PERIOD")
    p = kpis.pnl_period(db["t"]).sort_values("PERIOD")
    assert list(s["PERIOD"]) == list(p["PERIOD"])
    for c in ("Revenue", "Cogs", "GrossProfit", "Opex", "Ebit"):
        close(s[c], p[c])
    close(s["GrossMarginPct"], p["GrossMarginPct"])


def test_cleaning_is_rerunnable(db):
    before = q(db, "SELECT (SELECT COUNT(*) FROM dbo.VBRK) v, (SELECT COUNT(*) FROM dbo.Quarantine) q, (SELECT COUNT(*) FROM dbo.KNA1) k")
    db["c"].cursor().execute("EXEC dbo.usp_CleanAll")
    after = q(db, "SELECT (SELECT COUNT(*) FROM dbo.VBRK) v, (SELECT COUNT(*) FROM dbo.Quarantine) q, (SELECT COUNT(*) FROM dbo.KNA1) k")
    pd.testing.assert_frame_equal(before, after)


def test_constraints_reject_bad_rows(db):
    import pymssql
    cur = db["c"].cursor()
    with pytest.raises(pymssql.Error):  # negative amount violates CHECK
        cur.execute("INSERT dbo.VBRK (VBELN_VF, VBELN, KUNNR, FKDAT, FAEDT, NETWR, WAERK) SELECT TOP 1 'NEG0000001', VBELN, KUNNR, FKDAT, FAEDT, -5, WAERK FROM dbo.VBRK")
    with pytest.raises(pymssql.Error):  # orphan foreign key
        cur.execute("INSERT dbo.BSAD (VBELN_VF, AUGDT, DMBTR, WAERS) VALUES ('NOSUCHINV', '2025-01-01', 1, 'USD')")
    with pytest.raises(pymssql.Error):  # duplicate primary key
        cur.execute("INSERT dbo.KNA1 (KUNNR, NAME1, WAERS) SELECT TOP 1 KUNNR, NAME1, WAERS FROM dbo.KNA1")


def test_indexed_view_equals_base_table_aggregate(db):
    base = q(db, "SELECT PERIOD, HKONT, SUM(CASE WHEN SHKZG='S' THEN DMBTR ELSE -DMBTR END) AS A FROM dbo.BSEG GROUP BY PERIOD, HKONT ORDER BY PERIOD, HKONT")
    iv = q(db, "SELECT PERIOD, HKONT, SUM(CASE WHEN SHKZG='S' THEN Amount ELSE -Amount END) AS A FROM dbo.vw_GL_PeriodAccount WITH (NOEXPAND) GROUP BY PERIOD, HKONT ORDER BY PERIOD, HKONT")
    assert len(base) == len(iv)
    close(base["A"], iv["A"])


def test_direct_loaded_tables_complete(db):
    for t in DIRECT:
        n = q(db, f"SELECT COUNT(*) n FROM dbo.{t}")["n"][0]
        assert n == len(db["t"][t]), t
