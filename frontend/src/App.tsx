import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { ProjectStatus } from "./api/types";
import { useSSE } from "./api/useSSE";
import { Preferences } from "./components/Preferences";
import { StartScreen } from "./components/StartScreen";
import { Titlebar, type Tab } from "./components/Titlebar";
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
        }
      },
      [reloadStatus, toast],
    ),
    Boolean(status?.open),
  );

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

  const canEdit = status.can_edit && !status.lock_lost;

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
      {status.integrity_mismatch && (
        <div className="banner warn">
          ⚠ Project integrity check failed — the file may have been modified outside the app.
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
      ) : (
        <div className="center-msg">{activeTab} — coming in a later Phase 2 slice.</div>
      )}

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
