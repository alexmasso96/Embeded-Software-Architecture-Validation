import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useColumns, useModels, usePorts, useReleases } from "../api/hooks";
import type { ProjectStatus } from "../api/types";
import { cellText, resolveColumns } from "../columns";
import { Sidebar } from "../components/Sidebar";
import { PortsTable } from "../components/PortsTable";
import { Inspector } from "../components/Inspector";
import { StatusBar } from "../components/StatusBar";
import { Menu, type MenuItem } from "../components/Menu";

interface RowMenu {
  x: number;
  y: number;
  rowIndex: number;
}

export function Workspace({
  status,
  onReloadStatus,
  toast,
}: {
  status: ProjectStatus;
  onReloadStatus: () => void;
  toast: (msg: string) => void;
}) {
  const open = status.open;
  const canEdit = status.can_edit && !status.lock_lost;

  const models = useModels(open);
  const columns = useColumns(open);
  const releases = useReleases(open);

  const [activeModelId, setActiveModelId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [rowMenu, setRowMenu] = useState<RowMenu | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(230);

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

  // Default the selected model to the server's active model once loaded.
  useEffect(() => {
    if (models.data && activeModelId === null) {
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

  const resolved = useMemo(
    () => (columns.data ? resolveColumns(columns.data.columns).filter((c) => c.visible) : []),
    [columns.data],
  );

  const allRows = ports.data?.rows ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allRows;
    return allRows.filter((r) =>
      Object.values(r.cells).some((cell) =>
        cellText(cell).toLowerCase().includes(q),
      ),
    );
  }, [allRows, query]);

  const reviewCol = resolved.find((c) => c.role === "review");
  const reviewedCount = reviewCol
    ? allRows.filter((r) => cellText(r.cells[reviewCol.name]) === "Reviewed").length
    : 0;

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
        { label: "Show in Code Map", onClick: () => toast("Code Map: later slice") },
        { label: "Port history…", onClick: () => toast("History: later slice") },
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
          onSelectModel={(id) => {
            setActiveModelId(id);
            setSelectedRow(null);
          }}
          onManageModels={() => toast("Model management: later slice")}
          releases={releases.data?.releases ?? []}
          activeReleaseId={releases.data?.active_release_id ?? null}
          onSelectRelease={async (id) => {
            try {
              await api.post(`/releases/${id}/activate`);
              refreshAll();
            } catch (e) {
              toast(`Switch release failed: ${(e as Error).message}`);
            }
          }}
          canEdit={canEdit}
          width={sidebarWidth}
        />

        <div
          className="sidebar-resizer"
          title="Drag to resize"
          onMouseDown={startSidebarResize}
        />

        <div className="main">
          <div className="scopebar">
            <div className="search">
              ⌕
              <input
                placeholder="Search ports…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <button className="scope-btn" onClick={() => toast("Filter: later slice")}>
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
              onRowMenu={(rowIndex, x, y) => setRowMenu({ rowIndex, x, y })}
              canEdit={canEdit}
            />
          )}

          <Inspector
            label={selectedLabel}
            canEdit={canEdit}
            onPickMatch={() => toast("Match picker: later slice")}
            onShowInCodeMap={() => toast("Code Map: later slice")}
            onHistory={() => toast("History: later slice")}
            onDuplicate={() => selectedRow !== null && duplicateRow(selectedRow)}
            onRetire={() => selectedRow !== null && retireRow(selectedRow)}
          />
        </div>
      </div>

      <StatusBar
        status={status}
        modelName={activeModel?.name ?? null}
        rowCount={allRows.length}
        reviewedCount={reviewedCount}
      />

      {rowMenu && (
        <Menu
          x={rowMenu.x}
          y={rowMenu.y}
          items={rowMenuItems}
          onClose={() => setRowMenu(null)}
        />
      )}
    </>
  );
}
