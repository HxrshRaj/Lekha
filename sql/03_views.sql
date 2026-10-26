/* KPI views on the cleaned core tables. As-of date comes from dbo.Params so views stay deterministic.
   Pandas equivalents live in backend/lekha/kpis.py and are compared in tests/test_sql_vs_pandas.py. */
USE lekha;
GO
/* ---- receivables: open items and aging ---- */
CREATE OR ALTER VIEW dbo.vw_AR_Open AS
SELECT v.VBELN_VF, v.KUNNR, k.REGION, v.FKDAT, v.FAEDT, v.NETWR,
       DATEDIFF(DAY, v.FAEDT, p.AsOfDate) AS DaysOverdue,
       CASE WHEN v.FAEDT > p.AsOfDate THEN 'Current'
            WHEN DATEDIFF(DAY, v.FAEDT, p.AsOfDate) <= 30 THEN '0-30'
            WHEN DATEDIFF(DAY, v.FAEDT, p.AsOfDate) <= 60 THEN '31-60'
            WHEN DATEDIFF(DAY, v.FAEDT, p.AsOfDate) <= 90 THEN '61-90'
            ELSE '90+' END AS Bucket
FROM dbo.VBRK v
CROSS JOIN dbo.Params p
JOIN dbo.KNA1 k ON k.KUNNR = v.KUNNR
WHERE v.FKDAT <= p.AsOfDate
  AND NOT EXISTS (SELECT 1 FROM dbo.BSAD b WHERE b.VBELN_VF = v.VBELN_VF AND b.AUGDT <= p.AsOfDate);
GO
CREATE OR ALTER VIEW dbo.vw_AR_Aging AS
SELECT Bucket, COUNT(*) AS Invoices, SUM(NETWR) AS Amount,
       CAST(100.0 * SUM(NETWR) / SUM(SUM(NETWR)) OVER () AS DECIMAL(6,2)) AS PctOfOpen   -- window over the grouped result
FROM dbo.vw_AR_Open
GROUP BY Bucket;
GO
/* ---- payables aging (vendor invoices without clearing date) ---- */
CREATE OR ALTER VIEW dbo.vw_AP_Aging AS
WITH o AS (
    SELECT r.RMWWR, CASE WHEN r.FAEDT > p.AsOfDate THEN 'Current'
                         WHEN DATEDIFF(DAY, r.FAEDT, p.AsOfDate) <= 30 THEN '0-30'
                         WHEN DATEDIFF(DAY, r.FAEDT, p.AsOfDate) <= 60 THEN '31-60'
                         WHEN DATEDIFF(DAY, r.FAEDT, p.AsOfDate) <= 90 THEN '61-90' ELSE '90+' END AS Bucket
    FROM dbo.RBKP r CROSS JOIN dbo.Params p
    WHERE r.BLDAT <= p.AsOfDate AND (r.AUGDT IS NULL OR r.AUGDT > p.AsOfDate))
SELECT Bucket, COUNT(*) AS Invoices, SUM(RMWWR) AS Amount FROM o GROUP BY Bucket;
GO
/* ---- DSO: open AR at month end / credit sales of trailing 90 days * 90 ---- */
CREATE OR ALTER VIEW dbo.vw_DSO_Monthly AS
WITH months AS (SELECT DISTINCT EOMONTH(FKDAT) AS MonthEnd FROM dbo.VBRK)
SELECT m.MonthEnd, ar.OpenAR, s.Sales90,
       CAST(ar.OpenAR * 90.0 / NULLIF(s.Sales90, 0) AS DECIMAL(9,2)) AS DSO
FROM months m
CROSS APPLY (SELECT ISNULL(SUM(v.NETWR), 0) AS OpenAR FROM dbo.VBRK v
             WHERE v.FKDAT <= m.MonthEnd
               AND NOT EXISTS (SELECT 1 FROM dbo.BSAD b WHERE b.VBELN_VF = v.VBELN_VF AND b.AUGDT <= m.MonthEnd)) ar
CROSS APPLY (SELECT SUM(NETWR) AS Sales90 FROM dbo.VBRK WHERE FKDAT > DATEADD(DAY, -90, m.MonthEnd) AND FKDAT <= m.MonthEnd) s;
GO
/* ---- OTIF: on time (goods issue <= planned) AND in full (delivered qty >= ordered qty), per order ---- */
CREATE OR ALTER VIEW dbo.vw_OTIF_Order AS
SELECT a.VBELN, a.AUDAT, EOMONTH(a.AUDAT) AS OrderMonth, l.LFDAT, l.WADAT_IST,
       CASE WHEN l.WADAT_IST <= l.LFDAT THEN 1 ELSE 0 END AS OnTime,
       CASE WHEN d.QtyDel >= o.QtyOrd THEN 1 ELSE 0 END AS InFull
FROM dbo.VBAK a
JOIN dbo.LIKP l ON l.VBELN = a.VBELN
JOIN (SELECT VBELN, SUM(KWMENG) AS QtyOrd FROM dbo.VBAP GROUP BY VBELN) o ON o.VBELN = a.VBELN
JOIN (SELECT k.VBELN, SUM(i.LFIMG) AS QtyDel FROM dbo.LIKP k JOIN dbo.LIPS i ON i.VBELN_VL = k.VBELN_VL GROUP BY k.VBELN) d ON d.VBELN = a.VBELN;
GO
CREATE OR ALTER VIEW dbo.vw_OTIF_Monthly AS
SELECT OrderMonth, COUNT(*) AS Orders,
       CAST(100.0 * AVG(1.0 * OnTime) AS DECIMAL(6,2)) AS OnTimePct,
       CAST(100.0 * AVG(1.0 * InFull) AS DECIMAL(6,2)) AS InFullPct,
       CAST(100.0 * AVG(1.0 * OnTime * InFull) AS DECIMAL(6,2)) AS OTIFPct
