/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000", "/export.xlsx": "http://localhost:8000" } },
  build: { outDir: "dist", chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"], css: false },
});
