"""Build the typed analytic tables: cleaned staged tables + directly-loaded GL/master tables."""
from __future__ import annotations

import pandas as pd

from .generator import generate
from .staging import clean_pandas, make_staging, typed

AS_OF = pd.Timestamp("2025-12-31")
DIRECT = ["SKA1", "CSKS", "BKPF", "BSEG", "BUDG", "TICKETS"]


def build(seed: int = 42, scale: float = 1.0):
    """Returns (typed cleaned tables, truth, staging, quarantine, defect_log)."""
    truth = generate(seed, scale)
    stg, log = make_staging(truth, seed)
    core, quarantine = clean_pandas(stg)
    t = typed(core)
    for k in DIRECT:
        t[k] = truth[k].copy()
    return t, truth, stg, quarantine, log


def incomplete_orders(stg: dict[str, pd.DataFrame], quarantine: pd.DataFrame) -> set[str]:
    """Sales orders that lost at least one line item (VBAP/LIPS) to quarantine; their invoices cannot be 3-way matched."""
    q = quarantine[quarantine.REASON != "DUPLICATE_KEY"]  # a rejected duplicate leaves the original line in place
    vb = stg["VBAP"].merge(q[q.SRC_TABLE == "VBAP"][["SRC_SEQ"]], left_on="SEQ", right_on="SRC_SEQ")["VBELN"]
    lp = stg["LIPS"].merge(q[q.SRC_TABLE == "LIPS"][["SRC_SEQ"]], left_on="SEQ", right_on="SRC_SEQ")["VBELN_VL"]
    lk = stg["LIKP"].drop_duplicates("VBELN_VL").set_index("VBELN_VL")["VBELN"]
    return set(vb.dropna()) | set(lp.map(lk).dropna())
