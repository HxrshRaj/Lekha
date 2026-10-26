import pandas as pd

from lekha.generator import generate
from lekha.staging import SPECS, make_staging


def test_generator_is_deterministic():
    a, b = generate(7, 0.05), generate(7, 0.05)
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])
    c = generate(8, 0.05)
    assert not a["VBRK"]["NETWR"].equals(c["VBRK"]["NETWR"])


def test_staging_is_deterministic():
    t = generate(7, 0.05)
    (s1, l1), (s2, l2) = make_staging(t, 7), make_staging(t, 7)
    for k in s1:
        pd.testing.assert_frame_equal(s1[k], s2[k])
    pd.testing.assert_frame_equal(l1, l2)


def test_scale_and_sap_style_tables(built):
    truth = built["truth"]
    for name in ["KNA1", "LFA1", "MARA", "VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "BSAD", "EKKO", "EKPO", "EKBE", "BKPF", "BSEG"]:
        assert len(truth[name]) > 0
    assert truth["MARA"]["BASE_MATNR"].nunique() < len(truth["MARA"])  # product variants share a base product
    assert truth["MARA"]["CONF_CODE"].str.contains("COLOUR=").all()
    assert truth["VBRK"]["FKDAT"].between("2023-01-01", "2025-12-31").all()


def test_gl_balances(built):
    s = built["truth"]["BSEG"].groupby("SHKZG")["DMBTR"].sum()
    assert abs(s["S"] - s["H"]) < 1.0  # every document balances


def test_injected_defect_rate_is_about_two_percent(built):
    stg, log = built["stg"], built["log"]
    assert 0.01 < len(log) / sum(len(v) for v in stg.values()) < 0.04
    assert set(log["DEFECT"]) == {"NULL_REQUIRED", "BAD_DATE", "NEGATIVE_AMOUNT", "CURRENCY_MISMATCH", "ORPHAN_KEY", "DUPLICATE_KEY"}
    assert set(log["TABLE"]) <= set(SPECS)
