import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./theme/macos.css";
import { initTheme } from "./theme";

initTheme(); // apply persisted theme mode + accent before first paint

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
