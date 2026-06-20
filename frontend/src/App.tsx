import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { JobPayload, ProjectStatus } from "./api/types";
import { useSSE } from "./api/useSSE";
import { nativeSetTitle } from "./native";
import { JobProgressOverlay } from "./components/JobProgressOverlay";
import { Preferences } from "./components/Preferences";
import { StartScreen } from "./components/StartScreen";
import { Titlebar, type Tab } from "./components/Titlebar";
import { AIChat } from "./views/AIChat";
import { AIGeneration } from "./views/AIGeneration";
import { ChangeLog } from "./views/ChangeLog";
import { CodeMap } from "./views/CodeMap";
import { TestCodeInjection } from "./views/TestCodeInjection";
import { TestDesign } from "./views/TestDesign";
import { Workspace } from "./views/Workspace";

function basename(path: string | null): string {
  if (!path) return "Untitled";
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1].replace(/\.arch$/i, "");
}

export default function App() {
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("Workspace");
  const [saving, setSaving] = useState(false);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);
  const [activeJobs, setActiveJobs] = useState<Record<string, JobPayload>>({});
  const jobTimers = useRef<Record<string, number>>({});

  // Editing is allowed only with the exclusive lock still held. Computed with
  // optional chaining so the keyboard handler (mounted before the open/closed
  // branch) can read it via a ref without tripping the rules-of-hooks order.
  const canEdit = !!(status?.can_edit && !status?.lock_lost);

  const reloadStatus = useCallback(async () => {
    try {
      setStatus(await api.get<ProjectStatus>("/project/status"));
    } catch {
      /* worker not ready yet */
    }
  }, []);

  useEffect(() => {
    reloadStatus();
  }, [reloadStatus]);

  const toast = useCallback((msg: string) => {
    setToastMsg(msg);
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToastMsg(null), 2600);
  }, []);

  // Lock / takeover events flip the project to view-only — refresh status so the
  // banner + edit guards update without a manual reload.
  useSSE(
    useCallback(
      (e) => {
        if (e.event === "lock" || e.event === "lock_lost") {
          reloadStatus();
          if (e.event === "lock_lost" || e.data?.lock_lost) {
            toast("Edit lock lost — switched to view-only");
          }
        } else if (e.event === "job") {
          const job = e.data as unknown as JobPayload;
          if (!job.job_id) return;
          setActiveJobs((prev) => ({ ...prev, [job.job_id]: job }));
          // Keep terminal jobs on screen briefly so the user sees the final
          // state, then drop them. Replace any pending timer (a late update may
          // arrive after the first terminal event).
          if (
            job.status === "done" ||
            job.status === "failed" ||
            job.status === "cancelled"
          ) {
            if (jobTimers.current[job.job_id]) {
              window.clearTimeout(jobTimers.current[job.job_id]);
            }
            jobTimers.current[job.job_id] = window.setTimeout(() => {
              delete jobTimers.current[job.job_id];
              setActiveJobs((prev) => {
                const next = { ...prev };
                delete next[job.job_id];
                return next;
              });
            }, 3000);
          }
        }
      },
      [reloadStatus, toast],
    ),
    Boolean(status?.open),
  );

  // Clear any outstanding job-removal timers on unmount.
  useEffect(() => {
    const timers = jobTimers.current;
    return () => {
      Object.values(timers).forEach((t) => window.clearTimeout(t));
    };
  }, []);

  // Window title: project + release + edit/view mode (drives the native window
  // title in the desktop shell; just the tab title in a browser).
  useEffect(() => {
    const base = "Architecture Validator";
    let title = base;
    if (status?.open) {
      const name = basename(status.path);
      const rel = status.active_release ? ` — ${status.active_release}` : "";
      const modeLabel = canEdit ? "Editing" : "View-Only";
      title = `${name}${rel} — ${modeLabel} — ${base}`;
    }
    document.title = title;
    nativeSetTitle(title);
  }, [status?.open, status?.path, status?.active_release, canEdit]);

  // Global keyboard shortcuts. Mounted once; reads the latest save()/canEdit via
  // refs so it never re-subscribes. ⌘/Ctrl+S saves, ⌘/Ctrl+F focuses the search
  // box (via a custom event Workspace listens for), Escape closes App-owned
  // modals (the others manage their own Escape with rename-aware nuance).
  const saveRef = useRef<() => void>(() => {});
  const canEditRef = useRef(canEdit);
  canEditRef.current = canEdit;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        if (canEditRef.current) saveRef.current();
      } else if (mod && (e.key === "f" || e.key === "F")) {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("focus-search-input"));
      } else if (e.key === "Escape") {
        setPrefsOpen(false);
        setImportOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function save() {
    setSaving(true);
    try {
      await api.post("/project/save");
      toast("Saved");
      reloadStatus();
    } catch (e) {
      toast(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }
  saveRef.current = save;

  async function closeProject() {
    try {
      await api.post("/project/close");
      setPrefsOpen(false);
      reloadStatus();
      toast("Project closed");
    } catch (e) {
      toast(`Close failed: ${(e as Error).message}`);
    }
  }

  if (!status || !status.open) {
    return (
      <div className="app">
        <StartScreen onOpened={setStatus} onOpenPrefs={() => setPrefsOpen(true)} />
        {prefsOpen && <Preferences onClose={() => setPrefsOpen(false)} />}
      </div>
    );
  }

  return (
    <div className="app">
      <Titlebar
        projectName={basename(status.path)}
        release={status.active_release}
        activeTab={activeTab}
        onTab={setActiveTab}
        onSave={save}
        canSave={canEdit}
        saving={saving}
        onImport={() => setImportOpen(true)}
        onColumns={() => setColumnsOpen(true)}
        onPrefs={() => setPrefsOpen(true)}
      />

      {status.lock_lost && (
        <div className="banner err">
          ⚠ The edit lock was taken by another user. You are now in view-only mode.
        </div>
      )}
      {!status.lock_lost && status.mode === "view" && (
        <div className="banner warn">
          👁 View-only mode — editing is disabled.
        </div>
      )}

      {activeTab === "Workspace" ? (
        <Workspace
          status={status}
          onReloadStatus={reloadStatus}
          toast={toast}
          importOpen={importOpen}
          onCloseImport={() => setImportOpen(false)}
          columnsOpen={columnsOpen}
          onCloseColumns={() => setColumnsOpen(false)}
        />
      ) : activeTab === "Test Design" ? (
        <TestDesign toast={toast} />
      ) : activeTab === "AI Generation" ? (
        <AIGeneration toast={toast} />
      ) : activeTab === "AI Chat" ? (
        <AIChat toast={toast} />
      ) : activeTab === "Code Map" ? (
        <CodeMap toast={toast} />
      ) : activeTab === "Test Injection" ? (
        <TestCodeInjection toast={toast} canEdit={canEdit} />
      ) : activeTab === "Change Log" ? (
        <ChangeLog toast={toast} />
      ) : (
        <div className="center-msg">{activeTab} — coming in a later Phase 2 slice.</div>
      )}

      <JobProgressOverlay
        jobs={Object.values(activeJobs)}
        onCancel={(id) => {
          api
            .post(`/jobs/${id}/cancel`)
            .catch((e) => toast(`Cancel failed: ${(e as Error).message}`));
        }}
      />

      {toastMsg && <div className="v-toast">{toastMsg}</div>}
      {prefsOpen && (
        <Preferences
          onClose={() => setPrefsOpen(false)}
          onCloseProject={closeProject}
        />
      )}
    </div>
  );
}
