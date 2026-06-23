// Durable UI-preferences mirror (issue 6).
//
// The desktop shell binds a random localhost port each launch, which changes
// the page origin and so wipes origin-scoped localStorage between sessions —
// that's why recents and settings kept resetting in the built app. We mirror
// those small prefs into a backend JSON store in the OS app-data dir: hydrate
// localStorage from it at boot, then write through on every change. localStorage
// stays the synchronous in-session cache the rest of the app reads.

import { api } from "./api/client";

// Hydrate localStorage from the backend store. Call once at boot, before the
// theme is applied and the app renders. Best-effort: on failure we keep
// whatever localStorage already holds.
export async function loadPrefs(): Promise<void> {
  try {
    const { prefs } = await api.get<{ prefs: Record<string, string> }>("/prefs");
    for (const [k, v] of Object.entries(prefs)) {
      try {
        localStorage.setItem(k, v);
      } catch {
        /* quota / storage disabled — ignore */
      }
    }
  } catch {
    /* backend unavailable — fall back to localStorage as-is */
  }
}

// Write-through a single key to the backend store (fire-and-forget).
export function persistKey(key: string, value: string): void {
  api.put("/prefs", { key, value }).catch(() => {});
}

// Delete a key from the backend store (fire-and-forget).
export function removePersistedKey(key: string): void {
  api.put("/prefs", { key, value: null }).catch(() => {});
}
