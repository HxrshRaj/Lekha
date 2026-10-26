import { useMemo, useState } from "react";
import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  classifyText, useApi,
  type Aging, type Anomalies, type Classification, type DataQuality, type Forecast, type Kpis, type NlpMetrics,
  type PnlRow, type Regression, type Simulation, type Variance,
} from "../api";
import { money, moneyShort, num, pct, period } from "../format";
import { Panel } from "./Panel";

const axis = { stroke: "var(--muted)", fontSize: 12 } as const;

export function KpiCards() {
  const s = useApi<Kpis>("/api/kpis");
  return (
    <Panel title="Key figures" subtitle={s.data ? `As of ${s.data.as_of} · last-twelve-month (LTM) figures use the final 12 periods` : undefined} state={s} wide>
      {(k) => (
        <div className="kpis">
          <Kpi label="Open receivables" value={money(k.open_ar)} />
          <Kpi label="Overdue 90+ days" value={money(k.overdue_90_plus)} tone="bad" hint={`${pct((100 * k.overdue_90_plus) / k.open_ar)} of open AR`} />
          <Kpi label="DSO (latest month)" value={`${num(k.dso_latest, 1)} days`} />
          <Kpi label="OTIF" value={pct(k.otif_pct)} hint={`on time ${pct(k.on_time_pct)} · in full ${pct(k.in_full_pct)}`} />
          <Kpi label="Order-to-cash" value={`${num(k.avg_order_to_cash_days, 1)} days`} hint={`median ${num(k.median_order_to_cash_days)}`} />
          <Kpi label="Revenue (LTM)" value={moneyShort(k.revenue_ltm)} />
          <Kpi label="EBIT (LTM)" value={moneyShort(k.ebit_ltm)} tone={k.ebit_ltm < 0 ? "bad" : undefined} />
          <Kpi label="Gross margin (LTM)" value={pct(k.gross_margin_ltm_pct)} />
        </div>
      )}
    </Panel>
  );
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "bad" }) {
  return (
    <div className={`kpi${tone ? " " + tone : ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {hint && <div className="kpi-hint">{hint}</div>}
    </div>
  );
}

export function AgingPanel() {
  const s = useApi<Aging>("/api/aging");
  return (
    <Panel title="Receivables aging" subtitle="Open invoices by days past due date" state={s} isEmpty={(d) => d.receivables.length === 0} emptyText="No open receivables.">
      {(d) => (
        <>
          <div className="chart" role="img" aria-label="Bar chart of open receivables by aging bucket">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={d.receivables} margin={{ left: 8, right: 8 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="Bucket" {...axis} />
                <YAxis tickFormatter={moneyShort} {...axis} width={56} />
                <Tooltip formatter={(v: number) => money(v)} />
                <Bar dataKey="Amount" fill="var(--c1)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table>
            <thead><tr><th>Bucket</th><th className="r">Invoices</th><th className="r">Amount</th><th className="r">Share</th></tr></thead>
            <tbody>
              {d.receivables.map((r) => (
                <tr key={r.Bucket}><td>{r.Bucket}</td><td className="r">{num(r.Invoices)}</td><td className="r">{money(r.Amount)}</td><td className="r">{pct(r.PctOfOpen ?? 0)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Panel>
  );
}

export function CashPanel() {
  const f = useApi<Forecast>("/api/forecast");
  const sim = useApi<Simulation>("/api/simulation");
  const state = { data: f.data && sim.data ? { f: f.data, sim: sim.data } : null, loading: f.loading || sim.loading, error: f.error || sim.error, reload: () => { f.reload(); sim.reload(); } };
  return (
    <Panel title="Cash-in forecast" subtitle="Weekly cash receipts: history, model forecast, and Monte Carlo range for today's open invoices" state={state} wide>
      {({ f, sim }) => {
        const c = f.cash_in_usd;
        const hist = c.history.slice(-26).map((h) => ({ week: h.week_end, actual: h.actual }));
        const fc = c.forecast.map((x, i) => ({
          week: x.week_end, forecast: x.forecast,
          p5: sim.cash_collection.weekly[i]?.p5, p50: sim.cash_collection.weekly[i]?.p50, p95: sim.cash_collection.weekly[i]?.p95,
          band: sim.cash_collection.weekly[i] ? [sim.cash_collection.weekly[i].p5, sim.cash_collection.weekly[i].p95] : undefined,
        }));
        const data = [...hist, ...fc];
        const cc = sim.cash_collection;
        const best = c.backtest.models[0];
        return (
          <div className="two">
            <div>
              <div className="chart" role="img" aria-label="Line chart of weekly cash in with forecast and simulation range">
                <ResponsiveContainer width="100%" height={280}>
                  <ComposedChart data={data} margin={{ left: 8, right: 8 }}>
                    <CartesianGrid stroke="var(--grid)" vertical={false} />
                    <XAxis dataKey="week" {...axis} tickFormatter={(d: string) => d.slice(5)} minTickGap={24} />
                    <YAxis tickFormatter={moneyShort} {...axis} width={56} />
                    <Tooltip formatter={(v: number | number[]) => (Array.isArray(v) ? `${money(v[0])} – ${money(v[1])}` : money(v))} />
                    <Legend />
                    <Area dataKey="band" name="Simulated range (p5–p95, open invoices only)" fill="var(--c3)" fillOpacity={0.25} stroke="none" />
                    <Line dataKey="actual" name="Actual" stroke="var(--c1)" dot={false} strokeWidth={2} />
                    <Line dataKey="forecast" name={`Forecast (${c.forecast_model})`} stroke="var(--c2)" strokeDasharray="5 4" dot={false} strokeWidth={2} />
                    <Line dataKey="p50" name="Simulated median" stroke="var(--c3)" dot={false} strokeWidth={1.5} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <p className="note">The model forecast covers all future cash; the simulated band covers only invoices already open at the as-of date, so it sits below the forecast by design.</p>
            </div>
            <div>
              <h3>90-day simulated collections</h3>
              <p className="big">{moneyShort(cc.total_cash_in.p5)} – {moneyShort(cc.total_cash_in.p95)}</p>
              <p className="note">median {moneyShort(cc.total_cash_in.p50)} ({pct(cc.total_cash_in.pct_of_open_ar_p50, 0)} of {moneyShort(cc.open_ar)} open AR) · {num(cc.runs)} runs · seed {cc.seed}</p>
              <h3>Backtest vs baselines</h3>
              <table>
                <thead><tr><th>Model</th><th className="r">WAPE</th><th className="r">MAPE</th></tr></thead>
                <tbody>
                  {c.backtest.models.map((m) => (
                    <tr key={m.model} className={m.model === best.model ? "hl" : ""}><td>{m.model}</td><td className="r">{pct(100 * m.wape)}</td><td className="r">{pct(100 * m.mape)}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="note">Rolling-origin, {c.backtest.folds} folds, {c.backtest.horizon_weeks}-week horizon.{best.model === "naive" ? " The naive baseline wins." : ` Best: ${best.model}; naive WAPE ${pct(100 * c.backtest.naive_wape)}.`}</p>
            </div>
          </div>
        );
      }}
    </Panel>
  );
}

export function VariancePanel() {
  const s = useApi<Variance>("/api/variance");
  return (
    <Panel title="Budget vs actual" subtitle={s.data ? `Cost centres, period ${period(s.data.period)} · largest variances first` : undefined} state={s} isEmpty={(d) => d.rows.length === 0} emptyText="No variance rows for this period.">
      {(d) => (
        <div className="scroll">
          <table>
            <thead><tr><th>Cost centre</th><th className="r">Actual</th><th className="r">Budget</th><th className="r">Variance</th><th className="r">%</th></tr></thead>
            <tbody>
              {d.rows.slice(0, 10).map((r) => (
                <tr key={r.KOSTL}>
                  <td>{r.KOSTL}</td><td className="r">{money(r.Actual)}</td><td className="r">{money(r.Budget)}</td>
                  <td className={`r ${r.Variance > 0 ? "bad" : "good"}`}>{money(r.Variance)}</td>
                  <td className={`r ${Math.abs(r.VariancePct ?? 0) > 10 ? "bad" : ""}`}>{r.VariancePct == null ? "–" : pct(r.VariancePct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="note">Positive variance = overspend. Showing top 10 of {d.rows.length} cost centres.</p>
        </div>
      )}
    </Panel>
  );
}

export function PnlPanel() {
  const s = useApi<PnlRow[]>("/api/pnl");
  const rows = useMemo(() => (s.data ?? []).slice(-24).map((r) => ({ ...r, label: period(r.PERIOD) })), [s.data]);
  return (
    <Panel title="Profit and loss" subtitle="Monthly, from the general ledger (last 24 periods)" state={s} isEmpty={(d) => d.length === 0} emptyText="No ledger postings.">
      {() => (
        <>
          <div className="chart" role="img" aria-label="Chart of monthly revenue, gross profit and EBIT">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={rows} margin={{ left: 8, right: 8 }}>
                <CartesianGrid stroke="var(--grid)" vertical={false} />
                <XAxis dataKey="label" {...axis} minTickGap={20} />
                <YAxis tickFormatter={moneyShort} {...axis} width={56} />
                <Tooltip formatter={(v: number) => money(v)} />
                <Legend />
                <Bar dataKey="Revenue" fill="var(--c1)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="GrossProfit" name="Gross profit" fill="var(--c2)" radius={[3, 3, 0, 0]} />
                <Line dataKey="Ebit" name="EBIT" stroke="var(--c4)" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="scroll">
            <table>
              <thead><tr><th>Period</th><th className="r">Revenue</th><th className="r">COGS</th><th className="r">Opex</th><th className="r">EBIT</th><th className="r">GM%</th></tr></thead>
              <tbody>
                {rows.slice(-6).reverse().map((r) => (
                  <tr key={r.PERIOD}><td>{r.label}</td><td className="r">{money(r.Revenue)}</td><td className="r">{money(r.Cogs)}</td><td className="r">{money(r.Opex)}</td>
                    <td className={`r ${r.Ebit < 0 ? "bad" : ""}`}>{money(r.Ebit)}</td><td className="r">{r.GrossMarginPct == null ? "–" : pct(r.GrossMarginPct)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

const EXAMPLES = [
  "We were billed twice for the same order, please cancel the duplicate invoice",
  "Only 40 units arrived but the invoice charges for the full quantity",
  "Bank transfer was sent last week but the payment still shows as open",
];

export function NlpPanel() {
  const metrics = useApi<NlpMetrics>("/api/nlp/metrics");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<Classification | null>(null);
  const submit = async () => {
    setBusy(true); setErr(null);
    try { setRes(await classifyText(text.trim())); } catch (e) { setErr((e as Error).message); setRes(null); } finally { setBusy(false); }
  };
  return (
    <Panel title="Dispute text classifier" subtitle="TF-IDF + logistic regression, trained on synthetic template text" state={metrics}>
      {(m) => (
        <>
          <label htmlFor="nlp-text" className="sr">Dispute or ticket text</label>
          <textarea id="nlp-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste an invoice dispute or ticket description…" />
          <div className="row">
            <button onClick={submit} disabled={busy || text.trim().length < 3}>{busy ? "Classifying…" : "Classify"}</button>
            {EXAMPLES.map((x, i) => <button key={i} className="ghost" onClick={() => setText(x)}>Example {i + 1}</button>)}
          </div>
          {err && <div className="status error" role="alert"><p>{err}</p><button onClick={submit}>Retry</button></div>}
          {res && (
            <div className="result" aria-live="polite">
              <p><strong>{res.label.replace(/_/g, " ")}</strong> · confidence {pct(100 * res.confidence, 0)}</p>
              {res.scores.slice(0, 4).map((s) => (
                <div className="bar" key={s.label}><span>{s.label.replace(/_/g, " ")}</span><div><i style={{ width: `${100 * s.probability}%` }} /></div><span>{pct(100 * s.probability, 0)}</span></div>
              ))}
            </div>
          )}
          <details>
            <summary>Held-out metrics: accuracy {pct(100 * m.accuracy)}, macro F1 {m.macro_f1.toFixed(2)} (n={m.n_test}, synthetic text, optimistic)</summary>
            <div className="scroll">
              <table>
                <thead><tr><th>Class</th><th className="r">Precision</th><th className="r">Recall</th><th className="r">F1</th><th className="r">n</th></tr></thead>
                <tbody>{m.per_class.map((c) => <tr key={c.class}><td>{c.class}</td><td className="r">{c.precision.toFixed(2)}</td><td className="r">{c.recall.toFixed(2)}</td><td className="r">{c.f1.toFixed(2)}</td><td className="r">{c.support}</td></tr>)}</tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </Panel>
  );
}

export function AnomalyPanel() {
  const s = useApi<Anomalies>("/api/anomalies?kind=invoices&limit=15");
  return (
    <Panel title="Anomalous invoices" subtitle="Invoice value vs delivered quantity × order price (3-way match), plus z-score and isolation forest" state={s} isEmpty={(d) => d.items.length === 0} emptyText="No anomalies flagged.">
      {(d) => {
        const ev = d.summary.evaluation;
        return (
          <>
            <p className="note">Recovered {ev.flagged.true_positives} of {d.summary.injected_in_clean_data} injected anomalies (recall {pct(100 * ev.flagged.recall, 0)}, precision {pct(100 * ev.flagged.precision, 0)}). Amount-only z-score recall: {pct(100 * ev.flag_z.recall, 0)}.</p>
            <div className="scroll">
              <table>
                <thead><tr><th>Invoice</th><th>Date</th><th className="r">Amount</th><th className="r">vs expected</th><th>Flags</th></tr></thead>
                <tbody>
                  {d.items.map((a) => (
                    <tr key={a.VBELN_VF}>
                      <td>{a.VBELN_VF}</td><td>{a.FKDAT}</td><td className="r">{money(a.NETWR)}</td><td className="r">{a.match_ratio.toFixed(2)}×</td>
                      <td>{[a.flag_match && "3-way", a.flag_z && "z", a.flag_iso && "iso"].filter(Boolean).join(" · ") || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        );
      }}
    </Panel>
  );
}

export function DataQualityPanel() {
  const s = useApi<DataQuality>("/api/data-quality");
  return (
    <Panel title="Data quality" subtitle="Staging → core cleaning; rejected rows go to a quarantine table with the reason" state={s} isEmpty={(d) => d.tables.length === 0}>
      {(d) => (
        <>
          <p><strong>{num(d.total_quarantined)}</strong> of {num(d.total_staging_rows)} staging rows quarantined ({pct(d.quarantine_pct)}); about {pct(d.injected_pct)} were injected defects, the rest are orphan cascades.</p>
          <div className="reasons">{Object.entries(d.by_reason).map(([k, v]) => <span key={k} className="chip">{k.replace(/_/g, " ").toLowerCase()}: {num(v)}</span>)}</div>
          <div className="scroll">
            <table>
              <thead><tr><th>Table</th><th className="r">Rows</th><th className="r">Quarantined</th><th className="r">%</th></tr></thead>
              <tbody>{d.tables.map((t) => <tr key={t.table}><td>{t.table}</td><td className="r">{num(t.staging_rows)}</td><td className="r">{num(t.quarantined)}</td><td className="r">{pct(t.quarantine_pct)}</td></tr>)}</tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}

export function ModelsPanel() {
  const r = useApi<Regression>("/api/regression");
  const sim = useApi<Simulation>("/api/simulation");
  return (
    <>
      <Panel title="Days-to-pay regression" subtitle="OLS (interpretation) and gradient boosting, time-based holdout" state={r}>
        {(d) => (
          <>
            <p className="note">OLS R² {d.ols.r2.toFixed(3)} (train, n={num(d.n_train)}). Holdout n={num(d.n_test)}:</p>
            <table>
              <thead><tr><th>Model</th><th className="r">MAE (days)</th><th className="r">R²</th></tr></thead>
              <tbody>{Object.entries(d.holdout).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td className="r">{v.mae.toFixed(2)}</td><td className="r">{v.r2.toFixed(2)}</td></tr>)}</tbody>
            </table>
            <details><summary>OLS coefficients</summary>
              <div className="scroll"><table>
                <thead><tr><th>Term</th><th className="r">Coef</th><th className="r">p</th></tr></thead>
                <tbody>{d.ols.coefficients.map((c) => <tr key={c.term}><td>{c.term}</td><td className="r">{c.coef.toFixed(2)}</td><td className="r">{c.p_value < 0.001 ? "<0.001" : c.p_value.toFixed(3)}</td></tr>)}</tbody>
              </table></div>
            </details>
            <p className="note">{d.note}</p>
          </>
        )}
      </Panel>
      <Panel title="Safety stock simulation" subtitle="Monte Carlo of demand during lead time (95% service target)" state={sim}>
        {(d) => (
          <>
            <div className="scroll"><table>
              <thead><tr><th>Material</th><th className="r">Lead (d)</th><th className="r">Safety stock: formula</th><th className="r">simulated</th><th className="r">Stock-out risk at formula ROP</th></tr></thead>
              <tbody>{d.safety_stock.materials.map((m) => (
                <tr key={m.material}><td>{m.material}</td><td className="r">{m.lead_time_mean_days.toFixed(1)}</td><td className="r">{num(m.safety_stock_analytic)}</td><td className="r">{num(m.safety_stock_simulated)}</td><td className="r">{pct(100 * m.stockout_prob_at_analytic_rop)}</td></tr>
              ))}</tbody>
            </table></div>
            <p className="note">{num(d.safety_stock.runs)} runs, seed {d.safety_stock.seed}. The normal-approximation formula under-protects skewed demand: observed stock-out risk exceeds the 5% target.</p>
            <div className="chart" role="img" aria-label="Convergence of simulated mean cash collected as runs increase">
              <ResponsiveContainer width="100%" height={130}>
                <LineChart data={d.cash_collection.convergence} margin={{ left: 8, right: 8 }}>
                  <XAxis dataKey="runs" scale="log" type="number" domain={["dataMin", "dataMax"]} {...axis} />
                  <YAxis tickFormatter={moneyShort} {...axis} width={56} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v: number) => money(v)} />
                  <Line dataKey="mean" name="Mean cash-in (90d)" stroke="var(--c1)" dot />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="note">Convergence of the 90-day cash-in mean vs number of runs.</p>
          </>
        )}
      </Panel>
    </>
  );
}
