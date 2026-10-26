import { useCallback, useEffect, useState } from "react";

export interface Kpis {
  as_of: string; open_ar: number; overdue_90_plus: number; dso_latest: number; otif_pct: number; on_time_pct: number;
  in_full_pct: number; avg_order_to_cash_days: number; median_order_to_cash_days: number; revenue_ltm: number;
  ebit_ltm: number; gross_margin_ltm_pct: number;
}
export interface AgingRow { Bucket: string; Invoices: number; Amount: number; PctOfOpen?: number }
export interface Aging { receivables: AgingRow[]; payables: AgingRow[] }
export interface VarianceRow { KOSTL: string; PERIOD: number; Actual: number; Budget: number; Variance: number; VariancePct: number | null }
export interface Variance { period: number; rows: VarianceRow[] }
export interface PnlRow { PERIOD: number; Revenue: number; Cogs: number; Opex: number; GrossProfit: number; Ebit: number; GrossMarginPct: number | null }
export interface BacktestModel { model: string; wape: number; mape: number; bias: number }
export interface ForecastSeries {
  backtest: { models: BacktestModel[]; best: string; folds: number; horizon_weeks: number; naive_wape: number };
  history: { week_end: string; actual: number }[];
  forecast_model: string;
  forecast: { week_end: string; forecast: number }[];
}
export interface Forecast { cash_in_usd: ForecastSeries; demand_units: ForecastSeries }
export interface SimWeek { week: number; p5: number; p50: number; p95: number }
export interface Convergence { runs: number; mean?: number; std_error: number; p_stockout?: number }
export interface Simulation {
  cash_collection: {
    runs: number; seed: number; horizon_days: number; open_ar: number; open_invoices: number;
    total_cash_in: { mean: number; p5: number; p50: number; p95: number; pct_of_open_ar_p50: number };
    weekly: SimWeek[]; convergence: Convergence[]; caveat: string;
  };
  safety_stock: {
    runs: number; seed: number; service_level: number;
    materials: { material: string; lead_time_mean_days: number; daily_demand_mean: number; safety_stock_analytic: number; safety_stock_simulated: number;
      reorder_point_simulated: number; stockout_prob_at_analytic_rop: number }[];
  };
}
export interface NlpMetrics {
  accuracy: number; macro_f1: number; n_test: number;
  per_class: { class: string; precision: number; recall: number; f1: number; support: number }[];
  confusion_matrix: { labels: string[]; matrix: number[][] };
}
export interface Classification { label: string; confidence: number; scores: { label: string; probability: number }[] }
export interface AnomalyItem { VBELN_VF: string; KUNNR: string; FKDAT: string; NETWR: number; match_ratio: number; flag_z: boolean; flag_iqr: boolean; flag_iso: boolean; flag_match: boolean; injected: boolean }
export interface Anomalies {
  summary: { injected_in_clean_data: number; evaluation: Record<string, { flagged: number; true_positives: number; recall: number; precision: number }> };
  items: AnomalyItem[];
}
export interface DataQuality {
  total_staging_rows: number; total_quarantined: number; quarantine_pct: number; injected_pct: number; by_reason: Record<string, number>; note: string;
  tables: ({ table: string; staging_rows: number; quarantined: number; quarantine_pct: number } & Record<string, number | string>)[];
}
export interface Regression {
  ols: { r2: number; adj_r2: number; coefficients: { term: string; coef: number; p_value: number }[] };
  holdout: Record<string, { mae: number; rmse: number; r2: number }>; n_train: number; n_test: number; note: string;
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return (await r.json()) as T;
}

export async function classifyText(text: string): Promise<Classification> {
  const r = await fetch("/api/nlp/classify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!r.ok) throw new Error(r.status === 422 ? "Please enter at least a few words." : `Request failed (HTTP ${r.status})`);
  return (await r.json()) as Classification;
}

export interface State<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

export function useApi<T>(url: string): State<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    get<T>(url)
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [url, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
