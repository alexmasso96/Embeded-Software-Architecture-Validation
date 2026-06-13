import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProjectMode, ProjectStatus } from "../api/types";
import { addRecent, getRecents, removeRecent, type RecentProject } from "../recents";
import { FolderPicker } from "./FolderPicker";

function timeAgo(ms: number): string {
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// Launcher / start screen: New + Open cards and a recent-projects list.
// The actual create form (ELF/source/model setup) is a later, dedicated slice;
// here "New" just creates an empty .arch at a chosen location.
export function StartScreen({ onOpened }: { onOpened: (s: ProjectStatus) => void }) {
  const [recents, setRecents] = useState<RecentProject[]>(getRecents());
  const [picker, setPicker] = useState<"open" | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function afterOpen(path: string) {
    setRecents(addRecent(path));
    onOpened(await api.get<ProjectStatus>("/project/status"));
  }

  async function openProject(path: string, mode: ProjectMode) {
    setPicker(null);
    setBusy(true);
    setErr(null);
    try {
      await api.post("/project/open", { path, mode });
      await afterOpen(path);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function createProject(path: string) {
    setPicker(null);
    setBusy(true);
    setErr(null);
    try {
      await api.post("/project/new", { path });
      await afterOpen(path);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  function openRecent(path: string, mode: ProjectMode) {
    openProject(path, mode);
  }

  return (
    <div className="launcher">
      <div className="start">
        <div className="start-head">
          <h1>Architecture Validator Pro</h1>
          <div className="sub">Open a recent project, or start a new one.</div>
        </div>

        <div className="start-cards">
          <button className="start-card" disabled={busy} onClick={() => setPicker("new")}>
            <span className="start-card-icon">＋</span>
            <span className="start-card-title">New Project</span>
            <span className="start-card-sub">Create a new .arch file</span>
          </button>
          <button className="start-card" disabled={busy} onClick={() => setPicker("open")}>
            <span className="start-card-icon">📂</span>
            <span className="start-card-title">Open Project</span>
            <span className="start-card-sub">Browse for an existing .arch</span>
          </button>
        </div>

        <div className="start-recents">
          <div className="start-recents-head">Recent</div>
          {recents.length === 0 && <div className="start-recents-empty">No recent projects yet.</div>}
          {recents.map((r) => (
            <div className="recent-row" key={r.path}>
              <button
                className="recent-main"
                disabled={busy}
                title={`Open ${r.path} (view-only)`}
                onClick={() => openRecent(r.path, "view")}
              >
                <span className="recent-name">{r.name}</span>
                <span className="recent-path mono">{r.path}</span>
              </button>
              <span className="recent-time">{timeAgo(r.lastOpened)}</span>
              <button
                className="recent-act"
                disabled={busy}
                title="Open for editing (exclusive lock)"
                onClick={() => openRecent(r.path, "exclusive")}
              >
                ✏️
              </button>
              <button
                className="recent-act"
                disabled={busy}
                title="Remove from recents"
                onClick={() => setRecents(removeRecent(r.path))}
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        {busy && (
          <div className="launcher-err" style={{ color: "var(--muted)" }}>
            <span className="spin" /> Working…
          </div>
        )}
        {err && <div className="launcher-err">{err}</div>}
      </div>

      {picker === "open" && (
        <FolderPicker mode="open" onCancel={() => setPicker(null)} onConfirm={openProject} />
      )}
      {picker === "new" && (
        <FolderPicker
          mode="new"
          onCancel={() => setPicker(null)}
          onConfirm={(path) => createProject(path)}
        />
      )}
    </div>
  );
}
