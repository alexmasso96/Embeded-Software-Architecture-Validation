// Recently-accessed releases, tracked per project in localStorage so the
// sidebar dropdown can show "active + 5 most recent" without bloating the DB
// schema. Keyed by project path because release ids are only unique per project.
// Mirrored to the durable backend store (issue 6) so it survives the desktop
// shell's per-launch port change.

import { persistKey } from "./prefs";

const KEY = "arch.releaseRecents";
const MAX = 5;

type Store = Record<string, number[]>; // path -> release ids, most-recent first

function read(): Store {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return obj && typeof obj === "object" ? (obj as Store) : {};
  } catch {
    return {};
  }
}

function write(store: Store): void {
  const blob = JSON.stringify(store);
  try {
    localStorage.setItem(KEY, blob);
  } catch {
    /* quota / private mode — recents are best-effort */
  }
  persistKey(KEY, blob);
}

export function getReleaseRecents(path: string | null): number[] {
  if (!path) return [];
  const list = read()[path];
  return Array.isArray(list) ? list : [];
}

// Record that a release was just accessed; returns the new recents list.
export function touchReleaseRecent(path: string | null, id: number): number[] {
  if (!path) return [];
  const store = read();
  const prev = Array.isArray(store[path]) ? store[path] : [];
  const next = [id, ...prev.filter((x) => x !== id)].slice(0, MAX);
  store[path] = next;
  write(store);
  return next;
}
