import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useSSE } from "../api/useSSE";
import type { LineageNode, LineageResponse } from "../api/types";
import { FolderPicker } from "./FolderPicker";
import { BaselineDiff } from "./BaselineDiff";

// Tree-view grid geometry (px per cell).
const COL_W = 168;
const ROW_H = 92;
const NODE_W = 138;
const NODE_H = 56;

// macOS-style overlay for the Release & Baseline Manager. Two views over the
// same lineage data: a scannable List (Name / Type / Actions) and a visual Tree
// laid out on the backend's stable (grid_x, grid_y) coordinates. Deleted nodes
// keep their grid cells so toggling "Show Deleted" never shifts the layout.
export function ReleaseManager({
  projectEditable,
  onClose,
  onChanged,
  toast,
}: {
  // True when the project itself is editable (exclusive, lock held). Stays true
  // while a baseline is loaded, so release-management actions (branch, freeze/
  // unfreeze, import source) work from a baseline too.
  projectEditable: boolean;
  onClose: () => void;
  onChanged: () => void; // tell the workspace to refetch releases/status
  toast: (msg: string) => void;
}) {
  const [nodes, setNodes] = useState<LineageNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showDeleted, setShowDeleted] = useState(false);
  const [view, setView] = useState<"list" | "tree">("list");
  const [selected, setSelected] = useState<number | null>(null);
  // When set, the FolderPicker is open to choose a source folder for this node.
  const [pickFor, setPickFor] = useState<LineageNode | null>(null);
  // When set, the table-diff modal is open comparing the active model to this baseline.
  const [compareWith, setCompareWith] = useState<LineageNode | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<LineageResponse>("/releases/lineage");
      setNodes(r.nodes);
    } catch (e) {
      toast(`Load lineage failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // The import_source background job (and the drop endpoint) publish db-changed
  // when they finish — reload so the ✓ Source badge tracks the DB without a
  // manual refresh.
  useSSE((e) => {
    if (e.event === "db-changed") reload();
  }, true);

  const names = useMemo(() => new Set(nodes.map((n) => n.name)), [nodes]);

  const visible = showDeleted ? nodes : nodes.filter((n) => !n.is_deleted);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
      await reload();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  function uniqueName(base: string): string {
    let name = base;
    let n = 2;
    while (names.has(name)) name = `${base} ${n++}`;
    return name;
  }

  function activate(node: LineageNode) {
    if (node.is_deleted || node.is_active) return;
    run(async () => {
      try {
        await api.post(`/releases/${node.id}/activate`);
        toast(
          node.is_baseline
            ? `Loaded baseline “${node.name}” (read-only)`
            : `Switched to “${node.name}”`,
        );
      } catch (e) {
        toast(`Activate failed: ${(e as Error).message}`);
      }
    });
  }

  function branch(node: LineageNode) {
    const suggested = uniqueName(`${node.name}_branch`);
    const name = window.prompt(`Branch off “${node.name}” — new release name:`, suggested);
    if (name == null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    run(async () => {
      try {
        await api.post(`/releases/${node.id}/branch`, { name: trimmed });
        toast(`Branched “${trimmed}” from “${node.name}”`);
      } catch (e) {
        toast(`Branch failed: ${(e as Error).message}`);
      }
    });
  }

  function freeze(node: LineageNode) {
    const suggested = uniqueName(`${node.name}_snapshot`);
    const name = window.prompt(`Freeze a baseline of “${node.name}” — baseline name:`, suggested);
    if (name == null) return;
    const trimmed = name.trim();
    if (!trimmed) return;
    run(async () => {
      try {
        await api.post(`/baselines`, { name: trimmed, release_id: node.id });
        toast(`Froze baseline “${trimmed}”`);
      } catch (e) {
        toast(`Freeze failed: ${(e as Error).message}`);
      }
    });
  }

  function addResultColumn(node: LineageNode) {
    run(async () => {
      try {
        await api.post(`/releases/${node.id}/result-column`);
        toast(`Added result column for “${node.name}”`);
      } catch (e) {
        toast(`Add result column failed: ${(e as Error).message}`);
      }
    });
  }

  function unfreeze(node: LineageNode) {
    if (
      !window.confirm(
        `Unfreeze baseline “${node.name}”? It becomes an editable release again ` +
          `and its frozen snapshot becomes its live data.`,
      )
    )
      return;
    run(async () => {
      try {
        await api.post(`/releases/${node.id}/unfreeze`);
        toast(`Unfroze “${node.name}”`);
      } catch (e) {
        toast(`Unfreeze failed: ${(e as Error).message}`);
      }
    });
  }

  function remove(node: LineageNode) {
    const kind = node.is_baseline ? "baseline" : "release";
    const note = node.is_baseline
      ? "It can be restored from “Show Deleted”."
      : "This permanently removes the release.";
    if (!window.confirm(`Delete ${kind} “${node.name}”? ${note}`)) return;
    run(async () => {
      try {
        await api.del(`/releases/${node.id}`);
        toast(`Deleted “${node.name}”`);
      } catch (e) {
        toast(`Delete failed: ${(e as Error).message}`);
      }
    });
  }

  function restore(node: LineageNode) {
    // Only soft-deleted baselines can be restored (plain releases hard-delete).
    run(async () => {
      try {
        await api.post(`/releases/${node.id}/restore`);
        toast(`Restored “${node.name}”`);
      } catch (e) {
        toast(`Restore failed: ${(e as Error).message}`);
      }
    });
  }

  // Import Source: open the folder picker; the actual POST runs on confirm.
  function importSource(node: LineageNode) {
    setPickFor(node);
  }

  async function doImportSource(node: LineageNode, path: string) {
    setBusy(true);
    try {
      await api.post(`/releases/${node.id}/source`, { source_dir: path });
      toast(`Importing source for “${node.name}”…`);
    } catch (e) {
      toast(`Import source failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  function dropSource(node: LineageNode) {
    if (
      !window.confirm(
        `Drop source code files from database for ${node.name}? This will free ` +
          `up database file space but disable code map source viewing and test ` +
          `injection for this release.`,
      )
    )
      return;
    run(async () => {
      try {
        await api.del(`/releases/${node.id}/source`);
        toast(`Dropped source for “${node.name}”`);
      } catch (e) {
        toast(`Drop source failed: ${(e as Error).message}`);
      }
    });
  }

  const grid = useMemo(() => {
    const maxX = visible.reduce((m, n) => Math.max(m, n.grid_x), 0);
    const maxY = visible.reduce((m, n) => Math.max(m, n.grid_y), 0);
    return { w: (maxX + 1) * COL_W, h: (maxY + 1) * ROW_H };
  }, [visible]);

  const posOf = (n: LineageNode) => ({
    left: n.grid_x * COL_W + (COL_W - NODE_W) / 2,
    top: n.grid_y * ROW_H + (ROW_H - NODE_H) / 2,
    cx: n.grid_x * COL_W + COL_W / 2,
    cy: n.grid_y * ROW_H + ROW_H / 2,
  });

  const visibleById = useMemo(
    () => new Map(visible.map((n) => [n.name, n])),
    [visible],
  );

  return (
    <>
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal releasemgr" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">Manage Releases &amp; Baselines</div>

        <div className="rm-toolbar">
          <label className="rm-check">
            <input
              type="checkbox"
              checked={showDeleted}
              onChange={(e) => setShowDeleted(e.target.checked)}
            />
            Show Deleted
          </label>
          <div className="spacer" />
          <button
            className="rm-toggle"
            onClick={() => setView((v) => (v === "list" ? "tree" : "list"))}
          >
            {view === "list" ? "View Lineage Tree" : "View List"}
          </button>
        </div>

        <div className="rm-body">
          {loading && nodes.length === 0 ? (
            <div className="mm-empty">
              <span className="spin" />
              &nbsp;Loading…
            </div>
          ) : visible.length === 0 ? (
            <div className="mm-empty">No releases or baselines.</div>
          ) : view === "list" ? (
            <table className="rm-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th className="rm-actions-col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((n) => (
                  <tr
                    key={n.id}
                    className={
                      (n.id === selected ? "sel " : "") +
                      (n.is_deleted ? "deleted" : "")
                    }
                    onClick={() => setSelected(n.id)}
                    onDoubleClick={() => activate(n)}
                  >
                    <td>
                      <span className="rm-name">
                        {n.is_baseline && <span className="rm-lock">🔒</span>}
                        {n.name}
                        {n.is_active && <span className="mm-tag">active</span>}
                        {n.has_source && (
                          <span className="mm-tag src" title="Source code stored in the database">
                            ✓ Source
                          </span>
                        )}
                        {n.is_deleted && <span className="mm-tag del">deleted</span>}
                      </span>
                    </td>
                    <td>{n.is_baseline ? "Baseline" : "Release"}</td>
                    <td className="rm-actions-col">
                      {n.is_deleted ? (
                        n.is_baseline && (
                          <button disabled={!projectEditable || busy} onClick={() => restore(n)}>
                            Restore
                          </button>
                        )
                      ) : (
                        <>
                          {n.is_baseline && !n.is_active && (
                            <button disabled={!projectEditable || busy} onClick={() => activate(n)}>
                              Load
                            </button>
                          )}
                          {n.is_baseline && (
                            <button disabled={busy} onClick={() => setCompareWith(n)}>
                              Compare
                            </button>
                          )}
                          {n.is_baseline && (
                            <button disabled={!projectEditable || busy} onClick={() => unfreeze(n)}>
                              Unfreeze
                            </button>
                          )}
                          <button disabled={!projectEditable || busy} onClick={() => branch(n)}>
                            Branch
                          </button>
                          {!n.is_baseline && (
                            <button disabled={!projectEditable || busy} onClick={() => freeze(n)}>
                              Freeze
                            </button>
                          )}
                          {!n.is_baseline && (
                            <button disabled={!projectEditable || busy} onClick={() => addResultColumn(n)}>
                              Result Col
                            </button>
                          )}
                          {projectEditable && (
                            <button disabled={busy} onClick={() => importSource(n)}>
                              Import Source
                            </button>
                          )}
                          {projectEditable && n.has_source && (
                            <button
                              className="danger"
                              disabled={busy}
                              onClick={() => dropSource(n)}
                            >
                              Drop Source
                            </button>
                          )}
                          <button
                            className="danger"
                            disabled={!projectEditable || busy}
                            onClick={() => remove(n)}
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="rm-tree-scroll">
              <div className="rm-tree" style={{ width: grid.w, height: grid.h }}>
                <svg className="rm-edges" width={grid.w} height={grid.h}>
                  {visible.map((n) => {
                    const parent = n.parent_release_name
                      ? visibleById.get(n.parent_release_name)
                      : undefined;
                    if (!parent) return null;
                    const a = posOf(n);
                    const b = posOf(parent);
                    return (
                      <line
                        key={`e-${n.id}`}
                        x1={a.cx}
                        y1={a.cy}
                        x2={b.cx}
                        y2={b.cy}
                        className="rm-edge"
                      />
                    );
                  })}
                </svg>
                {visible.map((n) => {
                  const p = posOf(n);
                  return (
                    <div
                      key={n.id}
                      className={
                        "rm-node" +
                        (n.is_active ? " active" : "") +
                        (n.is_baseline ? " baseline" : "") +
                        (n.is_deleted ? " deleted" : "") +
                        (n.id === selected ? " sel" : "")
                      }
                      style={{ left: p.left, top: p.top, width: NODE_W, height: NODE_H }}
                      onClick={() => setSelected(n.id)}
                      onDoubleClick={() => activate(n)}
                      title={`${n.name} · ${n.row_count} rows`}
                    >
                      <div className="rm-node-name">
                        {n.is_baseline && "🔒 "}
                        {n.name}
                      </div>
                      <div className="rm-node-sub">
                        {n.is_baseline ? "Baseline" : "Release"}
                        {n.is_active ? " · active" : ""}
                        {n.has_source && (
                          <span className="mm-tag src" title="Source code stored in the database">
                            ✓ Source
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="mm-foot">
          {!projectEditable && (
            <span className="mm-vo">View-only — open for editing to change releases.</span>
          )}
          {view === "tree" && projectEditable && (
            <span className="rm-hint">Double-click a node to switch · use List view to branch / freeze</span>
          )}
          <div className="spacer" />
          <button className="primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>

      {pickFor && (
        <FolderPicker
          mode="folder"
          title={`Import source for “${pickFor.name}”`}
          hint="Navigate to the release's C source folder"
          onCancel={() => setPickFor(null)}
          onConfirm={(path) => {
            const node = pickFor;
            setPickFor(null);
            if (node) doImportSource(node, path);
          }}
        />
      )}

      {compareWith && (
        <BaselineDiff
          baselineId={compareWith.id}
          baselineName={compareWith.name}
          onClose={() => setCompareWith(null)}
        />
      )}
    </>
  );
}
