import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ModelInfo, ModelsResponse } from "../api/types";

const STATUSES = ["In Work", "Released", "Retired"];

// macOS-style modal for the full model lifecycle: create, rename, duplicate,
// set status, soft-delete and restore. Backed by POST/PATCH /api/models
// (soft-delete = PATCH {is_deleted:true}; restore = {is_deleted:false}).
// Includes deleted models (greyed) so they can be restored.
export function ModelManager({
  canEdit,
  onClose,
  onChanged,
  toast,
}: {
  canEdit: boolean;
  onClose: () => void;
  onChanged: () => void; // tell the workspace to refetch its model list
  toast: (msg: string) => void;
}) {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState<number | null>(null);
  const [draftName, setDraftName] = useState("");
  const renameRef = useRef<HTMLInputElement>(null);

  async function reload(keepSelection = true) {
    setLoading(true);
    try {
      const r = await api.get<ModelsResponse>("/models?include_deleted=true");
      setModels(r.models);
      if (!keepSelection || selected === null) {
        setSelected(r.active_model_id ?? r.models[0]?.id ?? null);
      }
    } catch (e) {
      toast(`Load models failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && renaming === null) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, renaming]);

  useEffect(() => {
    if (renaming !== null) {
      renameRef.current?.focus();
      renameRef.current?.select();
    }
  }, [renaming]);

  const sel = models.find((m) => m.id === selected) ?? null;

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  function newModel() {
    run(async () => {
      const base = "New Model";
      const taken = new Set(models.map((m) => m.name));
      let name = base;
      let n = 2;
      while (taken.has(name)) name = `${base} ${n++}`;
      try {
        const created = await api.post<{ id: number }>("/models", { name });
        await reload();
        setSelected(created.id);
        startRename(created.id, name);
      } catch (e) {
        toast(`Create failed: ${(e as Error).message}`);
      }
    });
  }

  function duplicate() {
    if (!sel) return;
    run(async () => {
      const taken = new Set(models.map((m) => m.name));
      let name = `${sel.name} copy`;
      let n = 2;
      while (taken.has(name)) name = `${sel.name} copy ${n++}`;
      try {
        const created = await api.post<{ id: number }>("/models", {
          name,
          copy_from_id: sel.id,
        });
        await reload();
        setSelected(created.id);
        toast(`Duplicated to “${name}”`);
      } catch (e) {
        toast(`Duplicate failed: ${(e as Error).message}`);
      }
    });
  }

  function startRename(id: number, current: string) {
    setRenaming(id);
    setDraftName(current);
  }

  function commitRename() {
    const id = renaming;
    const name = draftName.trim();
    const target = models.find((m) => m.id === id);
    setRenaming(null);
    if (id === null || !target || !name || name === target.name) return;
    run(async () => {
      try {
        await api.patch(`/models/${id}`, { name });
        await reload();
      } catch (e) {
        toast(`Rename failed: ${(e as Error).message}`);
      }
    });
  }

  function setStatus(status: string) {
    if (!sel || status === sel.status) return;
    run(async () => {
      try {
        await api.patch(`/models/${sel.id}`, { status });
        await reload();
      } catch (e) {
        toast(`Status change failed: ${(e as Error).message}`);
      }
    });
  }

  function softDelete() {
    if (!sel) return;
    if (!window.confirm(`Delete model “${sel.name}”? It can be restored later.`)) return;
    run(async () => {
      try {
        await api.patch(`/models/${sel.id}`, { is_deleted: true });
        await reload();
      } catch (e) {
        toast(`Delete failed: ${(e as Error).message}`);
      }
    });
  }

  function restore() {
    if (!sel) return;
    run(async () => {
      try {
        await api.patch(`/models/${sel.id}`, { is_deleted: false });
        await reload();
      } catch (e) {
        toast(`Restore failed: ${(e as Error).message}`);
      }
    });
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal modelmgr" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">Manage Models</div>

        <div className="mm-body">
          <div className="mm-list">
            {loading && models.length === 0 ? (
              <div className="mm-empty">
                <span className="spin" />
                &nbsp;Loading…
              </div>
            ) : models.length === 0 ? (
              <div className="mm-empty">No models.</div>
            ) : (
              models.map((m) => (
                <div
                  key={m.id}
                  className={
                    "mm-row" +
                    (m.id === selected ? " sel" : "") +
                    (m.is_deleted ? " deleted" : "")
                  }
                  onClick={() => setSelected(m.id)}
                  onDoubleClick={() =>
                    canEdit && !m.is_deleted && startRename(m.id, m.name)
                  }
                >
                  <span className="sl-icon">▣</span>
                  {renaming === m.id ? (
                    <input
                      ref={renameRef}
                      className="mm-rename"
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      onBlur={commitRename}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename();
                        if (e.key === "Escape") setRenaming(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <span className="mm-name">{m.name}</span>
                  )}
                  {m.is_active && <span className="mm-tag">active</span>}
                  {m.is_deleted && <span className="mm-tag del">deleted</span>}
                  <span className="badge">{m.row_count}</span>
                </div>
              ))
            )}
          </div>

          <div className="mm-side">
            <div className="mm-detail">
              {sel ? (
                <>
                  <div className="mm-detail-name">{sel.name}</div>
                  <label className="mm-field">
                    Status
                    <select
                      value={sel.status}
                      disabled={!canEdit || sel.is_deleted || busy}
                      onChange={(e) => setStatus(e.target.value)}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="mm-meta">{sel.row_count} ports</div>
                </>
              ) : (
                <div className="mm-empty">Select a model</div>
              )}
            </div>

            <div className="mm-actions">
              <button onClick={newModel} disabled={!canEdit || busy}>
                ＋ New Model
              </button>
              <button
                onClick={() => sel && startRename(sel.id, sel.name)}
                disabled={!canEdit || busy || !sel || sel.is_deleted}
              >
                Rename
              </button>
              <button
                onClick={duplicate}
                disabled={!canEdit || busy || !sel || sel.is_deleted}
              >
                Duplicate
              </button>
              {sel?.is_deleted ? (
                <button onClick={restore} disabled={!canEdit || busy}>
                  Restore
                </button>
              ) : (
                <button
                  className="danger"
                  onClick={softDelete}
                  disabled={!canEdit || busy || !sel}
                >
                  Delete…
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="mm-foot">
          {!canEdit && <span className="mm-vo">View-only — open for editing to change models.</span>}
          <div className="spacer" />
          <button className="primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
