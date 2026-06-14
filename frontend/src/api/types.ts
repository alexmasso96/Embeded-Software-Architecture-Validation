// Types mirroring the FastAPI worker's JSON shapes (backend/routers/*).

export type ProjectMode = "exclusive" | "view";

export interface ProjectStatus {
  open: boolean;
  path: string | null;
  mode: ProjectMode | null;
  can_edit: boolean;
  integrity_mismatch: boolean;
  active_model: string | null;
  active_release: string | null;
  model_count: number;
  release_count: number;
  lock_info: Record<string, unknown> | null;
  lock_lost: boolean;
}

export interface ModelInfo {
  id: number;
  name: string;
  status: string;
  is_deleted: boolean;
  sort_order: number;
  is_active: boolean;
  row_count: number;
}

export interface ModelsResponse {
  models: ModelInfo[];
  active_model_id: number | null;
}

export interface ColumnSpec {
  name: string;
  type: string; // logic_key — e.g. "Port Search", "PortStateColumn", "MatchColumn"
  visible: boolean | null; // true=Show, false=Hide, null=Auto (Init/Cyclic)
  width: number;
}

export interface ColumnsResponse {
  columns: ColumnSpec[];
}

// A cell is a dict; "text" is the displayed value, "widget_text" for dropdowns.
export interface Cell {
  text?: string;
  widget_text?: string;
  widget_style?: string;
  user_changed?: boolean;
  is_purple?: boolean;
  last_func?: string;
  [k: string]: unknown;
}

export type Row = Record<string, Cell>;

export interface PortRow {
  row_index: number;
  cells: Row;
}

export interface PortsResponse {
  model_id: number;
  total: number;
  offset: number;
  limit: number;
  rows: PortRow[];
}

export interface ReleaseInfo {
  id: number;
  name: string;
  is_active?: boolean;
  selectable?: boolean;
  is_baseline?: boolean;
  [k: string]: unknown;
}

export interface ReleasesResponse {
  releases: ReleaseInfo[];
  active_release_id: number | null;
}

// Filesystem browse (dev folder picker; /api/fs)
export interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  is_arch: boolean;
}

export interface FsListResponse {
  path: string;
  parent: string | null;
  sep: string;
  entries: FsEntry[];
}

// SSE event payload off /api/events
export interface BusEvent {
  event: string; // "db-changed" | "lock" | "job" | ...
  data: Record<string, unknown>;
}
