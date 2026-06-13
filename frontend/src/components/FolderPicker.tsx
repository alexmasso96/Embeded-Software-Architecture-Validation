import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { FsEntry, FsListResponse, ProjectMode } from "../api/types";

// Finder-style Miller-columns browser backed by GET /api/fs/list (dev stand-in
// for the Phase-3 native dialog). Each column shows one folder's contents;
// clicking a folder opens the next column to its right. Two modes:
//   open → select an existing .arch (default view-only; tick to open for editing).
//   new  → navigate to a destination folder (+ New Folder), type a filename → create.
export function FolderPicker({
  mode,
  onCancel,
  onConfirm,
}: {
  mode: "open" | "new";
  onCancel: () => void;
  onConfirm: (path: string, openMode: ProjectMode) => void;
}) {
  // One listing per visible column; cols[i+1] is the contents of the folder
  // selected in cols[i]. selected[i] = the highlighted entry path in column i.
  const [cols, setCols] = useState<FsListResponse[]>([]);
  const [selected, setSelected] = useState<(string | null)[]>([]);
  const [selectedArch, setSelectedArch] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [filename, setFilename] = useState("");
  const [editMode, setEditMode] = useState(false); // open mode: default view-only
  const [newFolderName, setNewFolderName] = useState<string | null>(null); // null = input hidden

  const scrollRef = useRef<HTMLDivElement>(null);

  async function fetchDir(path?: string): Promise<FsListResponse | null> {
    const q = path ? `?path=${encodeURIComponent(path)}` : "";
    try {
      return await api.get<FsListResponse>(`/fs/list${q}`);
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }

  useEffect(() => {
    (async () => {
      setLoading(true);
      const home = await fetchDir();
      if (home) {
        setCols([home]);
        setSelected([null]);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the deepest column in view as the user drills down.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [cols.length]);

  const currentDir = cols.length ? cols[cols.length - 1].path : null;

  async function onEntryClick(colIndex: number, entry: FsEntry) {
    setError(null);
    setNewFolderName(null);
    const sel = selected.slice(0, colIndex + 1);
    sel[colIndex] = entry.path;

    if (entry.is_dir) {
      setSelectedArch(null);
      const listing = await fetchDir(entry.path);
      if (!listing) return;
      setCols((prev) => [...prev.slice(0, colIndex + 1), listing]);
      setSelected(sel);
    } else if (entry.is_arch && mode === "open") {
      setSelectedArch(entry.path);
      setCols((prev) => prev.slice(0, colIndex + 1)); // drop deeper columns
      setSelected(sel);
    }
  }

  function onEntryDouble(colIndex: number, entry: FsEntry) {
    if (entry.is_arch && mode === "open") {
      onConfirm(entry.path, editMode ? "exclusive" : "view");
    } else {
      onEntryClick(colIndex, entry);
    }
  }

  async function createFolder() {
    const name = (newFolderName ?? "").trim();
    if (!name || !currentDir) return;
    try {
      await api.post("/fs/mkdir", { parent: currentDir, name });
      setNewFolderName(null);
      // Refresh the deepest column so the new folder appears.
      const refreshed = await fetchDir(currentDir);
      if (refreshed) setCols((prev) => [...prev.slice(0, -1), refreshed]);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function confirm() {
    if (mode === "open") {
      if (selectedArch) onConfirm(selectedArch, editMode ? "exclusive" : "view");
    } else {
      if (!currentDir || !filename.trim()) return;
      let name = filename.trim();
      if (!name.toLowerCase().endsWith(".arch")) name += ".arch";
      const sep = cols[cols.length - 1].sep || "/";
      onConfirm(currentDir.replace(/[\\/]$/, "") + sep + name, "exclusive");
    }
  }

  const canConfirm = mode === "open" ? Boolean(selectedArch) : Boolean(filename.trim());

  return (
    <div className="modal-overlay" onMouseDown={onCancel}>
      <div className="modal picker" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">
          {mode === "open" ? "Open Project" : "New Project — choose location"}
        </div>

        <div className="picker-bar">
          <div className="picker-path mono">{selectedArch ?? currentDir ?? "…"}</div>
          {mode === "new" &&
            (newFolderName === null ? (
              <button
                className="scope-btn"
                disabled={!currentDir}
                onClick={() => setNewFolderName("")}
              >
                ＋ New Folder
              </button>
            ) : (
              <div className="newfolder">
                <input
                  autoFocus
                  className="picker-filename"
                  placeholder="Folder name"
                  spellCheck={false}
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") createFolder();
                    if (e.key === "Escape") setNewFolderName(null);
                  }}
                />
                <button className="scope-btn" onClick={createFolder}>
                  Create
                </button>
                <button className="scope-btn" onClick={() => setNewFolderName(null)}>
                  ✕
                </button>
              </div>
            ))}
        </div>

        <div className="picker-cols" ref={scrollRef}>
          {loading && (
            <div className="center-msg">
              <span className="spin" />
            </div>
          )}
          {error && <div className="picker-empty" style={{ color: "var(--red)" }}>{error}</div>}
          {!loading &&
            cols.map((col, ci) => (
              <div className="picker-col" key={ci}>
                {col.entries.length === 0 && <div className="picker-empty">Empty</div>}
                {col.entries.map((e) => {
                  const isSel = selected[ci] === e.path;
                  return (
                    <div
                      key={e.path}
                      className={
                        "picker-row" +
                        (isSel ? " sel" : "") +
                        (e.is_dir ? " dir" : " file")
                      }
                      onClick={() => onEntryClick(ci, e)}
                      onDoubleClick={() => onEntryDouble(ci, e)}
                    >
                      <span className="picker-icon">{e.is_dir ? "📁" : "▣"}</span>
                      <span className="picker-name">{e.name}</span>
                      {e.is_dir && <span className="picker-chev">›</span>}
                    </div>
                  );
                })}
              </div>
            ))}
        </div>

        <div className="picker-foot">
          {mode === "new" ? (
            <input
              className="picker-filename"
              type="text"
              placeholder="ProjectName.arch"
              spellCheck={false}
              value={filename}
              onChange={(ev) => setFilename(ev.target.value)}
              onKeyDown={(ev) => ev.key === "Enter" && confirm()}
            />
          ) : (
            <label className="picker-mode">
              <input
                type="checkbox"
                checked={editMode}
                onChange={(ev) => setEditMode(ev.target.checked)}
              />
              Open for editing (exclusive lock)
            </label>
          )}
          <div className="spacer" />
          <button className="scope-btn" onClick={onCancel}>
            Cancel
          </button>
          <button className="save-btn" disabled={!canConfirm} onClick={confirm}>
            {mode === "open" ? "Open" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
