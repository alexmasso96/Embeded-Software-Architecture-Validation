import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { PortRow } from "../api/types";
import {
  cellText,
  confClass,
  initCyclicValue,
  isConflict,
  parseMatch,
  pillTone,
  PORT_STATE_CLASS,
  PORT_STATE_OPTIONS,
  REVIEW_CLASS,
  REVIEW_OPTIONS,
  scoreTone,
  type ResolvedColumn,
  type Tone,
} from "../columns";
import { Menu, type MenuItem } from "./Menu";

const ROW_H = 37;

interface PillTarget {
  x: number;
  y: number;
  rowIndex: number;
  colName: string;
  options: string[];
  current: string;
}

export function PortsTable({
  columns,
  rows,
  selectedRowIndex,
  onSelectRow,
  onEditCell,
  onOpenMatch,
  onRowMenu,
  canEdit,
}: {
  columns: ResolvedColumn[];
  rows: PortRow[];
  selectedRowIndex: number | null;
  onSelectRow: (rowIndex: number) => void;
  onEditCell: (rowIndex: number, colName: string, value: string) => void;
  onOpenMatch: (rowIndex: number, col: ResolvedColumn, x: number, y: number) => void;
  onRowMenu: (rowIndex: number, x: number, y: number) => void;
  canEdit: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pill, setPill] = useState<PillTarget | null>(null);

  // Per-column widths, seeded from the backend layout and adjusted by dragging
  // the header separators. Local-only (a feel-good UX nicety) — persisting back
  // via PUT /columns can come with the column customizer.
  const [widths, setWidths] = useState<Record<string, number>>({});
  useEffect(() => {
    setWidths((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const c of columns) {
        if (next[c.name] == null) {
          next[c.name] = c.width || 120;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [columns]);
  const colWidth = (name: string, fallback: number) => widths[name] ?? fallback ?? 120;

  function startResize(e: React.MouseEvent, name: string) {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startW = colWidth(name, 120);
    const onMove = (ev: MouseEvent) => {
      const w = Math.max(56, startW + (ev.clientX - startX));
      setWidths((p) => ({ ...p, [name]: w }));
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

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 16,
  });

  const items = virtualizer.getVirtualItems();
  const totalH = virtualizer.getTotalSize();
  const padTop = items.length ? items[0].start : 0;
  const padBottom = items.length ? totalH - items[items.length - 1].end : 0;

  function openPill(
    e: React.MouseEvent,
    rowIndex: number,
    col: ResolvedColumn,
    current: string,
  ) {
    if (!canEdit) return;
    e.stopPropagation();
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPill({
      x: r.left,
      y: r.bottom + 4,
      rowIndex,
      colName: col.name,
      options: col.role === "state" ? PORT_STATE_OPTIONS : REVIEW_OPTIONS,
      current,
    });
  }

  function renderCell(row: PortRow, col: ResolvedColumn) {
    const value = cellText(row.cells[col.name]);

    if (col.role === "state" || col.role === "review") {
      if (!value) return <span className="dim">—</span>;
      const cls =
        col.role === "state"
          ? PORT_STATE_CLASS[value] ?? "p-grey"
          : REVIEW_CLASS[value] ?? "p-grey";
      return (
        <button
          className={`pill ${cls}${canEdit ? " editable" : ""}`}
          onClick={(e) => openPill(e, row.row_index, col, value)}
        >
          {value}
        </button>
      );
    }

    if (col.role === "match") {
      const { name, score } = parseMatch(value);
      const body = name ? (
        <>
          <span className="mono">{name}</span>
          {score !== null && <span className={confClass(score)}>{score}%</span>}
        </>
      ) : (
        <span className="dim">{canEdit ? "Pick…" : "—"}</span>
      );
      if (!canEdit) return body;
      return (
        <button
          className="matchcell"
          title="Pick match candidate"
          onClick={(e) => {
            e.stopPropagation();
            onSelectRow(row.row_index);
            const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
            onOpenMatch(row.row_index, col, r.left, r.bottom + 4);
          }}
        >
          {body}
        </button>
      );
    }

    if (col.role === "init" || col.role === "cyclic") {
      const { value: v, override } = initCyclicValue(col, row.cells);
      if (!v) return <span className="dim">—</span>;
      return <span className={"mono initc" + (override ? " override" : "")}>{v}</span>;
    }

    if (col.role === "tcid" || col.role === "port") {
      return <span className="mono">{value}</span>;
    }

    return value || <span className="dim">—</span>;
  }

  // Subtle background gradient for coloured cells (#4) so values read easily.
  function cellTone(row: PortRow, col: ResolvedColumn): Tone {
    const value = cellText(row.cells[col.name]);
    if (col.role === "state") return value ? pillTone(PORT_STATE_CLASS[value] ?? "p-grey") : "";
    if (col.role === "review") return value ? pillTone(REVIEW_CLASS[value] ?? "p-grey") : "";
    if (col.role === "match") return scoreTone(parseMatch(value).score);
    return "";
  }

  const pillMenuItems: MenuItem[] = pill
    ? pill.options.map((opt) => ({
        label: opt,
        checked: opt === pill.current,
        onClick: () => onEditCell(pill.rowIndex, pill.colName, opt),
      }))
    : [];

  return (
    <div className="tablewrap" ref={scrollRef}>
      <table className="ptable" style={{ tableLayout: "fixed" }}>
        <colgroup>
          {columns.map((c) => (
            <col key={c.name} style={{ width: colWidth(c.name, c.width) }} />
          ))}
          <col style={{ width: 44 }} />
        </colgroup>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.name}>
                {c.name}
                <span
                  className="col-resizer"
                  title="Drag to resize"
                  onMouseDown={(e) => startResize(e, c.name)}
                />
              </th>
            ))}
            <th />
          </tr>
        </thead>
        <tbody>
          {padTop > 0 && <tr style={{ height: padTop }} />}
          {items.map((vi) => {
            const row = rows[vi.index];
            const selected = row.row_index === selectedRowIndex;
            return (
              <tr
                key={row.row_index}
                className={"prow" + (selected ? " selected" : "")}
                style={{ height: ROW_H }}
                onClick={() => onSelectRow(row.row_index)}
              >
                {columns.map((c) => {
                  const conflict = c.role === "match" && isConflict(row.cells[c.name]);
                  const tone = conflict ? "" : cellTone(row, c);
                  const cls = conflict ? "conflict" : tone ? `tone-${tone}` : undefined;
                  return (
                    <td key={c.name} className={cls}>
                      {renderCell(row, c)}
                    </td>
                  );
                })}
                <td>
                  <button
                    className="kebab"
                    title="Row actions"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectRow(row.row_index);
                      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
                      onRowMenu(row.row_index, r.right - 170, r.bottom + 4);
                    }}
                  >
                    ⋯
                  </button>
                </td>
              </tr>
            );
          })}
          {padBottom > 0 && <tr style={{ height: padBottom }} />}
        </tbody>
      </table>

      {pill && (
        <Menu
          x={pill.x}
          y={pill.y}
          items={pillMenuItems}
          onClose={() => setPill(null)}
        />
      )}
    </div>
  );
}