FROM dbo.vw_OTIF_Order GROUP BY OrderMonth;
GO
/* ---- order-to-cash cycle time (paid invoices): order -> goods issue -> invoice -> payment ---- */
CREATE OR ALTER VIEW dbo.vw_CycleTime_Order AS
SELECT v.VBELN_VF, EOMONTH(a.AUDAT) AS OrderMonth,
       DATEDIFF(DAY, a.AUDAT, l.WADAT_IST) AS OrderToDelivery,
       DATEDIFF(DAY, l.WADAT_IST, v.FKDAT)  AS DeliveryToInvoice,
       DATEDIFF(DAY, v.FKDAT, b.AUGDT)      AS InvoiceToCash,
       DATEDIFF(DAY, a.AUDAT, b.AUGDT)      AS OrderToCash
FROM dbo.VBRK v
JOIN dbo.VBAK a ON a.VBELN = v.VBELN
JOIN dbo.LIKP l ON l.VBELN = v.VBELN
JOIN dbo.BSAD b ON b.VBELN_VF = v.VBELN_VF;
GO
CREATE OR ALTER VIEW dbo.vw_CycleTime_Monthly AS
SELECT DISTINCT OrderMonth,
       COUNT(*)            OVER (PARTITION BY OrderMonth) AS PaidOrders,
       AVG(1.0 * OrderToDelivery)  OVER (PARTITION BY OrderMonth) AS AvgOrderToDelivery,
       AVG(1.0 * DeliveryToInvoice) OVER (PARTITION BY OrderMonth) AS AvgDeliveryToInvoice,
       AVG(1.0 * InvoiceToCash)    OVER (PARTITION BY OrderMonth) AS AvgInvoiceToCash,
       AVG(1.0 * OrderToCash)      OVER (PARTITION BY OrderMonth) AS AvgOrderToCash,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY OrderToCash) OVER (PARTITION BY OrderMonth) AS MedianOrderToCash
FROM dbo.vw_CycleTime_Order;
GO
/* ---- budget vs actual by cost centre, with YTD running totals ---- */
CREATE OR ALTER VIEW dbo.vw_BudgetVariance AS
WITH act AS (
    SELECT s.KOSTL, s.PERIOD, SUM(CASE WHEN s.SHKZG = 'S' THEN s.DMBTR ELSE -s.DMBTR END) AS Actual
    FROM dbo.BSEG s JOIN dbo.SKA1 a ON a.HKONT = s.HKONT AND a.GRP = 'OPEX'
    WHERE s.KOSTL IS NOT NULL GROUP BY s.KOSTL, s.PERIOD),
j AS (
    SELECT b.KOSTL, b.PERIOD, ISNULL(a.Actual, 0) AS Actual, b.AMT_BUDGET AS Budget FROM dbo.BUDG b LEFT JOIN act a ON a.KOSTL = b.KOSTL AND a.PERIOD = b.PERIOD)
SELECT KOSTL, PERIOD, Actual, Budget, Actual - Budget AS Variance,
       CAST(100.0 * (Actual - Budget) / NULLIF(Budget, 0) AS DECIMAL(9,2)) AS VariancePct,
       SUM(Actual) OVER (PARTITION BY KOSTL, PERIOD / 100 ORDER BY PERIOD ROWS UNBOUNDED PRECEDING) AS YtdActual,
       SUM(Budget) OVER (PARTITION BY KOSTL, PERIOD / 100 ORDER BY PERIOD ROWS UNBOUNDED PRECEDING) AS YtdBudget
FROM j;
GO
/* ---- P&L by period from the general ledger ---- */
CREATE OR ALTER VIEW dbo.vw_PnL_Period AS
WITH g AS (
    SELECT s.PERIOD,
           SUM(CASE WHEN a.GRP = 'REV'  THEN CASE WHEN s.SHKZG = 'H' THEN s.DMBTR ELSE -s.DMBTR END ELSE 0 END) AS Revenue,
           SUM(CASE WHEN a.GRP = 'COGS' THEN CASE WHEN s.SHKZG = 'S' THEN s.DMBTR ELSE -s.DMBTR END ELSE 0 END) AS Cogs,
           SUM(CASE WHEN a.GRP = 'OPEX' THEN CASE WHEN s.SHKZG = 'S' THEN s.DMBTR ELSE -s.DMBTR END ELSE 0 END) AS Opex
    FROM dbo.BSEG s JOIN dbo.SKA1 a ON a.HKONT = s.HKONT GROUP BY s.PERIOD)
SELECT PERIOD, Revenue, Cogs, Revenue - Cogs AS GrossProfit, Opex, Revenue - Cogs - Opex AS Ebit,
       CAST(100.0 * (Revenue - Cogs) / NULLIF(Revenue, 0) AS DECIMAL(6,2)) AS GrossMarginPct,
       LAG(Revenue) OVER (ORDER BY PERIOD) AS PrevRevenue
FROM g;
GO
