// Theme mode + accent colour: applied to <html> and persisted in localStorage,
// then mirrored to the durable backend store (issue 6) so it survives the
// desktop shell's per-launch port change. Mode "auto" tracks the OS via
// prefers-color-scheme. Accent overrides the --accent / --v-accent CSS vars.

import { persistKey } from "./prefs";

export type ThemeMode = "light" | "dark" | "auto";

const MODE_KEY = "arch.theme.mode";
const ACCENT_KEY = "arch.theme.accent";

export interface AccentPreset {
  key: string;
  color: string;
  label: string; // Linux-distro joke names (shown as tooltips)
}

// Pills show the colour visually, so labels live only in tooltips.
export const ACCENTS: AccentPreset[] = [
  { key: "fedora", color: "#0a60ff", label: "Perfect Fedora" },
  { key: "ubuntu", color: "#e95420", label: "Bloated Ubuntu" },
  { key: "mint", color: "#3eb489", label: "Fresh Mint" },
  { key: "redhat", color: "#ee0000", label: "Corporate Red Hat" },
  { key: "bazzite", color: "#c026d3", label: "Gamer Mode Bazzite" },
  { key: "arch", color: "#1793d1", label: "Elitist Arch" },
];
export const DEFAULT_ACCENT = ACCENTS[0].color;

let media: MediaQueryList | null = null;

export function getMode(): ThemeMode {
  const v = localStorage.getItem(MODE_KEY);
  return v === "light" || v === "dark" || v === "auto" ? v : "auto";
}

export function getAccent(): string {
  return localStorage.getItem(ACCENT_KEY) || DEFAULT_ACCENT;
}

function effective(mode: ThemeMode): "light" | "dark" {
  if (mode === "auto") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return mode;
}

export function applyMode(mode: ThemeMode): void {
  localStorage.setItem(MODE_KEY, mode);
  persistKey(MODE_KEY, mode);
  document.documentElement.setAttribute("data-theme", effective(mode));

  // Track the system theme only while in "auto".
  if (media) media.onchange = null;
  if (mode === "auto") {
    media = window.matchMedia("(prefers-color-scheme: dark)");
    media.onchange = () => {
      if (getMode() === "auto") {
        document.documentElement.setAttribute("data-theme", effective("auto"));
      }
    };
  }
}

export function applyAccent(color: string): void {
  localStorage.setItem(ACCENT_KEY, color);
  persistKey(ACCENT_KEY, color);
  const root = document.documentElement;
  root.style.setProperty("--accent", color);
  root.style.setProperty("--v-accent", color);
}

// Is the current accent one of the presets, or a custom hex?
export function isCustomAccent(color: string): boolean {
  return !ACCENTS.some((a) => a.color.toLowerCase() === color.toLowerCase());
}

export function initTheme(): void {
  applyMode(getMode());
  applyAccent(getAccent());
}
