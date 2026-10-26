import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine; Recharts' ResponsiveContainer needs ResizeObserver.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub;
