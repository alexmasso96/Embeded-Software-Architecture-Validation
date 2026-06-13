import { Fragment, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { FsEntry, FsListResponse, ProjectMode } from "../api/types";
import { FileIcon, FolderIcon } from "./Icons";

const DEFAULT_COL_W = 236;

type PickerMode = "open" | "new" | "import";

function extsFor(mode: PickerMode, exts?: string[]): string {
  if (exts && exts.length) return exts.join(",");
  return mode === "import" ? ".elf,.json" : ".arch";
}

// Finder-style Miller-columns browser backed by GET /api/fs/list (dev stand-in
// for the Phase-3 native dialog). Modes:
//   open   → select an existing .arch (default view-only; tick to open editing).
//   new    → navigate to a folder (+ New Folder), type a filename → create.
//   import → select an .elf / .json to import into the project.
export function FolderPicker({
  mode,
  exts,
  onCancel,
  onConfirm,
}: {
  mode: PickerMode;
  exts?: string[];
  onCancel: () => void;
  onConfirm: (path: string, openMode: ProjectMode) => void;
}) {
  const [cols, setCols] = useState<FsListResponse[]>([]);
  const [selected, setSelected] = useState<(string | null)[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [colWidths, setColWidths] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [filename, setFilename] = useState("");
  const [editMode, setEditMode] = useState(false); // open mode: default view-only
  const [newFolderName, setNewFolderName] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const extsParam = extsFor(mode, exts);

  async function fetchDir(path?: string): Promise<FsListResponse | null> {
    const params = new URLSearchParams({ exts: extsParam });
    if (path) params.set("path", path);
    try {
      return await api.get<FsListResponse>(`/fs/list?${params.toString()}`);
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

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [cols.length]);

  const currentDir = cols.length ? cols[cols.length - 1].path : null;
  const sep = cols.length ? cols[cols.length - 1].sep || "/" : "/";

  const widthOf = (ci: number) => colWidths[ci] ?? DEFAULT_COL_W;

  function startColResize(e: React.MouseEvent, ci: number) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startW = widthOf(ci);
    const onMove = (ev: MouseEvent) => {
      const w = Math.max(140, Math.min(640, startW + (ev.clientX - startX)));
      setColWidths((prev) => {
        const n = [...prev];
        n[ci] = w;
        return n;
      });
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }

  function fitColumn(ci: number) {
    const colEl = scrollRef.current?.querySelector(`[data-ci="${ci}"]`);
    if (!colEl) return;
    let max = 0;
    colEl.querySelectorAll(".picker-name").forEach((n) => {
      max = Math.max(max, (n as HTMLElement).scrollWidth);
    });
    const hasDir = colEl.querySelector(".picker-row.dir") != null;
    const w = Math.min(640, Math.max(150, Math.ceil(max) + 18 + 9 + (hasDir ? 19 : 6) + 32 + 6));
    setColWidths((prev) => {
      const n = [...prev];
      n[ci] = w;
      return n;
    });
  }

  async function navigateTo(path: string) {
    setError(null);
    setNewFolderName(null);
    setSelectedFile(null);
    const listing = await fetchDir(path);
    if (!listing) return;
    setCols([listing]);
    setSelected([null]);
    setColWidths([]);
  }

  async function onEntryClick(colIndex: number, entry: FsEntry) {
    setError(null);
    setNewFolderName(null);
    const sel = selected.slice(0, colIndex + 1);
    sel[colIndex] = entry.path;

    if (entry.is_dir) {
      setSelectedFile(null);
      const listing = await fetchDir(entry.path);
      if (!listing) return;
      setCols((prev) => [...prev.slice(0, colIndex + 1), listing]);
      setSelected(sel);
    } else if (mode !== "new") {
      setSelectedFile(entry.path);
      setCols((prev) => prev.slice(0, colIndex + 1));
      setSelected(sel);
    }
  }

  function onEntryDouble(colIndex: number, entry: FsEntry) {
    if (!entry.is_dir && mode !== "new") {
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
      const refreshed = await fetchDir(currentDir);
      if (refreshed) setCols((prev) => [...prev.slice(0, -1), refreshed]);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function confirm() {
    if (mode === "new") {
      if (!currentDir || !filename.trim()) return;
      let name = filename.trim();
      if (!name.toLowerCase().endsWith(".arch")) name += ".arch";
      onConfirm(currentDir.replace(/[\\/]$/, "") + sep + name, "exclusive");
    } else if (selectedFile) {
      onConfirm(selectedFile, editMode ? "exclusive" : "view");
    }
  }

  const canConfirm = mode === "new" ? Boolean(filename.trim()) : Boolean(selectedFile);
  const actionLabel = mode === "new" ? "Create" : mode === "import" ? "Import" : "Open";
  const title =
    mode === "open" ? "Open Project"
      : mode === "import" ? "Import Symbols — choose an .elf or .json"
        : "New Project — choose location";

  // Breadcrumb of the current directory (Finder-style segmented path).
  const crumbs: { name: string; path: string }[] = [];
  if (currentDir) {
    const isPosix = sep === "/";
    if (isPosix) crumbs.push({ name: "/", path: "/" });
    let acc = isPosix ? "" : "";
    for (const part of currentDir.split(sep).filter(Boolean)) {
      acc = acc + sep + part;
      crumbs.push({ name: part, path: acc });
    }
  }

  return (
    <div className="modal-overlay" onMouseDown={onCancel}>
      <div className="modal picker" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">{title}</div>

        <div className="picker-bar">
          <div className="crumbs">
            {crumbs.map((c, i) => {
              const last = i === crumbs.length - 1;
              return (
                <Fragment key={c.path}>
                  {i > 0 && <span className="crumb-sep">›</span>}
                  <button
                    className={"crumb" + (last ? " current" : "")}
                    disabled={last}
                    onClick={() => navigateTo(c.path)}
                  >
                    <FolderIcon size={13} />
                    <span>{c.name === "/" ? "Macintosh HD" : c.name}</span>
                  </button>
                </Fragment>
              );
            })}
          </div>
          {mode === "new" &&
            (newFolderName === null ? (
              <button className="scope-btn" disabled={!currentDir} onClick={() => setNewFolderName("")}>
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
                <button className="scope-btn" onClick={createFolder}>Create</button>
                <button className="scope-btn" onClick={() => setNewFolderName(null)}>✕</button>
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
              <Fragment key={ci}>
                <div
                  className="picker-col"
                  data-ci={ci}
                  style={{ flex: `0 0 ${widthOf(ci)}px`, width: widthOf(ci) }}
                >
                  {col.entries.length === 0 && <div className="picker-empty">Empty</div>}
                  {col.entries.map((e) => {
                    const isSel = selected[ci] === e.path;
                    return (
                      <div
                        key={e.path}
                        className={"picker-row" + (isSel ? " sel" : "") + (e.is_dir ? " dir" : " file")}
                        onClick={() => onEntryClick(ci, e)}
                        onDoubleClick={() => onEntryDouble(ci, e)}
                      >
                        <span className="picker-icon">
                          {e.is_dir ? <FolderIcon size={15} /> : <FileIcon size={15} />}
                        </span>
                        <span className="picker-name">{e.name}</span>
                        {e.is_dir && <span className="picker-chev">›</span>}
                      </div>
                    );
                  })}
                </div>
                <div
                  className="picker-coldiv"
                  title="Drag to resize · double-click to fit contents"
                  onMouseDown={(ev) => startColResize(ev, ci)}
                  onDoubleClick={() => fitColumn(ci)}
                >
                  <span className="coldiv-grip">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              </Fragment>
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
          ) : mode === "open" ? (
            <label className="picker-mode">
              <input
                type="checkbox"
                checked={editMode}
                onChange={(ev) => setEditMode(ev.target.checked)}
              />
              Open for editing (exclusive lock)
            </label>
          ) : (
            <span className="picker-mode">
              {selectedFile ? selectedFile.split(/[\\/]/).pop() : "Select an .elf or .json file"}
            </span>
          )}
          <div className="spacer" />
          <button className="scope-btn" onClick={onCancel}>Cancel</button>
          <button className="save-btn" disabled={!canConfirm} onClick={confirm}>
            {actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
