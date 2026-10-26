# Power BI readiness (Power BI was NOT used by the author)

No `.pbix` is included and none of the DAX in `measures.dax` has been run in Power BI Desktop. It is written to match the KPI
definitions that *are* tested in Python and SQL (`backend/lekha/kpis.py`, `sql/03_views.sql`). Expect to fix small syntax issues.
Data is SYNTHETIC and SAP-STYLE (simplified).

## Build it
1. `cd backend && python -m lekha.powerbi` writes the star schema to `powerbi/data/*.csv` (about 600k rows in total).
2. Power BI Desktop -> Get data -> Text/CSV -> import every CSV in `powerbi/data/`.
3. Model view -> create these relationships (many-to-one, single direction):

| From (many) | To (one) |
|---|---|
| fact_invoice[InvoiceDateKey] | dim_date[DateKey] (active) |
| fact_invoice[DueDateKey], fact_invoice[PaidDateKey] | dim_date[DateKey] (inactive; use `USERELATIONSHIP` when needed) |
| fact_invoice[KUNNR], fact_otif_order[KUNNR] | dim_customer[KUNNR] |
| fact_gl[DateKey], fact_budget[DateKey] | dim_date[DateKey] |
| fact_gl[HKONT] | dim_account[HKONT] |
| fact_gl[KOSTL], fact_budget[KOSTL] | dim_cost_centre[KOSTL] |

4. Mark `dim_date` as a date table (`Date`). Paste each measure from `measures.dax` into a "Measures" table.
5. Suggested pages: **Receivables** (Open AR, Overdue 90+ %, aging by `fact_invoice[Bucket]`, DSO by month),
   **Order to cash** (OTIF %, On Time %, In Full % by month), **Finance** (Revenue, EBIT by month, Opex budget vs actual by cost centre).
6. Cross-check three numbers against the dashboard or `backend/results/results.json`: Open AR, DSO (latest month end), OTIF %.

## Star schema
```
dim_date --+-- fact_invoice ----- dim_customer
           +-- fact_otif_order --+
           +-- fact_gl --------- dim_account, dim_cost_centre
           +-- fact_budget ----- dim_cost_centre
dim_material (product variants: BASE_MATNR + CONF_CODE) is exported for item-level extensions.
```
`fact_invoice.Bucket` and `DaysOverdue` are precomputed as of 2025-12-31, the as-of date used everywhere in Lekha.
