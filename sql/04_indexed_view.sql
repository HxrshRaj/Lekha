/* Indexed view: pre-aggregated GL by period/account/cost centre. Used for the before/after measurement in
   backend/lekha/perf.py (query = P&L-style aggregation over BSEG). */
USE lekha;
GO
DROP VIEW IF EXISTS dbo.vw_GL_PeriodAccount;
GO
CREATE VIEW dbo.vw_GL_PeriodAccount WITH SCHEMABINDING AS
SELECT PERIOD, HKONT, SHKZG, COUNT_BIG(*) AS Lines, SUM(DMBTR) AS Amount
FROM dbo.BSEG
GROUP BY PERIOD, HKONT, SHKZG;
GO
CREATE UNIQUE CLUSTERED INDEX UCX_vw_GL_PeriodAccount ON dbo.vw_GL_PeriodAccount (PERIOD, HKONT, SHKZG);
GO
