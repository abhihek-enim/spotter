/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the Django API runs on :8000; the browser only ever talks to /api on this origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  // MapLibre is one ~1 MB library in its own chunk (285 KB gzipped); nothing to split further.
  build: { chunkSizeWarningLimit: 1100 },
  test: { environment: "node" },
});
