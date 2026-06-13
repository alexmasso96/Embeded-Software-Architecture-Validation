import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: Vite serves the SPA and proxies /api to the FastAPI worker so the
// frontend code is identical to production (where pywebview points the window
// straight at the worker, which serves frontend/dist/ on the same origin).
const WORKER = process.env.VITE_WORKER_URL || "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: WORKER,
        changeOrigin: true,
        // SSE: the EventSource stream must not be buffered.
        configure: (proxy) => {
          proxy.on("proxyRes", (proxyRes) => {
            if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
              proxyRes.headers["cache-control"] = "no-cache";
            }
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
