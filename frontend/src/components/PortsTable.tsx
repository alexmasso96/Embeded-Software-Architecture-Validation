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
  canEdit,
}: {
  columns: ResolvedColumn[];
  rows: PortRow[];
  selectedRowIndex: number | null;
  onSelectRow: (rowIndex: number) => void;
  onEditCell: (rowIndex: number, colName: string, value: string) => void;
  onOpenMatch: (rowIndex: number, col: ResolvedColumn, x: number, y: number) => void;
  canEdit: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pill, setPill] = useState<PillTarget | null>(null);

  // Look up the Port State / Review Status columns by role — they drive the
  // per-row styling cascades (retired/deleted rows, reviewed match tinting).
  const stateCol = columns.find((c) => c.role === "state");
  const reviewCol = columns.find((c) => c.role === "review");

  // Per-column widths, seeded from the backend layout and adjusted by dragging
  // the header separators. Local-only (a feel-good UX nicety) — persisting back
  // via PUT /columns can come with the column customizer.
  const [widths, setWidths] = useState<Record<string, number>>({});
  useEffect(() => {
    setWidths((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const c of columns) {
        let targetW = c.width || 120;
        if (c.name === "TC. ID") targetW = 65;
        else if (c.name.endsWith(" (Init)")) targetW = 50;
        else if (c.name.endsWith(" (Cyclic)")) targetW = 55;
        else if (c.role === "review") targetW = 95;
        else if (c.role === "state") targetW = 85;

        // Force-override if the width is unset in state OR matches the database default
        if (next[c.name] == null || next[c.name] === c.width) {
          next[c.name] = targetW;
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

  function renderCell(row: PortRow, col: ResolvedColumn, reviewed: boolean) {
    const value = cellText(row.cells[col.name]);

    if (col.role === "state" || col.role === "review") {
      const displayValue = value || (col.role === "state" ? "In Work" : "Not Reviewed");
      const cls =
        col.role === "state"
          ? PORT_STATE_CLASS[displayValue] ?? "p-grey"
          : REVIEW_CLASS[displayValue] ?? "p-grey";
      return (
        <button
          className={`cell-btn ${cls}${canEdit ? " editable" : ""}`}
          onClick={(e) => openPill(e, row.row_index, col, displayValue)}
        >
          {displayValue}
        </button>
      );
    }

    if (col.role === "match") {
      const { name, score } = parseMatch(value);

      // B6: an empty cell renders the fallback em-dash and exposes no picker
      // trigger, even when the table is editable.
      if (!name) {
        return <span className="dim">—</span>;
      }

      // B5: reviewed rows tint the match green and drop the % score.
      const showScore = !reviewed && score !== null;
      const matchClass = reviewed ? " reviewed-match" : "";

      if (!canEdit) {
        return (
          <div className={"matchcell-readonly" + matchClass}>
            <span className="mono match-name">{name}</span>
            {showScore && <span className={confClass(score)}>{score}%</span>}
          </div>
        );
      }

      return (
        <button
          className={"matchcell" + matchClass}
          title="Pick match candidate"
          onClick={(e) => {
            e.stopPropagation();
            onSelectRow(row.row_index);
            const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
            onOpenMatch(row.row_index, col, r.left, r.bottom + 4);
          }}
        >
          <span className="mono match-name">{name}</span>
          {showScore && <span className={confClass(score)}>{score}%</span>}
        </button>
      );
    }

    if (col.role === "init" || col.role === "cyclic") {
      const { value: v, override } = initCyclicValue(col, row.cells);
      if (!v) return <span className="dim">—</span>;
      return <span className={"mono initc" + (override ? " override" : "")}>{v}</span>;
    }

    if (col.role === "tcid" || col.role === "port") {
      // B6: fallback em-dash for empty non-status cells.
      return value ? <span className="mono">{value}</span> : <span className="dim">—</span>;
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
          </tr>
        </thead>
        <tbody>
          {padTop > 0 && <tr style={{ height: padTop }} />}
          {items.map((vi) => {
            const row = rows[vi.index];
            const selected = row.row_index === selectedRowIndex;
            const stateVal = stateCol ? cellText(row.cells[stateCol.name]) : "";
            const reviewed =
              !!reviewCol && cellText(row.cells[reviewCol.name]) === "Reviewed";
            const rowCls =
              "prow" +
              (selected ? " selected" : "") +
              (stateVal === "Retired" ? " retired" : "") +
              (stateVal === "Deleted" ? " deleted" : "");
            return (
              <tr
                key={row.row_index}
                className={rowCls}
                style={{ height: ROW_H }}
                onClick={() => onSelectRow(row.row_index)}
              >
                {columns.map((c) => {
                  const conflict = c.role === "match" && isConflict(row.cells[c.name]);
                  // B5: reviewed match cells read green regardless of score.
                  const tone =
                    conflict
                      ? ""
                      : reviewed && c.role === "match"
                        ? "ok"
                        : cellTone(row, c);
                  const isPillCol = c.role === "state" || c.role === "review";
                  const cls = [
                    conflict ? "conflict" : tone ? `tone-${tone}` : "",
                    isPillCol ? "cell-button-td" : "",
                  ].filter(Boolean).join(" ");
                  return (
                    <td key={c.name} className={cls || undefined}>
                      {renderCell(row, c, reviewed)}
                    </td>
                  );
                })}
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
