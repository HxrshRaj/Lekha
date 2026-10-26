"""Staging tables (all-string, like a raw extract) with ~2% injected data-quality defects,
plus the pandas reference implementation of the cleaning/quarantine rules.

The same rules are implemented in T-SQL in sql/03_clean.sql; tests compare both.
Reason priority (first match wins): NULL_REQUIRED, DUPLICATE_KEY, BAD_DATE, NEGATIVE_AMOUNT,
CURRENCY_MISMATCH, ORPHAN_KEY.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# table -> spec. order matters (parents first).
SPECS: dict[str, dict] = {
    "KNA1": dict(key=["KUNNR"], required=["KUNNR", "NAME1", "WAERS"], dates=[], amounts=[]),
    "LFA1": dict(key=["LIFNR"], required=["LIFNR", "NAME1"], dates=[], amounts=[]),
    "MARA": dict(key=["MATNR"], required=["MATNR", "MAKTX", "PRICE"], dates=[], amounts=[("PRICE", "neg")]),
    "VBAK": dict(key=["VBELN"], required=["VBELN", "KUNNR", "AUDAT", "VDATU", "NETWR", "WAERK"], dates=["AUDAT", "VDATU"],
                 amounts=[("NETWR", "neg")], currency=("WAERK", "KUNNR", "KNA1", "KUNNR", "WAERS"),
                 fks=[(["KUNNR"], "KNA1", ["KUNNR"])]),
    "VBAP": dict(key=["VBELN", "POSNR"], required=["VBELN", "POSNR", "MATNR", "KWMENG", "NETPR"], dates=[],
                 amounts=[("KWMENG", "nonpos"), ("NETPR", "neg")],
                 fks=[(["VBELN"], "VBAK", ["VBELN"]), (["MATNR"], "MARA", ["MATNR"])]),
    "LIKP": dict(key=["VBELN_VL"], required=["VBELN_VL", "VBELN", "LFDAT", "WADAT_IST"], dates=["LFDAT", "WADAT_IST"], amounts=[],
                 fks=[(["VBELN"], "VBAK", ["VBELN"])]),
    "LIPS": dict(key=["VBELN_VL", "POSNR"], required=["VBELN_VL", "POSNR", "MATNR", "LFIMG"], dates=[], amounts=[("LFIMG", "neg")],
                 fks=[(["VBELN_VL"], "LIKP", ["VBELN_VL"]), (["MATNR"], "MARA", ["MATNR"])]),
    "VBRK": dict(key=["VBELN_VF"], required=["VBELN_VF", "VBELN", "KUNNR", "FKDAT", "FAEDT", "NETWR", "WAERK"],
                 dates=["FKDAT", "FAEDT"], amounts=[("NETWR", "neg")], currency=("WAERK", "KUNNR", "KNA1", "KUNNR", "WAERS"),
                 fks=[(["VBELN"], "VBAK", ["VBELN"]), (["KUNNR"], "KNA1", ["KUNNR"])]),
    "BSAD": dict(key=["VBELN_VF"], required=["VBELN_VF", "AUGDT", "DMBTR"], dates=["AUGDT"], amounts=[("DMBTR", "neg")],
                 fks=[(["VBELN_VF"], "VBRK", ["VBELN_VF"])], date_after=("AUGDT", "VBRK", "VBELN_VF", "VBELN_VF", "FKDAT")),
    "EKKO": dict(key=["EBELN"], required=["EBELN", "LIFNR", "BEDAT"], dates=["BEDAT"], amounts=[],
                 fks=[(["LIFNR"], "LFA1", ["LIFNR"])]),
    "EKPO": dict(key=["EBELN", "EBELP"], required=["EBELN", "EBELP", "MATNR", "MENGE", "NETPR"], dates=[],
                 amounts=[("MENGE", "nonpos"), ("NETPR", "neg")], fks=[(["EBELN"], "EKKO", ["EBELN"]), (["MATNR"], "MARA", ["MATNR"])]),
    "EKBE": dict(key=["EBELN", "EBELP"], required=["EBELN", "EBELP", "BUDAT", "MENGE"], dates=["BUDAT"], amounts=[("MENGE", "neg")],
                 fks=[(["EBELN", "EBELP"], "EKPO", ["EBELN", "EBELP"])]),
    "RBKP": dict(key=["BELNR_MM"], required=["BELNR_MM", "EBELN", "LIFNR", "BLDAT", "FAEDT", "RMWWR"], dates=["BLDAT", "FAEDT"],
                 optional_dates=["AUGDT"], amounts=[("RMWWR", "neg")], fks=[(["LIFNR"], "LFA1", ["LIFNR"])]),
}
STAGED = list(SPECS)
REASONS = ["NULL_REQUIRED", "DUPLICATE_KEY", "BAD_DATE", "NEGATIVE_AMOUNT", "CURRENCY_MISMATCH", "ORPHAN_KEY"]
DEFECT_RATE = 0.02  # total per table across defect types
BAD_DATE_STRINGS = ["2024-13-45", "31/02/2024", "N/A", "0000-00-00"]


def _to_str(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            v = s.dt.strftime("%Y-%m-%d").astype(object)
        elif pd.api.types.is_float_dtype(s):
            v = s.map(lambda x: None if pd.isna(x) else f"{x:.2f}").astype(object)
        else:
            v = s.map(lambda x: None if pd.isna(x) else str(x)).astype(object)
        out[c] = v.where(v.notna(), None)
    return out


def make_staging(truth: dict[str, pd.DataFrame], seed: int = 42) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Return (staging tables with SEQ column, defect log of what was injected)."""
    rng = np.random.default_rng(seed + 1)
    stg: dict[str, pd.DataFrame] = {}
    log = []
    for t in STAGED:
        sp = SPECS[t]
        df = _to_str(truth[t]).reset_index(drop=True)
        n = len(df)
        # amount decimals: store money with 2 dp, quantities as ints
        for c in ("KWMENG", "LFIMG", "MENGE", "POSNR", "EBELP"):
            if c in df.columns:
                df[c] = df[c].map(lambda x: None if x is None else str(int(float(x))))
        k = lambda frac: max(1, int(round(n * DEFECT_RATE * frac)))
        used: set[int] = set()

        def pick(m, pool=None):
            cand = np.array([i for i in (pool if pool is not None else range(n)) if i not in used])
            if len(cand) == 0:
                return np.array([], dtype=int)
            ids = rng.choice(cand, size=min(m, len(cand)), replace=False)
            used.update(int(i) for i in ids)
            return ids

        def record(ids, kind, d=df):
            for i in ids:
                log.append((t, "|".join(str(d.at[i, c]) for c in sp["key"]), kind))

        nonkey_req = [c for c in sp["required"] if c not in sp["key"]]
        if nonkey_req:
            ids = pick(k(0.2))
            for i in ids:
                df.at[i, nonkey_req[int(rng.integers(len(nonkey_req)))]] = None
            record(ids, "NULL_REQUIRED")
        if sp["dates"]:
            ids = pick(k(0.15))
            for i in ids:
                df.at[i, sp["dates"][int(rng.integers(len(sp["dates"])))]] = BAD_DATE_STRINGS[int(rng.integers(len(BAD_DATE_STRINGS)))]
            record(ids, "BAD_DATE")
        if "date_after" in sp:  # payment dated before the invoice
            ids = pick(k(0.1))
            for i in ids:
                df.at[i, sp["date_after"][0]] = "2020-01-01"
            record(ids, "BAD_DATE")
        if sp["amounts"]:
            ids = pick(k(0.15))
            for i in ids:
                col, kind = sp["amounts"][int(rng.integers(len(sp["amounts"])))]
                v = float(df.at[i, col])
                df.at[i, col] = f"{-abs(v) if v != 0 else -1:.2f}" if col not in ("KWMENG", "LFIMG", "MENGE") else str(-int(abs(v) or 1))
            record(ids, "NEGATIVE_AMOUNT")
        if "currency" in sp:
            ids = pick(k(0.1))
            df.loc[ids, sp["currency"][0]] = "EUR"
            record(ids, "CURRENCY_MISMATCH")
        if sp.get("fks"):
            ids = pick(k(0.15))
            for i in ids:
                cols, _, _ = sp["fks"][int(rng.integers(len(sp["fks"])))]
                c0 = cols[0]
                df.at[i, c0] = "X" + str(df.at[i, c0])[1:] if df.at[i, c0] else "X999"
            record(ids, "ORPHAN_KEY")
        # duplicate key rows (exact copies appended at the end)
        dup_ids = rng.choice(n, size=k(0.25), replace=False)
        dups = df.iloc[dup_ids].copy()
        record(dup_ids, "DUPLICATE_KEY")
        df = pd.concat([df, dups], ignore_index=True)
        df.insert(0, "SEQ", np.arange(1, len(df) + 1))
        stg[t] = df
    return stg, pd.DataFrame(log, columns=["TABLE", "KEY", "DEFECT"])


