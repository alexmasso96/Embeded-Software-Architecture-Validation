// Recent-projects list. Cached in localStorage for synchronous reads, and
// mirrored to the durable backend store (issue 6) so it survives the desktop
// shell's per-launch port change, app restarts, and updates.

import { persistKey } from "./prefs";

export interface RecentProject {
  path: string;
  name: string;
  lastOpened: number; // epoch ms
}

const KEY = "arch.recents";
const MAX = 8;

function basename(path: string): string {
  const parts = path.split(/[\\/]/);
  return (parts[parts.length - 1] || path).replace(/\.arch$/i, "");
}

export function getRecents(): RecentProject[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as RecentProject[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function addRecent(path: string): RecentProject[] {
  const now = Date.now();
  const next = [
    { path, name: basename(path), lastOpened: now },
    ...getRecents().filter((r) => r.path !== path),
  ].slice(0, MAX);
  const blob = JSON.stringify(next);
  localStorage.setItem(KEY, blob);
  persistKey(KEY, blob);
  return next;
}

export function removeRecent(path: string): RecentProject[] {
  const next = getRecents().filter((r) => r.path !== path);
  const blob = JSON.stringify(next);
  localStorage.setItem(KEY, blob);
  persistKey(KEY, blob);
  return next;
}
