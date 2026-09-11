import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies to the backend so the browser only ever sees one
// origin -- the same arrangement production gets for free, where FastAPI
// serves the built SPA itself. VITE_API_TARGET exists because under Docker
// Compose the backend is another container ("http://api:8000"), not localhost.
const target = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target, changeOrigin: true },
      "/ws": { target: target.replace(/^http/, "ws"), ws: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
