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
        // Don't pool upstream sockets. The worker is restarted often in dev; a
        // kept-alive socket to a dead worker makes the proxy serve 500s (and
        // hangs SSE) until vite restarts. A fresh socket per request is cheap
        // locally and survives worker restarts. Production has no proxy.
        agent: false,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("Connection", "close");
          });
          // SSE: the EventSource stream must not be buffered.
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
