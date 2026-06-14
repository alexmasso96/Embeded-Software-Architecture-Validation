// Column-model helpers. The backend serves the column schema as
// [{name, type, visible, width}] where `type` is the Phase-0 logic_key string
// (e.g. "Port Search", "PortStateColumn", "Review Status"). The React table
// derives per-column rendering from that logic_key — no Qt column classes.

import type { Cell, ColumnSpec, Row } from "./api/types";

export const SEARCH_KEYS = ["Port Search", "Function Search", "Variable Search"];

// Search logic_key → the `kind` the /api/symbols endpoint expects.
// Mirrors Logic_Symbol_Matcher._SEARCH_KIND_BY_LOGIC.
export type SymbolKind = "function" | "variable" | "any";
export const SEARCH_KIND: Record<string, SymbolKind> = {
  "Port Search": "any",
  "Function Search": "function",
  "Variable Search": "variable",
};

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

export type ColRole =
  | "tcid"
  | "port"
  | "match"
  | "state"
  | "review"
  | "init"
  | "cyclic"
  | "text";

export interface ResolvedColumn extends ColumnSpec {
  role: ColRole;
  // For a "match" column: the search column feeding it and the symbol kind to
  // query. For "init"/"cyclic": the Match column whose function drives the value.
  searchCol?: string;
  kind?: SymbolKind;
  funcCol?: string;
}

// Classify each visible column. A "match" column is the one immediately
// following a search column (that's where the fuzzy "Name (NN%)" result lands —
// see Logic_Symbol_Matcher.search_specs_from_layout).
export function resolveColumns(columns: ColumnSpec[]): ResolvedColumn[] {
  // match column index → its source search column
  const matchSource = new Map<number, ColumnSpec>();
  columns.forEach((c, i) => {
    if (SEARCH_KEYS.includes(c.type) && i + 1 < columns.length) {
      matchSource.set(i + 1, c);
    }
  });

  return columns.map((c, i) => {
    let role: ColRole = "text";
    if (c.type === "PortStateColumn") role = "state";
    else if (c.type === "Review Status") role = "review";
    else if (c.type === "InitColumn") role = "init";
    else if (c.type === "CyclicColumn") role = "cyclic";
    else if (SEARCH_KEYS.includes(c.type)) role = "port";
    else if (matchSource.has(i)) role = "match";
    if (c.name === "TC. ID") role = "tcid";

    if (role === "match") {
      const src = matchSource.get(i)!;
      return { ...c, role, searchCol: src.name, kind: SEARCH_KIND[src.type] ?? "any" };
    }
    if (role === "init" || role === "cyclic") {
      // "Input Port (Init)" / "(Cyclic)" derive from "Input Port (Match)".
      const funcCol = c.name.replace(/ \((Init|Cyclic)\)$/, " (Match)");
      return { ...c, role, funcCol };
    }
    return { ...c, role };
  });
}

// ---- Init / Cyclic derivation (ported from column_types.InitColumn/CyclicColumn) ----
export const DEFAULT_CYCLICITY = "10";

// "1" if the matched function looks like an init function, else "0".
export function initValueFor(funcName: string): string {
  return funcName.toLowerCase().includes("init") ? "1" : "0";
}

// Parse "<n>ms" → n, a generic "cyclic" tag → the default, else "0".
export function cyclicValueFor(funcName: string, deflt = DEFAULT_CYCLICITY): string {
  if (!funcName) return "0";
  const m = funcName.toLowerCase().match(/(\d+)ms/);
  if (m) return m[1];
  if (funcName.toLowerCase().includes("cyclic")) return deflt;
  return "0";
}

// The displayed Init/Cyclic value for a row: a stored user override wins,
// otherwise it's auto-derived from the adjacent Match column's function. Empty
// when there is no matched function yet. `override` flags a manual value.
export function initCyclicValue(
  col: ResolvedColumn,
  row: Row,
): { value: string; override: boolean } {
  const cell = row[col.name];
  const stored = cellText(cell);
  if (cell?.user_changed && stored) return { value: stored, override: true };
  const funcName = col.funcCol ? parseMatch(cellText(row[col.funcCol])).name : "";
  if (!funcName) return { value: "", override: false };
  const value = col.role === "init" ? initValueFor(funcName) : cyclicValueFor(funcName);
  return { value, override: false };
}

// A match cell carries a conflict warning (purple) when the stored, previously
// accepted match no longer agrees with the auto-best — e.g. after a release
// switch. The flag is backend-driven; the picker clears it on acknowledgment.
export function isConflict(cell: Cell | undefined): boolean {
  return !!cell?.is_purple;
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

// Semantic tone of a coloured value → a subtle cell-background gradient class so
// percentages / states read more easily (#4). "" = no tint.
export type Tone = "ok" | "warn" | "err" | "grey" | "";

const PILL_TONE: Record<string, Tone> = {
  "p-green": "ok",
  "p-yellow": "warn",
  "p-red": "err",
  "p-grey": "grey",
};

export function scoreTone(score: number | null): Tone {
  if (score === null) return "";
  if (score >= 80) return "ok";
  if (score >= 60) return "warn";
  return "err";
}

export function pillTone(cls: string): Tone {
  return PILL_TONE[cls] ?? "";
}
