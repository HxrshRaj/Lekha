const weekly = Array.from({ length: 13 }, (_, i) => ({ week: i + 1, p5: 100000, p50: 150000, p95: 200000 }));
const hist = Array.from({ length: 52 }, (_, i) => ({
  week_end: `2025-${String(Math.min(12, 1 + Math.floor(i / 5))).padStart(2, "0")}-${String(1 + (i % 5) * 5).padStart(2, "0")}`,
  actual: 200000 + i * 100,
}));
const series = {
  backtest: {
    models: [{ model: "gbm", wape: 0.1, mape: 0.1, bias: 0 }, { model: "naive", wape: 0.113, mape: 0.116, bias: 0 }],
    best: "gbm", folds: 11, horizon_weeks: 4, naive_wape: 0.113,
  },
  history: hist,
  forecast_model: "gbm",
  forecast: Array.from({ length: 13 }, (_, i) => ({ week_end: `2026-01-${String(4 + i).padStart(2, "0")}`, forecast: 210000 })),
};

export const fixtures = {
  "/api/kpis": {
    as_of: "2025-12-31", open_ar: 3000000, overdue_90_plus: 800000, dso_latest: 74.5, otif_pct: 73.1, on_time_pct: 82.4, in_full_pct: 88.5,
    avg_order_to_cash_days: 53.3, median_order_to_cash_days: 52, revenue_ltm: 12900000, ebit_ltm: 830000, gross_margin_ltm_pct: 34,
  },
  "/api/aging": {
    receivables: [
      { Bucket: "Current", Invoices: 900, Amount: 1000000, PctOfOpen: 33.3 },
      { Bucket: "90+", Invoices: 300, Amount: 800000, PctOfOpen: 26.7 },
    ],
    payables: [],
  },
  "/api/variance": { period: 202512, rows: [{ KOSTL: "CC001", PERIOD: 202512, Actual: 5200, Budget: 4800, Variance: 400, VariancePct: 8.33 }] },
  "/api/pnl": Array.from({ length: 24 }, (_, i) => ({
    PERIOD: i < 12 ? 202401 + i : 202501 + (i - 12), Revenue: 1000000, Cogs: 650000, Opex: 250000, GrossProfit: 350000, Ebit: 100000, GrossMarginPct: 35,
  })),
  "/api/forecast": { cash_in_usd: series, demand_units: series },
  "/api/simulation": {
    cash_collection: {
      runs: 5000, seed: 7, horizon_days: 90, open_ar: 3000000, open_invoices: 2500,
      total_cash_in: { mean: 2000000, p5: 1830000, p50: 2030000, p95: 2060000, pct_of_open_ar_p50: 67.7 },
      weekly,
      convergence: [{ runs: 100, mean: 2001000, std_error: 2000 }, { runs: 1000, mean: 2000500, std_error: 600 }],
      caveat: "",
    },
    safety_stock: {
      runs: 20000, seed: 11, service_level: 0.95,
      materials: [{ material: "B0004-BLU-L", lead_time_mean_days: 34, daily_demand_mean: 17.8, safety_stock_analytic: 368, safety_stock_simulated: 410, reorder_point_simulated: 1014, stockout_prob_at_analytic_rop: 0.065 }],
    },
  },
  "/api/regression": {
    ols: { r2: 0.82, adj_r2: 0.82, coefficients: [{ term: "dispute", coef: 7.97, p_value: 0 }] },
    holdout: { ols: { mae: 4.5, rmse: 5.8, r2: 0.83 }, gbm: { mae: 4.3, rmse: 5.6, r2: 0.85 } },
    n_train: 17000, n_test: 7000, note: "synthetic regime change",
  },
  "/api/nlp/metrics": {
    accuracy: 0.89, macro_f1: 0.88, n_test: 610,
    per_class: [{ class: "pricing_error", precision: 0.91, recall: 0.94, f1: 0.93, support: 124 }],
    confusion_matrix: { labels: ["pricing_error"], matrix: [[124]] },
  },
  "/api/anomalies": {
    summary: {
      injected_in_clean_data: 298,
      evaluation: {
        flagged: { flagged: 911, true_positives: 280, recall: 0.94, precision: 0.31 },
        flag_z: { flagged: 32, true_positives: 13, recall: 0.044, precision: 0.4 },
      },
    },
    items: [{ VBELN_VF: "0009000123", KUNNR: "0000100001", FKDAT: "2024-05-01", NETWR: 9000, match_ratio: 6.2, flag_z: true, flag_iqr: false, flag_iso: true, flag_match: true, injected: true }],
  },
  "/api/data-quality": {
    total_staging_rows: 1000, total_quarantined: 21, quarantine_pct: 2.1, injected_pct: 2.0, note: "", by_reason: { NULL_REQUIRED: 5, DUPLICATE_KEY: 10 },
    tables: [{ table: "VBAK", staging_rows: 500, quarantined: 10, quarantine_pct: 2 }],
  },
  classify: { label: "duplicate_invoice", confidence: 0.91, scores: [{ label: "duplicate_invoice", probability: 0.91 }, { label: "pricing_error", probability: 0.05 }] },
} as const;