# --------------------------- pandas reference cleaning ------------------------------------
def _blank(s: pd.Series) -> pd.Series:
    return s.isna() | (s.astype(str).str.strip() == "")


def _pdate(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.where(s.notna()), format="%Y-%m-%d", errors="coerce")


def clean_pandas(stg: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    core: dict[str, pd.DataFrame] = {}
    quarantine = []
    for t in STAGED:
        sp = SPECS[t]
        df = stg[t].copy()
        reason = pd.Series(None, index=df.index, dtype=object)

        def setr(mask, r):
            reason.loc[mask & reason.isna()] = r

        req_null = pd.Series(False, index=df.index)
        for c in sp["required"]:
            req_null |= _blank(df[c])
        setr(req_null, "NULL_REQUIRED")
        keyed = df[~req_null] if True else df
        rn = df.where(~req_null).groupby(sp["key"], dropna=True)["SEQ"].rank(method="first")
        setr(rn.fillna(1) > 1, "DUPLICATE_KEY")
        bad_date = pd.Series(False, index=df.index)
        for c in sp["dates"]:
            bad_date |= _pdate(df[c]).isna()
        for c in sp.get("optional_dates", []):
            bad_date |= df[c].notna() & _pdate(df[c]).isna()
        if "date_after" in sp:
            col, parent, jc, pc, pdc = sp["date_after"]
            pm = core[parent][[pc, pdc]].assign(**{pdc: lambda x: pd.to_datetime(x[pdc])}).drop_duplicates(pc).set_index(pc)[pdc]
            pdate = df[jc].map(pm)
            bad_date |= (_pdate(df[col]) < pdate).fillna(False)
        setr(bad_date, "BAD_DATE")
        neg = pd.Series(False, index=df.index)
        for c, kind in sp["amounts"]:
            v = pd.to_numeric(df[c], errors="coerce")
            neg |= (v < 0) if kind == "neg" else (v <= 0)
        setr(neg, "NEGATIVE_AMOUNT")
        if "currency" in sp:
            col, fk, parent, pcol, pcur = sp["currency"]
            cur = df[fk].map(core[parent].drop_duplicates(pcol).set_index(pcol)[pcur])
            setr((cur.notna() & (df[col] != cur)), "CURRENCY_MISMATCH")
        orphan = pd.Series(False, index=df.index)
        for cols, parent, pcols in sp.get("fks", []):
            keys = set(map(tuple, core[parent][pcols].astype(str).to_numpy()))
            orphan |= ~pd.Series([tuple(r) in keys for r in df[cols].astype(str).to_numpy()], index=df.index)
        setr(orphan, "ORPHAN_KEY")
        quarantine.append(pd.DataFrame({"SRC_TABLE": t, "SRC_SEQ": df.loc[reason.notna(), "SEQ"], "REASON": reason[reason.notna()]}))
        core[t] = df[reason.isna()].drop(columns="SEQ").reset_index(drop=True)
    return core, pd.concat(quarantine, ignore_index=True)


NUM_COLS = {"KNA1": ["ZTERM_DAYS", "CREDIT_LIMIT"], "LFA1": ["ZTERM_DAYS"], "MARA": ["STD_COST", "PRICE", "LEAD_DAYS"],
            "VBAK": ["NETWR"], "VBAP": ["POSNR", "KWMENG", "NETPR", "NETWR"], "LIPS": ["POSNR", "LFIMG"], "VBRK": ["NETWR"],
            "BSAD": ["DMBTR"], "EKPO": ["EBELP", "MENGE", "NETPR"], "EKBE": ["EBELP", "MENGE"], "RBKP": ["RMWWR"]}
DATE_COLS = {"VBAK": ["AUDAT", "VDATU"], "LIKP": ["LFDAT", "WADAT_IST"], "VBRK": ["FKDAT", "FAEDT"], "BSAD": ["AUGDT"],
             "EKKO": ["BEDAT"], "EKBE": ["BUDAT"], "RBKP": ["BLDAT", "FAEDT", "AUGDT"]}


def typed(core: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Convert cleaned all-string tables to typed tables for analytics."""
    out = {}
    for t, df in core.items():
        d = df.copy()
        for c in NUM_COLS.get(t, []):
            d[c] = pd.to_numeric(d[c])
        for c in DATE_COLS.get(t, []):
            d[c] = _pdate(d[c])
        out[t] = d
    return out
