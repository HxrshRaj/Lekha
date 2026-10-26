# Indexed view: measured before / after

Run on `Microsoft SQL Server 2022 (RTM-CU27-GDR) (KB5126934) - 16.0.4305.5 (X64) `, scale 1.0, `dbo.BSEG` = 178,262 rows, warm cache, 30 runs per query (python `-m lekha.perf`).

Query: GL amount by period and account (the aggregation under the P&L).

| | Base table scan + aggregate | Indexed view `vw_GL_PeriodAccount` (`NOEXPAND`) |
|---|---|---|
| median time | 96.5 ms | 12.7 ms |
| p90 time | 138.3 ms | 15.7 ms |
| logical reads | 1,499 | 4 |
| rows returned | 396 | 396 |

Speed-up (median): 7.6x; logical reads reduced 374.8x.

## Plan: base table
```
  |--Sort(ORDER BY:([lekha].[dbo].[BSEG].[PERIOD] ASC, [lekha].[dbo].[BSEG].[HKONT] ASC))
       |--Hash Match(Aggregate, HASH:([lekha].[dbo].[BSEG].[PERIOD], [lekha].[dbo].[BSEG].[HKONT]), RESIDUAL:([lekha].[dbo].[BSEG].[PERIOD] = [lekha].[dbo].[BSEG].[PERIOD] AND [lekha].[dbo].[BSEG].[HKONT] = [lekha].[dbo].[BSEG].[HKONT]) DEFINE:([Expr1002]=SUM([Expr1003])))
            |--Compute Scalar(DEFINE:([Expr1003]=CASE WHEN [lekha].[dbo].[BSEG].[SHKZG]='S' THEN [lekha].[dbo].[BSEG].[DMBTR] ELSE  -[lekha].[dbo].[BSEG].[DMBTR] END))
                 |--Clustered Index Scan(OBJECT:([lekha].[dbo].[BSEG].[PK__BSEG__2E068344A5779996]))
```
## Plan: indexed view
```
  |--Compute Scalar(DEFINE:([Expr1002]=CASE WHEN [Expr1008]=(0) THEN NULL ELSE [Expr1009] END))
       |--Stream Aggregate(GROUP BY:([lekha].[dbo].[vw_GL_PeriodAccount].[PERIOD], [lekha].[dbo].[vw_GL_PeriodAccount].[HKONT]) DEFINE:([Expr1008]=COUNT_BIG([Expr1003]), [Expr1009]=SUM([Expr1003])))
            |--Compute Scalar(DEFINE:([Expr1003]=CASE WHEN [lekha].[dbo].[vw_GL_PeriodAccount].[SHKZG]='S' THEN [lekha].[dbo].[vw_GL_PeriodAccount].[Amount] ELSE  -[lekha].[dbo].[vw_GL_PeriodAccount].[Amount] END))
                 |--Clustered Index Scan(OBJECT:([lekha].[dbo].[vw_GL_PeriodAccount].[UCX_vw_GL_PeriodAccount]), ORDERED FORWARD)
```
The indexed view has a unique clustered index on (PERIOD, HKONT, SHKZG), maintained on every write to `BSEG`
(a write-cost trade-off; fine for a mostly-append ledger, not free for heavy OLTP).
