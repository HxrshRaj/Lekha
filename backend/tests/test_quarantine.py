import pandas as pd

from lekha.staging import REASONS, clean_pandas


def test_every_staging_row_lands_in_exactly_one_place(built):
    stg, q = built["stg"], built["q"]
    core = clean_pandas(stg)[0]
    for t, df in stg.items():
        n_q = int((q.SRC_TABLE == t).sum())
        assert len(core[t]) + n_q == len(df)
    assert not q.duplicated(["SRC_TABLE", "SRC_SEQ"]).any()
    assert set(q.REASON) <= set(REASONS)


def test_each_injected_defect_type_is_quarantined_with_the_right_reason(built):
    q, log = built["q"], built["log"]
    for reason in ("NULL_REQUIRED", "BAD_DATE", "NEGATIVE_AMOUNT", "CURRENCY_MISMATCH", "DUPLICATE_KEY"):
        injected = (log["DEFECT"] == reason).sum()
        found = (q["REASON"] == reason).sum()
        assert found >= injected * 0.95, (reason, injected, found)


def test_core_has_no_rule_violations(built):
    t = built["t"]
    assert (t["VBRK"]["NETWR"] >= 0).all() and (t["BSAD"]["DMBTR"] >= 0).all()
    assert (t["VBRK"]["WAERK"] == "USD").all()
    assert t["VBRK"]["VBELN_VF"].is_unique and t["VBAK"]["VBELN"].is_unique
    assert t["VBRK"]["KUNNR"].isin(t["KNA1"]["KUNNR"]).all()
    assert t["VBAP"]["VBELN"].isin(t["VBAK"]["VBELN"]).all()
    assert t["BSAD"]["VBELN_VF"].isin(t["VBRK"]["VBELN_VF"]).all()
    assert (t["BSAD"].merge(t["VBRK"], on="VBELN_VF").eval("AUGDT >= FKDAT")).all()


def test_quarantine_priority_and_dedup_keep_first(built):
    stg = {k: v.copy() for k, v in built["stg"].items()}
    k = stg["KNA1"]
    n = int(k["SEQ"].max())
    base = k.iloc[0].copy()
    bad = base.copy(); bad["SEQ"] = n + 1; bad["KUNNR"] = "ZZ1"; bad["NAME1"] = None   # null required field
    nokey = base.copy(); nokey["SEQ"] = n + 2; nokey["KUNNR"] = None                     # null key
    dup = base.copy(); dup["SEQ"] = n + 3                                                # duplicate of an existing key
    stg["KNA1"] = pd.concat([k, pd.DataFrame([bad, nokey, dup])], ignore_index=True)
    core, q = clean_pandas(stg)
    r = q[q.SRC_TABLE == "KNA1"].set_index("SRC_SEQ")["REASON"]
    assert r[n + 1] == "NULL_REQUIRED" and r[n + 2] == "NULL_REQUIRED" and r[n + 3] == "DUPLICATE_KEY"
    assert base["KUNNR"] in set(core["KNA1"]["KUNNR"])  # the first copy survives
