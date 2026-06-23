import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useColumns, useModels, usePorts, useReleases } from "../api/hooks";
import { useSSE } from "../api/useSSE";
import type { ProjectStatus } from "../api/types";
import {
  cellText,
  initCyclicValue,
  parseMatch,
  resolveColumns,
  type ResolvedColumn,
} from "../columns";
import { Sidebar } from "../components/Sidebar";
import { ModelManager } from "../components/ModelManager";
import { ReleaseManager } from "../components/ReleaseManager";
import { getReleaseRecents, touchReleaseRecent } from "../releaseRecents";
import { ImportWizard } from "../components/ImportWizard";
import { ColumnCustomizer } from "../components/ColumnCustomizer";
import { PortsTable } from "../components/PortsTable";
import { MatchPicker } from "../components/MatchPicker";
import { Inspector } from "../components/Inspector";
import { HistoryModal } from "../components/HistoryModal";
import { StatusBar } from "../components/StatusBar";
import { Menu, type MenuItem } from "../components/Menu";

interface RowMenu {
  x: number;
  y: number;
  rowIndex: number;
}

interface MatchTarget {
  x: number;
  y: number;
  rowIndex: number;
  col: ResolvedColumn;
}

type FilterMode = "all" | "reviewed" | "not-reviewed" | "conflicts" | "broken";

// Background jobs that mutate the port table — when one of these finishes we
// must refetch so the grid reflects the new matches/symbols.
const MUTATING_JOBS = new Set(["fuzzy_rematch", "import_symbols", "parse_elf"]);

