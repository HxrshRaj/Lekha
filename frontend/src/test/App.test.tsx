import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { fixtures } from "./fixtures";

type Reply = { status?: number; body: unknown };
type Route = (url: string, init?: RequestInit) => Reply;

function mockFetch(route: Route) {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const { status = 200, body } = route(url, init);
    return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
  }));
}

const ok: Route = (url) => {
  const path = url.split("?")[0];
  if (path in fixtures) return { body: (fixtures as Record<string, unknown>)[path] };
  return { status: 404, body: {} };
};

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("dashboard", () => {
  it("shows the synthetic / SAP-style disclaimer and footer", async () => {
    mockFetch(ok);
    render(<App />);
    expect(screen.getByRole("note")).toHaveTextContent(/synthetic/i);
    expect(screen.getByRole("note")).toHaveTextContent(/not real SAP data/i);
    expect(document.querySelector("footer")).toHaveTextContent(/Not real SAP/);
    await waitFor(() => expect(screen.getByText("Open receivables")).toBeInTheDocument());
  });

  it("shows loading state first, then KPI values", async () => {
    mockFetch(ok);
    render(<App />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("Open receivables")).toBeInTheDocument());
    expect(screen.getByText("$3,000,000")).toBeInTheDocument();
    expect(screen.getByText("73.1%")).toBeInTheDocument();
  });

  it("shows an error with a working Retry button", async () => {
    let calls = 0;
    mockFetch((url, init) => {
      if (url === "/api/kpis") { calls += 1; return calls === 1 ? { status: 500, body: {} } : ok(url, init); }
      return ok(url, init);
    });
    render(<App />);
    expect(await screen.findByText(/Could not load key figures/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]);
    await waitFor(() => expect(screen.getByText("Open receivables")).toBeInTheDocument());
    expect(calls).toBe(2);
  });

  it("shows an empty state when there are no anomalies", async () => {
    mockFetch((url, init) => url.startsWith("/api/anomalies")
      ? { body: { summary: fixtures["/api/anomalies"].summary, items: [] } } : ok(url, init));
    render(<App />);
    expect(await screen.findByText("No anomalies flagged.")).toBeInTheDocument();
  });

  it("renders variance, anomaly and data-quality tables", async () => {
    mockFetch(ok);
    render(<App />);
    expect(await screen.findByText("CC001")).toBeInTheDocument();
    expect(await screen.findByText("0009000123")).toBeInTheDocument();
    expect(await screen.findByText(/quarantined \(2\.1%\)/)).toBeInTheDocument();
    expect(screen.getAllByText("90+").length).toBeGreaterThan(0);
  });

  it("classifies pasted text and shows the label", async () => {
    mockFetch((url, init) => (init?.method === "POST" ? { body: fixtures.classify } : ok(url, init)));
    render(<App />);
    const box = await screen.findByPlaceholderText(/Paste an invoice dispute/);
    const btn = screen.getByRole("button", { name: "Classify" });
    expect(btn).toBeDisabled();
    fireEvent.change(box, { target: { value: "billed twice for the same order" } });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect((await screen.findAllByText("duplicate invoice")).length).toBeGreaterThan(0);
    expect(screen.getByText(/confidence 91%/)).toBeInTheDocument();
  });

  it("shows an error when classification fails", async () => {
    mockFetch((url, init) => (init?.method === "POST" ? { status: 503, body: {} } : ok(url, init)));
    render(<App />);
    const box = await screen.findByPlaceholderText(/Paste an invoice dispute/);
    fireEvent.change(box, { target: { value: "damaged goods on arrival" } });
    fireEvent.click(screen.getByRole("button", { name: "Classify" }));
    expect(await screen.findByText(/Request failed \(HTTP 503\)/)).toBeInTheDocument();
  });

  it("offers the Excel export", async () => {
    mockFetch(ok);
    render(<App />);
    expect(screen.getByRole("link", { name: "Download Excel" })).toHaveAttribute("href", "/export.xlsx");
  });
});
