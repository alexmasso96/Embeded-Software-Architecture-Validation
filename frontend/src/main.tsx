import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./theme/macos.css";
import { initTheme } from "./theme";
import { bootstrapToken } from "./native";

// In the desktop shell, pull the session token through the pywebview bridge
// before the first API call. In a browser this resolves immediately (no-op).
bootstrapToken().then(() => {
  initTheme(); // apply persisted theme mode + accent before first paint

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
