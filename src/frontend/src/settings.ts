// UI preferences that aren't theme colours: toolbar icon labels and which file
// browser to use. Persisted in localStorage; changes broadcast a window event so
// any subscribed component re-renders live (see useSetting).

import { useEffect, useState } from "react";
import { persistKey } from "./prefs";

const ICON_LABELS_KEY = "arch.ui.iconLabels";
const FILE_EXPLORER_KEY = "arch.ui.fileExplorer";
const CHANGED_EVENT = "arch-settings-changed";

export type FileExplorerMode = "custom" | "system";

function emit() {
  window.dispatchEvent(new Event(CHANGED_EVENT));
}

// Toolbar icons: show text labels under the glyphs, or icons only. Default on
// (labels) — more discoverable, which is what issue 5 asks for.
export function getIconLabels(): boolean {
  return localStorage.getItem(ICON_LABELS_KEY) !== "0";
}
export function setIconLabels(v: boolean): void {
  const blob = v ? "1" : "0";
  localStorage.setItem(ICON_LABELS_KEY, blob);
  persistKey(ICON_LABELS_KEY, blob);
  emit();
}

// "custom" → the in-app Finder-style FolderPicker. "system" → the OS-native file
// dialog (desktop build only; falls back to custom in a plain browser).
export function getFileExplorer(): FileExplorerMode {
  return localStorage.getItem(FILE_EXPLORER_KEY) === "system" ? "system" : "custom";
}
export function setFileExplorer(mode: FileExplorerMode): void {
  localStorage.setItem(FILE_EXPLORER_KEY, mode);
  persistKey(FILE_EXPLORER_KEY, mode);
  emit();
}

// Subscribe a component to a setting so it re-renders when the value changes
// anywhere (e.g. the Preferences dialog flips it).
export function useSetting<T>(read: () => T): T {
  const [value, setValue] = useState<T>(read);
  useEffect(() => {
    const handler = () => setValue(read());
    window.addEventListener(CHANGED_EVENT, handler);
    return () => window.removeEventListener(CHANGED_EVENT, handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return value;
}
