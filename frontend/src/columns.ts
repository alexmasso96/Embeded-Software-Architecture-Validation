// Column-model helpers. The backend serves the column schema as
// [{name, type, visible, width}] where `type` is the Phase-0 logic_key string
// (e.g. "Port Search", "PortStateColumn", "Review Status"). The React table
// derives per-column rendering from that logic_key — no Qt column classes.

import type { Cell, ColumnSpec, Row } from "./api/types";

export const SEARCH_KEYS = ["Port Search", "Function Search", "Variable Search"];

// Canonical pill value → palette class, ported from src/UI/column_types.py.
export const PORT_STATE_CLASS: Record<string, string> = {
  Released: "p-green",
  "In Work": "p-yellow",
  Retired: "p-grey",
  Deleted: "p-red",
};
export const PORT_STATE_OPTIONS = ["Released", "In Work", "Retired", "Deleted"];

export const REVIEW_CLASS: Record<string, string> = {
  Reviewed: "p-green",
  "In Review": "p-yellow",
  "Not Reviewed": "p-red",
  "Broken Link": "p-grey",
};
export const REVIEW_OPTIONS = ["Not Reviewed", "In Review", "Reviewed"];

export type ColRole = "tcid" | "port" | "match" | "state" | "review" | "text";

export interface ResolvedColumn extends ColumnSpec {
  role: ColRole;
}

// Classify each visible column. A "match" column is the one immediately
// following a search column (that's where the fuzzy "Name (NN%)" result lands —
// see Logic_Symbol_Matcher.search_specs_from_layout).
export function resolveColumns(columns: ColumnSpec[]): ResolvedColumn[] {
  const matchIdx = new Set<number>();
  columns.forEach((c, i) => {
    if (SEARCH_KEYS.includes(c.type) && i + 1 < columns.length) matchIdx.add(i + 1);
  });

  return columns.map((c, i) => {
    let role: ColRole = "text";
    if (c.type === "PortStateColumn") role = "state";
    else if (c.type === "Review Status") role = "review";
    else if (SEARCH_KEYS.includes(c.type)) role = "port";
    else if (matchIdx.has(i)) role = "match";
    if (c.name === "TC. ID") role = "tcid";
    return { ...c, role };
  });
}

export function cellText(cell: Cell | undefined): string {
  if (!cell) return "";
  return (cell.widget_text ?? cell.text ?? "") as string;
}

export function getCell(row: Row, colName: string): Cell | undefined {
  return row[colName];
}

// Parse "DoorLock_Cmd (98%)" → { name, score }.
export function parseMatch(value: string): { name: string; score: number | null } {
  const m = value.match(/^(.*?)\s*\((\d+)%\)\s*$/);
  if (m) return { name: m[1], score: parseInt(m[2], 10) };
  return { name: value, score: null };
}

export function confClass(score: number | null): string {
  if (score === null) return "";
  if (score >= 80) return "conf";
  if (score >= 60) return "conf mid";
  return "conf low";
}
