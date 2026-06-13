import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ProjectMode, ProjectStatus } from "../api/types";
import { addRecent, getRecents, removeRecent, type RecentProject } from "../recents";
import { FolderPicker } from "./FolderPicker";
import { FolderIcon } from "./Icons";
import { PasswordDialog } from "./PasswordDialog";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function timeAgo(ms: number): string {
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

interface UnlockTarget {
  path: string;
  mode: ProjectMode;
  error?: string | null;
}

// Phases of the New-Project flow after the .arch is created (and open):
//   "choose" → Empty vs Import; "import" → pick .elf/.json; "release" → name it.
type NewPhase = null | "choose" | "import" | "release";

export function StartScreen({
  onOpened,
  onOpenPrefs,
}: {
  onOpened: (s: ProjectStatus) => void;
  onOpenPrefs: () => void;
}) {
  const [recents, setRecents] = useState<RecentProject[]>(getRecents());
  const [picker, setPicker] = useState<"open" | "new" | null>(null);
  const [pwSetupPath, setPwSetupPath] = useState<string | null>(null);
  const [unlock, setUnlock] = useState<UnlockTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // New-project post-create state (project is created & open during these).
  const [phase, setPhase] = useState<NewPhase>(null);
  const [createdPath, setCreatedPath] = useState<string | null>(null);
  const [importFile, setImportFile] = useState<string | null>(null);
  const [releaseName, setReleaseName] = useState("R1.0");
  const [importMsg, setImportMsg] = useState<string | null>(null);

  async function finishOpen(path: string) {
    setRecents(addRecent(path));
    onOpened(await api.get<ProjectStatus>("/project/status"));
  }

  async function doOpen(path: string, mode: ProjectMode, password?: string) {
    setPicker(null);
    setBusy(true);
    setErr(null);
    try {
      await api.post("/project/open", { path, mode, password });
      setUnlock(null);
      await finishOpen(path);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setUnlock({ path, mode });
      else if (e instanceof ApiError && e.status === 403)
        setUnlock({ path, mode, error: "Incorrect master password." });
      else {
        setErr(e instanceof ApiError ? e.detail : String(e));
        setUnlock(null);
      }
    } finally {
      setBusy(false);
    }
  }

  // Create the encrypted .arch, then offer Empty vs Import.
  async function createProject(path: string, password: string) {
    setBusy(true);
    setErr(null);
    try {
      await api.post("/project/new", { path, password });
      setPwSetupPath(null);
      setCreatedPath(path);
      setPhase("choose");
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runImport(file: string, name: string) {
    if (!createdPath) return;
    setBusy(true);
    setImportMsg("Creating release…");
    setErr(null);
    try {
      const rel = await api.post<{ id: number }>("/releases", { name });
      await api.post(`/releases/${rel.id}/activate`);
      setImportMsg("Importing symbols…");
      const started = await api.post<{ job_id: string }>("/jobs/import_symbols", {
        file_path: file,
        release_id: rel.id,
      });
      for (;;) {
        await sleep(250);
        const j = await api.get<{ status: string; error?: string }>(
          `/jobs/${started.job_id}`,
        );
        if (j.status === "done") break;
        if (j.status === "failed" || j.status === "cancelled")
          throw new Error(j.error || "Import failed.");
      }
      setPhase(null);
      await finishOpen(createdPath);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setImportMsg(null);
      setPhase("choose"); // back to the choice so the user can retry / go empty
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="launcher">
      <div className="start">
        <div className="start-head">
          <div>
            <h1>Architecture Validator Pro</h1>
            <div className="sub">Open a recent project, or start a new one.</div>
          </div>
          <button className="start-prefs" title="Preferences" onClick={onOpenPrefs}>
            ⚙
          </button>
        </div>

        <div className="start-cards">
          <button className="start-card" disabled={busy} onClick={() => setPicker("new")}>
            <span className="start-card-icon">＋</span>
            <span className="start-card-title">New Project</span>
            <span className="start-card-sub">Create an encrypted .arch</span>
          </button>
          <button className="start-card" disabled={busy} onClick={() => setPicker("open")}>
            <span className="start-card-icon">
              <FolderIcon size={24} />
            </span>
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
                onClick={() => doOpen(r.path, "view")}
              >
                <span className="recent-name">{r.name}</span>
                <span className="recent-path mono">{r.path}</span>
              </button>
              <span className="recent-time">{timeAgo(r.lastOpened)}</span>
              <button
                className="recent-act"
                disabled={busy}
                title="Open for editing (exclusive lock)"
                onClick={() => doOpen(r.path, "exclusive")}
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
            <span className="spin" /> {importMsg || "Working…"}
          </div>
        )}
        {err && <div className="launcher-err">{err}</div>}
      </div>

      {picker === "open" && (
        <FolderPicker mode="open" onCancel={() => setPicker(null)} onConfirm={doOpen} />
      )}
      {picker === "new" && (
        <FolderPicker
          mode="new"
          onCancel={() => setPicker(null)}
          onConfirm={(path) => {
            setPicker(null);
            setPwSetupPath(path);
          }}
        />
      )}

      {pwSetupPath && (
        <PasswordDialog
          mode="setup"
          busy={busy}
          onCancel={() => setPwSetupPath(null)}
          onSubmit={(pw) => createProject(pwSetupPath, pw)}
        />
      )}

      {unlock && (
        <PasswordDialog
          mode="unlock"
          busy={busy}
          error={unlock.error}
          onCancel={() => setUnlock(null)}
          onSubmit={(pw) => doOpen(unlock.path, unlock.mode, pw)}
        />
      )}

      {/* Empty vs Import (project already created & open) */}
      {phase === "choose" && (
        <div className="modal-overlay">
          <div className="modal choose" onMouseDown={(e) => e.stopPropagation()}>
            <div className="modal-head">New Project — what's next?</div>
            <div className="choose-body">
              <button
                className="choose-card"
                disabled={busy}
                onClick={() => createdPath && finishOpen(createdPath)}
              >
                <span className="choose-icon">▦</span>
                <span className="choose-title">Empty Project</span>
                <span className="choose-sub">Start with a blank table.</span>
              </button>
              <button className="choose-card" disabled={busy} onClick={() => setPhase("import")}>
                <span className="choose-icon">⇪</span>
                <span className="choose-title">Import</span>
                <span className="choose-sub">Load symbols from an .elf or .json.</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {phase === "import" && (
        <FolderPicker
          mode="import"
          onCancel={() => setPhase("choose")}
          onConfirm={(file) => {
            setImportFile(file);
            setPhase("release");
          }}
        />
      )}

      {phase === "release" && (
        <div className="modal-overlay">
          <div className="modal pwdialog" onMouseDown={(e) => e.stopPropagation()}>
            <div className="modal-head">Name the Release</div>
            <div className="pw-body">
              <p className="pw-sub">
                The imported symbols are stored under a release version.
                <br />
                <span className="mono">{importFile?.split(/[\\/]/).pop()}</span>
              </p>
              <label>Release name</label>
              <input
                autoFocus
                type="text"
                value={releaseName}
                onChange={(e) => setReleaseName(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" &&
                  releaseName.trim() &&
                  importFile &&
                  runImport(importFile, releaseName.trim())
                }
              />
            </div>
            <div className="picker-foot">
              <div className="spacer" />
              <button className="scope-btn" disabled={busy} onClick={() => setPhase("import")}>
                Back
              </button>
              <button
                className="save-btn"
                disabled={busy || !releaseName.trim()}
                onClick={() => importFile && runImport(importFile, releaseName.trim())}
              >
                {busy ? "Importing…" : "Import"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
