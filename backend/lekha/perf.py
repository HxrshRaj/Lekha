"""Measured before/after for the indexed view (needs SQL Server): python -m lekha.perf [--scale 1.0]
Writes docs/perf_indexed_view.md with timings, logical reads and the showplan text of both queries."""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

from . import sqlserver
from .tables import AS_OF, build

BASE = ("SELECT PERIOD, HKONT, SUM(CASE WHEN SHKZG='S' THEN DMBTR ELSE -DMBTR END) AS A "
        "FROM dbo.BSEG GROUP BY PERIOD, HKONT ORDER BY PERIOD, HKONT")
VIEW = ("SELECT PERIOD, HKONT, SUM(CASE WHEN SHKZG='S' THEN Amount ELSE -Amount END) AS A "
        "FROM dbo.vw_GL_PeriodAccount WITH (NOEXPAND) GROUP BY PERIOD, HKONT ORDER BY PERIOD, HKONT")


def _reads(c) -> int:
    cur = c.cursor()
    cur.execute("SELECT logical_reads FROM sys.dm_exec_sessions WHERE session_id = @@SPID")
    return int(cur.fetchone()[0])


def measure(c, sql: str, n: int = 30) -> dict:
    cur = c.cursor()
    cur.execute(sql); cur.fetchall()  # warm up
    times, reads = [], []
    for _ in range(n):
        r0 = _reads(c)
        t0 = time.perf_counter()
        cur.execute(sql); rows = cur.fetchall()
        times.append((time.perf_counter() - t0) * 1000)
        reads.append(_reads(c) - r0 - 1)  # -1: the DMV lookup itself
    return {"median_ms": statistics.median(times), "p90_ms": sorted(times)[int(0.9 * n) - 1], "logical_reads": int(statistics.median(reads)), "rows": len(rows)}


def plan(c, sql: str) -> str:
    cur = c.cursor()
    cur.execute("SET SHOWPLAN_TEXT ON")
    cur.execute(sql)
    text = "\n".join(str(r[0]) for r in cur.fetchall())
    cur.execute("SET SHOWPLAN_TEXT OFF")
    return text


def main(scale: float, out: Path) -> None:
    t, truth, stg, q, _ = build(42, scale)
    conn = sqlserver.connect("master")
    sqlserver.build_database(conn, stg, truth, str(AS_OF.date()))
    c = sqlserver.connect("lekha")
    cur = c.cursor()
    cur.execute("SELECT @@VERSION"); version = cur.fetchone()[0].splitlines()[0]
    cur.execute("SELECT COUNT(*) FROM dbo.BSEG"); n_bseg = cur.fetchone()[0]
    b, v = measure(c, BASE), measure(c, VIEW)
    md = f"""# Indexed view: measured before / after

Run on `{version}`, scale {scale}, `dbo.BSEG` = {n_bseg:,} rows, warm cache, 30 runs per query (python `-m lekha.perf`).

Query: GL amount by period and account (the aggregation under the P&L).

| | Base table scan + aggregate | Indexed view `vw_GL_PeriodAccount` (`NOEXPAND`) |
|---|---|---|
| median time | {b['median_ms']:.1f} ms | {v['median_ms']:.1f} ms |
| p90 time | {b['p90_ms']:.1f} ms | {v['p90_ms']:.1f} ms |
| logical reads | {b['logical_reads']:,} | {v['logical_reads']:,} |
| rows returned | {b['rows']} | {v['rows']} |

Speed-up (median): {b['median_ms'] / max(v['median_ms'], 0.001):.1f}x; logical reads reduced {b['logical_reads'] / max(v['logical_reads'], 1):.1f}x.

## Plan: base table
```
{plan(c, BASE)}
```
## Plan: indexed view
```
{plan(c, VIEW)}
```
The indexed view has a unique clustered index on (PERIOD, HKONT, SHKZG), maintained on every write to `BSEG`
(a write-cost trade-off; fine for a mostly-append ledger, not free for heavy OLTP).
"""
    out.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "perf_indexed_view.md"))
    a = ap.parse_args()
    main(a.scale, Path(a.out))
