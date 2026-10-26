"""SQL Server helpers: run the T-SQL scripts, bulk-load staging/GL tables, read KPI views.
Connection comes from env vars (LEKHA_SQL_HOST/PORT/USER/PASSWORD); the layer is optional at runtime
(the deployed API serves precomputed results and never needs SQL Server)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
GL_LOAD = ["SKA1", "CSKS", "BKPF", "BSEG", "BUDG", "TICKETS"]


def connect(database: str = "master"):
    import pymssql
    return pymssql.connect(server=os.environ.get("LEKHA_SQL_HOST", "localhost"), port=os.environ.get("LEKHA_SQL_PORT", "14330"),
                           user=os.environ.get("LEKHA_SQL_USER", "sa"), password=os.environ.get("LEKHA_SQL_PASSWORD", "Lekha_Passw0rd!"),
                           database=database, autocommit=True, login_timeout=30)


def run_script(conn, path: Path) -> None:
    cur = conn.cursor()
    for batch in re.split(r"^\s*GO\s*$", path.read_text(encoding="utf-8"), flags=re.M | re.I):
        if batch.strip():
            cur.execute(batch)
            while cur.nextset():
                pass


def _lit(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT or (not isinstance(v, str) and pd.isna(v)):
        return "NULL"
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return "'" + pd.Timestamp(v).strftime("%Y-%m-%d") + "'"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        return repr(float(v))
    return "N'" + str(v).replace("'", "''") + "'"


def bulk_insert(conn, table: str, df: pd.DataFrame, chunk: int = 900) -> None:
    cols = ", ".join(df.columns)
    cur = conn.cursor()
    rows = df.astype(object).where(df.notna(), None).to_numpy().tolist()
    for i in range(0, len(rows), chunk):
        vals = ",".join("(" + ",".join(_lit(v) for v in r) + ")" for r in rows[i:i + chunk])
        cur.execute(f"INSERT INTO {table} ({cols}) VALUES {vals}")


def build_database(conn, stg: dict[str, pd.DataFrame], truth: dict[str, pd.DataFrame], as_of: str = "2025-12-31") -> None:
    run_script(conn, SQL_DIR / "01_schema.sql")
    conn.cursor().execute("USE lekha")
    c = connect("lekha")
    run_script(c, SQL_DIR / "02_clean.sql")
    for t in GL_LOAD:
        bulk_insert(c, f"dbo.{t}", truth[t])
    for t, df in stg.items():
        bulk_insert(c, f"stg.{t}", df)
    c.cursor().execute("UPDATE dbo.Params SET AsOfDate = %s", (as_of,))
    c.cursor().execute("EXEC dbo.usp_CleanAll")
    run_script(c, SQL_DIR / "03_views.sql")
    run_script(c, SQL_DIR / "04_indexed_view.sql")
    c.close()


def query(conn, sql: str) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    for col in df.columns:
        if df[col].map(lambda x: hasattr(x, "as_tuple")).any():
            df[col] = df[col].astype(float)
    return df
