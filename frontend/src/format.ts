const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

export const money = (n: number) => usd0.format(n);
export const moneyShort = (n: number) => compact.format(n);
export const pct = (n: number, d = 1) => `${n.toFixed(d)}%`;
export const num = (n: number, d = 0) => n.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
/** 202512 -> "2025-12" */
export const period = (p: number) => `${Math.floor(p / 100)}-${String(p % 100).padStart(2, "0")}`;
