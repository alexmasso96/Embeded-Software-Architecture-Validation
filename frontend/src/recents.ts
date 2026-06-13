// Recent-projects list, persisted in localStorage (survives pywebview reloads
// too). Frontend-only — no backend state needed for "recents".

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
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}

export function removeRecent(path: string): RecentProject[] {
  const next = getRecents().filter((r) => r.path !== path);
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}