export function Workspace({
  status,
  onReloadStatus,
  toast,
  importOpen,
  onCloseImport,
  columnsOpen,
  onCloseColumns,
  onShowInCodeMap,
}: {
  status: ProjectStatus;
  onReloadStatus: () => void;
  toast: (msg: string) => void;
  importOpen: boolean;
  onCloseImport: () => void;
  columnsOpen: boolean;
  onCloseColumns: () => void;
  onShowInCodeMap: (funcName: string) => void;
}) {
  const open = status.open;
  const canEdit = status.can_edit && !status.lock_lost;

  const models = useModels(open);
  const columns = useColumns(open);
  const releases = useReleases(open);

  const [activeModelId, setActiveModelId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  // Independent Port-State visibility toggles (ported from the old table's
  // show_retired/show_deleted). Defaults match the old app: Retired visible,
  // Deleted hidden.
  const [showRetired, setShowRetired] = useState(true);
  const [showDeleted, setShowDeleted] = useState(false);
  const [filterMenu, setFilterMenu] = useState<{ x: number; y: number } | null>(null);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [rowMenu, setRowMenu] = useState<RowMenu | null>(null);
  const [matchTarget, setMatchTarget] = useState<MatchTarget | null>(null);
  const [historyTarget, setHistoryTarget] = useState<{
    title: string;
    subtitle?: string;
    query: string;
  } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // ⌘/Ctrl+F (handled globally in App) fires this event; focus + select the box.
  useEffect(() => {
    const onFocus = () => {
      searchRef.current?.focus();
      searchRef.current?.select();
    };
    window.addEventListener("focus-search-input", onFocus);
    return () => window.removeEventListener("focus-search-input", onFocus);
  }, []);
  const [manageOpen, setManageOpen] = useState(false);
  const [releaseMgrOpen, setReleaseMgrOpen] = useState(false);
  const [recentReleaseIds, setRecentReleaseIds] = useState<number[]>(() =>
    getReleaseRecents(status.path),
  );
  const [sidebarWidth, setSidebarWidth] = useState(230);

  // Re-read recents when the open project changes (ids are per-project).
  useEffect(() => {
    setRecentReleaseIds(getReleaseRecents(status.path));
  }, [status.path]);

  // The active release is, by definition, the most-recently-accessed one. Track
  // it off the authoritative server value so every switch (sidebar, branch, or
  // manager "Activate") feeds the dropdown's recents — no guessing pre-refetch.
  const activeReleaseId = releases.data?.active_release_id ?? null;
  useEffect(() => {
    if (activeReleaseId != null) {
      setRecentReleaseIds(touchReleaseRecent(status.path, activeReleaseId));
    }
  }, [activeReleaseId, status.path]);

  function startSidebarResize(e: React.MouseEvent) {
    e.preventDefault();
    const startX = e.clientX;
    const startW = sidebarWidth;
    const onMove = (ev: MouseEvent) => {
      setSidebarWidth(Math.min(480, Math.max(170, startW + (ev.clientX - startX))));
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

  // Default the selected model to the server's active model once loaded, and
  // re-home the selection if the current model vanished (e.g. soft-deleted via
  // the model manager) so the table never queries a stale id.
  useEffect(() => {
    if (!models.data) return;
    const exists = models.data.models.some((m) => m.id === activeModelId);
    if (activeModelId === null || !exists) {
      setActiveModelId(models.data.active_model_id ?? models.data.models[0]?.id ?? null);
    }
  }, [models.data, activeModelId]);

  const ports = usePorts(activeModelId);

  // Refetch on relevant server-side changes (other clients, jobs, our edits).
  function refreshAll() {
    models.reload();
    columns.reload();
    releases.reload();
    ports.reload();
    onReloadStatus();
  }

  // Live-refresh when a port-mutating job finishes (the Re-match Symbols button,
  // or an import's auto-match) or another client changes the DB. Without this the
  // grid kept showing stale/empty Match cells until a manual model switch.
  useSSE((e) => {
    if (e.event === "db-changed") {
      refreshAll();
    } else if (
      e.event === "job" &&
      e.data?.status === "done" &&
      MUTATING_JOBS.has(String(e.data?.kind))
    ) {
      refreshAll();
    }
  }, open);

  const allRows = ports.data?.rows ?? [];

  const resolved = useMemo(() => {
    if (!columns.data) return [];
    return resolveColumns(columns.data.columns, columns.data.result_columns).filter((c) => {
      if (c.visible === true) return true;
      if (c.visible === false) return false;
      // null = "Auto" (Init/Cyclic): show only when some row has a meaningful value.
      return allRows.some((r) => {
        const { value } = initCyclicValue(c, r.cells);
        return value && value !== "0";
      });
    });
  }, [columns.data, allRows]);
  const reviewCol = resolved.find((c) => c.role === "review");
  const stateCol = resolved.find((c) => c.role === "state");
  const matchColNames = useMemo(
    () => resolved.filter((c) => c.role === "match").map((c) => c.name),
    [resolved],
  );

  // Rows are narrowed by Port-State visibility, then the scope filter, then the
  // text query.
  const filtered = useMemo(() => {
    let rows = allRows;
    if (stateCol && (!showRetired || !showDeleted)) {
      rows = rows.filter((r) => {
        const s = cellText(r.cells[stateCol.name]);
        if (s === "Retired" && !showRetired) return false;
        if (s === "Deleted" && !showDeleted) return false;
        return true;
      });
    }
    if (filterMode !== "all") {
      rows = rows.filter((r) => {
        if (filterMode === "conflicts") {
          return matchColNames.some((n) => r.cells[n]?.is_purple === true);
        }
        if (!reviewCol) return false;
        const review = cellText(r.cells[reviewCol.name]);
        if (filterMode === "reviewed") return review === "Reviewed";
        if (filterMode === "not-reviewed") return review === "Not Reviewed";
        if (filterMode === "broken") return review === "Broken Link";
        return true;
      });
    }
    const q = query.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) =>
        Object.values(r.cells).some((cell) =>
          cellText(cell).toLowerCase().includes(q),
        ),
      );
    }
    return rows;
  }, [allRows, query, filterMode, reviewCol, matchColNames, stateCol, showRetired, showDeleted]);

  const reviewedCount = reviewCol
    ? allRows.filter((r) => cellText(r.cells[reviewCol.name]) === "Reviewed").length
    : 0;

  const filterMenuItems: MenuItem[] = [
    { label: "Show All", checked: filterMode === "all", onClick: () => setFilterMode("all") },
    {
      label: "Show Reviewed Only",
      checked: filterMode === "reviewed",
      onClick: () => setFilterMode("reviewed"),
    },
    {
      label: "Show Not Reviewed Only",
      checked: filterMode === "not-reviewed",
      onClick: () => setFilterMode("not-reviewed"),
    },
    {
      label: "Show Conflicts Only",
      checked: filterMode === "conflicts",
      onClick: () => setFilterMode("conflicts"),
    },
    {
      label: "Show Broken Links Only",
      checked: filterMode === "broken",
      onClick: () => setFilterMode("broken"),
    },
    { separator: true },
    {
      label: "Show Retired Ports",
      checked: showRetired,
      // Keep the menu open so both visibility toggles can be flipped at once.
      onClick: () => setShowRetired((v) => !v),
      keepOpen: true,
    },
    {
      label: "Show Deleted Ports",
      checked: showDeleted,
      onClick: () => setShowDeleted((v) => !v),
      keepOpen: true,
    },
  ];

  const activeModel = models.data?.models.find((m) => m.id === activeModelId) ?? null;
  const selectedRowData =
    selectedRow !== null ? allRows.find((r) => r.row_index === selectedRow) : null;
  const portCol = resolved.find((c) => c.role === "port" || c.role === "tcid");
  const selectedLabel = selectedRowData
    ? `Row ${selectedRow}${
        portCol ? ` · ${cellText(selectedRowData.cells[portCol.name])}` : ""
      }`
    : null;

  async function editCell(rowIndex: number, colName: string, value: string) {
    if (activeModelId === null) return;
    try {
      await api.patch(`/models/${activeModelId}/ports/${rowIndex}`, {
        updates: { [colName]: value },
      });
      ports.reload();
    } catch (e) {
      toast(`Edit failed: ${(e as Error).message}`);
    }
  }

  // Persist a chosen fuzzy-match candidate into its Match cell. Writes the
  // canonical "Name (NN%)" into widget_text, records the user's acknowledgment
  // (user_changed), and clears any conflict tint (is_purple → false). Merges
  // onto the existing cell so other fields (e.g. last_func) survive.
  async function pickMatch(
    rowIndex: number,
    colName: string,
    name: string,
    score: number,
  ) {
    if (activeModelId === null) return;
    const row = allRows.find((r) => r.row_index === rowIndex);
    const existing = row?.cells[colName] ?? {};
    const text = `${name} (${score}%)`;
    const cell = {
      ...existing,
      text,
      widget_text: text,
      user_changed: true,
      is_purple: false,
    };
    try {
      await api.patch(`/models/${activeModelId}/ports/${rowIndex}`, {
        updates: { [colName]: cell },
      });
      ports.reload();
    } catch (e) {
      toast(`Match update failed: ${(e as Error).message}`);
    }
  }

  // Open the match picker for a row's first Match column (used by the Inspector
  // strip, which has no per-cell anchor — anchor at the triggering button).
  function openMatchForSelected(e: React.MouseEvent) {
    if (selectedRow === null) return;
    const matchCol = resolved.find((c) => c.role === "match");
    if (!matchCol) {
      toast("No match column in this model");
      return;
    }
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setMatchTarget({ rowIndex: selectedRow, col: matchCol, x: r.left, y: r.bottom + 4 });
  }

  function openPortHistory(rowIndex: number) {
    const row = allRows.find((r) => r.row_index === rowIndex);
    // History entries key on the Port Search column value (what the backend
    // records), so scope by that column — not the TC.ID column that `portCol`
    // prefers for the row label.
    const portSearchCol = resolved.find((c) => c.role === "port");
    const name = (
      row && portSearchCol ? cellText(row.cells[portSearchCol.name]) : ""
    ).trim();
    const port = name || "N/A";
    const params = new URLSearchParams();
    if (activeModel?.name) params.set("model_name", activeModel.name);
    params.set("port", port);
    setHistoryTarget({
      title: "Port History",
      subtitle: `Row ${rowIndex + 1}${name ? ` · ${name}` : ""}`,
      query: `?${params.toString()}`,
    });
  }

  function openModelHistory() {
    const params = new URLSearchParams();
    if (activeModel?.name) params.set("model_name", activeModel.name);
    const qs = params.toString();
    setHistoryTarget({
      title: "Change History",
      subtitle: activeModel?.name ?? undefined,
      query: qs ? `?${qs}` : "",
    });
  }

  // Jump to the Code Map focused on the function matched to the selected port.
  function showSelectedInCodeMap() {
    if (selectedRow === null || !selectedRowData) return;
    const matchCol = resolved.find((c) => c.role === "match");
    const fn = matchCol
      ? parseMatch(cellText(selectedRowData.cells[matchCol.name])).name
      : "";
    if (!fn) {
      toast("No matched function for this port");
      return;
    }
    onShowInCodeMap(fn);
  }

  async function deleteRow(rowIndex: number) {
    if (activeModelId === null) return;
    try {
      await api.del(`/models/${activeModelId}/ports/${rowIndex}`);
      setSelectedRow(null);
      ports.reload();
      toast("Row deleted");
    } catch (e) {
      toast(`Delete failed: ${(e as Error).message}`);
    }
  }

  async function duplicateRow(rowIndex: number) {
    if (activeModelId === null) return;
    const src = allRows.find((r) => r.row_index === rowIndex);
    if (!src) return;
    try {
      await api.post(`/models/${activeModelId}/ports/bulk`, { rows: [src.cells] });
      ports.reload();
      toast("Row duplicated");
    } catch (e) {
      toast(`Duplicate failed: ${(e as Error).message}`);
    }
  }

  async function retireRow(rowIndex: number) {
    const stateCol = resolved.find((c) => c.role === "state");
    if (!stateCol) {
      toast("No port-state column to retire into");
      return;
    }
    await editCell(rowIndex, stateCol.name, "Retired");
    toast("Row retired");
  }

  async function addPort() {
    if (activeModelId === null) return;
    try {
      await api.post(`/models/${activeModelId}/ports`);
      ports.reload();
    } catch (e) {
      toast(`Add failed: ${(e as Error).message}`);
    }
  }

  async function rematch() {
    if (activeModelId === null) return;
    try {
      await api.post("/jobs/fuzzy_rematch", { model_id: activeModelId });
      toast("Re-match started — results stream in");
    } catch (e) {
      toast(`Re-match failed: ${(e as Error).message}`);
    }
  }

  const rowMenuItems: MenuItem[] = rowMenu
    ? [
        {
          label: "Show in Code Map",
          onClick: () => {
            setSelectedRow(rowMenu.rowIndex);
            const row = allRows.find((r) => r.row_index === rowMenu.rowIndex);
            const matchCol = resolved.find((c) => c.role === "match");
            const fn =
              row && matchCol
                ? parseMatch(cellText(row.cells[matchCol.name])).name
                : "";
            if (fn) onShowInCodeMap(fn);
            else toast("No matched function for this port");
          },
        },
        {
          label: "Port history…",
          onClick: () => openPortHistory(rowMenu.rowIndex),
        },
        ...(canEdit
          ? [
              { label: "Duplicate", onClick: () => duplicateRow(rowMenu.rowIndex) },
              { label: "Retire", onClick: () => retireRow(rowMenu.rowIndex) },
              { label: "Delete", danger: true, onClick: () => deleteRow(rowMenu.rowIndex) },
            ]
          : []),
      ]
    : [];

  const loading = models.loading || columns.loading || ports.loading;
  const err = models.error || columns.error || ports.error;

  return (
    <>
      <div className="body">
        <Sidebar
          models={models.data?.models ?? []}
          activeModelId={activeModelId}
          onSelectModel={async (id) => {
            // Activate server-side first so the worker's active model matches the
            // client (fixes models other than the default showing no data), then
            // sync local selection and refetch models/ports/status.
            try {
              await api.post(`/models/${id}/activate`);
              setActiveModelId(id);
              setSelectedRow(null);
              refreshAll();
            } catch (e) {
              toast(`Switch model failed: ${(e as Error).message}`);
            }
          }}
          onManageModels={() => setManageOpen(true)}
          releases={releases.data?.releases ?? []}
          activeReleaseId={activeReleaseId}
          recentReleaseIds={recentReleaseIds}
          onSelectRelease={async (id) => {
            try {
              await api.post(`/releases/${id}/activate`);
              refreshAll();
            } catch (e) {
              toast(`Switch release failed: ${(e as Error).message}`);
            }
          }}
          onManageReleases={() => setReleaseMgrOpen(true)}
          canEdit={canEdit}
          width={sidebarWidth}
        />

        <div
          className="sidebar-resizer"
          title="Drag to resize"
          onMouseDown={startSidebarResize}
        />

        <div className="main">
          {status.active_release_is_baseline && (
            <div className="baseline-banner">
              <span>
                🔒 Viewing baseline <b>{status.active_release}</b> — read-only snapshot.
              </span>
              <button
                className="scope-btn"
                onClick={() => {
                  // Exit by switching to the most recent real (non-baseline) release.
                  const target = (releases.data?.releases ?? []).find(
                    (r) => r.selectable,
                  );
                  if (!target) {
                    toast("No editable release to return to.");
                    return;
                  }
                  api
                    .post(`/releases/${target.id}/activate`)
                    .then(() => refreshAll())
                    .catch((e) => toast(`Exit baseline failed: ${(e as Error).message}`));
                }}
              >
                Exit baseline
              </button>
            </div>
          )}
          <div className="scopebar">
            <div className="search">
              ⌕
              <input
                ref={searchRef}
                placeholder="Search ports…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button
              className={"scope-btn" + (filterMode !== "all" ? " active" : "")}
              onClick={(e) => {
                const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
                setFilterMenu({ x: r.left, y: r.bottom + 4 });
              }}
            >
              Filter ▾
            </button>
            <button className="scope-btn" disabled={!canEdit} onClick={rematch}>
              Re-match Symbols
            </button>
            <div className="spacer" />
            <button className="scope-btn" disabled={!canEdit} onClick={addPort}>
              ＋ Add Port
            </button>
          </div>

          {err ? (
            <div className="center-msg" style={{ color: "var(--red)" }}>
              {err}
            </div>
          ) : loading && allRows.length === 0 ? (
            <div className="center-msg">
              <span className="spin" />
              &nbsp;Loading…
            </div>
          ) : activeModelId === null ? (
            <div className="center-msg">No model selected.</div>
          ) : (
            <PortsTable
              columns={resolved}
              rows={filtered}
              selectedRowIndex={selectedRow}
              onSelectRow={setSelectedRow}
              onEditCell={editCell}
              onOpenMatch={(rowIndex, col, x, y) =>
                setMatchTarget({ rowIndex, col, x, y })
              }
              canEdit={canEdit}
              modelStatus={activeModel?.status ?? "In Work"}
            />
          )}

          <Inspector
            label={selectedLabel}
            canEdit={canEdit}
            onPickMatch={openMatchForSelected}
            onShowInCodeMap={showSelectedInCodeMap}
            onHistory={() => selectedRow !== null && openPortHistory(selectedRow)}
            onModelHistory={openModelHistory}
            onDuplicate={() => selectedRow !== null && duplicateRow(selectedRow)}
            onRetire={() => selectedRow !== null && retireRow(selectedRow)}
          />
        </div>
      </div>

      <StatusBar
        status={status}
        modelName={activeModel?.name ?? null}
        modelStatus={activeModel?.status ?? null}
        rowCount={allRows.length}
        reviewedCount={reviewedCount}
      />

      {filterMenu && (
        <Menu
          x={filterMenu.x}
          y={filterMenu.y}
          items={filterMenuItems}
          onClose={() => setFilterMenu(null)}
        />
      )}

      {rowMenu && (
        <Menu
          x={rowMenu.x}
          y={rowMenu.y}
          items={rowMenuItems}
          onClose={() => setRowMenu(null)}
        />
      )}

      {manageOpen && (
        <ModelManager
          canEdit={canEdit}
          onClose={() => setManageOpen(false)}
          onChanged={refreshAll}
          toast={toast}
        />
      )}

      {releaseMgrOpen && (
        <ReleaseManager
          projectEditable={status.mode === "exclusive" && !status.lock_lost}
          onClose={() => setReleaseMgrOpen(false)}
          onChanged={refreshAll}
          toast={toast}
        />
      )}

      {importOpen && (
        <ImportWizard
          activeModelId={activeModelId}
          activeModelName={activeModel?.name ?? null}
          currentRelease={status.active_release}
          columns={columns.data?.columns ?? []}
          onChanged={refreshAll}
          onClose={onCloseImport}
        />
      )}

      {columnsOpen && (
        <ColumnCustomizer
          canEdit={canEdit}
          onClose={onCloseColumns}
          onChanged={refreshAll}
          toast={toast}
        />
      )}

      {matchTarget && (
        <MatchPicker
          x={matchTarget.x}
          y={matchTarget.y}
          kind={matchTarget.col.kind ?? "any"}
          initialQuery={cellText(
            allRows.find((r) => r.row_index === matchTarget.rowIndex)?.cells[
              matchTarget.col.searchCol ?? ""
            ],
          )}
          current={
            parseMatch(
              cellText(
                allRows.find((r) => r.row_index === matchTarget.rowIndex)?.cells[
                  matchTarget.col.name
                ],
              ),
            ).name
          }
          onPick={(name, score) =>
            pickMatch(matchTarget.rowIndex, matchTarget.col.name, name, score)
          }
          onClose={() => setMatchTarget(null)}
        />
      )}

      {historyTarget && (
        <HistoryModal
          title={historyTarget.title}
          subtitle={historyTarget.subtitle}
          query={historyTarget.query}
          onClose={() => setHistoryTarget(null)}
        />
      )}
    </>
  );
}
