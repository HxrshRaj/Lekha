import { AgingPanel, AnomalyPanel, CashPanel, DataQualityPanel, KpiCards, ModelsPanel, NlpPanel, PnlPanel, VariancePanel } from "./components/sections";

export default function App() {
  return (
    <div className="app">
      <header className="top">
        <div>
          <h1>Lekha</h1>
          <p>Finance and order-to-cash analytics</p>
        </div>
        <a className="btn" href="/export.xlsx" download>Download Excel</a>
      </header>
      <p className="banner" role="note">
        All data is <strong>synthetic</strong> and <strong>SAP-style</strong> (simplified table names such as VBAK, BSEG, KNA1). It is not real SAP data and nothing here is connected to an SAP system.
      </p>
      <main className="grid">
        <KpiCards />
        <AgingPanel />
        <VariancePanel />
        <CashPanel />
        <PnlPanel />
        <NlpPanel />
        <AnomalyPanel />
        <DataQualityPanel />
        <ModelsPanel />
      </main>
      <footer>
        Synthetic, SAP-style, simplified demo data · Not real SAP, not production scale · <a href="/docs">API docs</a>
      </footer>
    </div>
  );
}
