import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./theme/macos.css";
import "./monaco"; // bundle Monaco locally (no CDN) — must run before any Editor mounts
import { initTheme } from "./theme";
import { bootstrapToken } from "./native";
import { loadPrefs } from "./prefs";

// In the desktop shell, pull the session token through the pywebview bridge
// before the first API call. In a browser this resolves immediately (no-op).
bootstrapToken()
  // Hydrate localStorage from the durable backend store (issue 6) before we read
  // any persisted setting — the desktop shell's per-launch port otherwise wipes
  // origin-scoped localStorage between sessions.
  .then(() => loadPrefs())
  .then(() => {
    initTheme(); // apply persisted theme mode + accent before first paint

    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  });
