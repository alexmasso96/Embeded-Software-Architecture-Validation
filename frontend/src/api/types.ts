// Types mirroring the FastAPI worker's JSON shapes (backend/routers/*).

export type ProjectMode = "exclusive" | "view";

export interface ProjectStatus {
  open: boolean;
  path: string | null;
  mode: ProjectMode | null;
  can_edit: boolean;
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
  elf_hash?: string | null;
  elf_path?: string | null;
  has_source?: boolean;
  [k: string]: unknown;
}

export interface ReleasesResponse {
  releases: ReleaseInfo[];
  active_release_id: number | null;
}

// Release & Baseline Manager lineage (GET /api/releases/lineage). Includes
// soft-deleted nodes so the tree can keep their grid cells as spacers.
export interface LineageNode {
  id: number;
  name: string;
  is_baseline: boolean;
  is_deleted: boolean;
  is_active: boolean;
  parent_release_name: string | null;
  description: string;
  timestamp: string;
  row_count: number;
  elf_hash: string | null;
  has_source: boolean;
  grid_x: number;
  grid_y: number;
}

export interface LineageResponse {
  active_release_id: number | null;
  nodes: LineageNode[];
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

// Code Map (GET /api/codemap*) — mirrors backend/routers/codemap.py.
export interface CodeMapResponse {
  model_id: number;
  function_count: number;
  functions: string[];
  global_count: number;
  define_count: number;
}

export type GraphNodeType = "center" | "caller" | "callee";

export interface GraphNode {
  name: string;
  level: number; // <0 caller side, 0 focus, >0 callee side
  type: GraphNodeType;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: "caller" | "callee";
}

export interface CodeMapGraph {
  focus: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  truncated: boolean;
  max_nodes?: number;
}

export interface GlobalMatch {
  name: string;
  type: string;
}

export interface FunctionDetail {
  name: string;
  address: number;
  size: number;
  signature: string | null;
  return_type: string | null;
  file: string | null;
  line_start: number | null;
  callers: string[];
  callees: string[];
  globals: GlobalMatch[];
  tooltip_html: string;
}

export interface SourceResponse {
  name: string;
  file: string | null;
  line_start?: number;
  found: boolean;
  source: string;
  reason?: string;
}

// Change Log (GET /api/changelog*) — mirrors backend/routers/changelog.py.
export type DiffStatus = "modified" | "added" | "deleted" | string;

export interface ChangelogFile {
  file_path: string;
  status: DiffStatus;
}

export interface ChangelogResponse {
  model_id: number;
  diff_hash: string | null;
  files: ChangelogFile[];
  ai_change_log: string;
}

// Aligned side-by-side diff. Each line is a [text, kind] pair; kind is one of
// "deleted" | "added" | "empty" | "header" | "unchanged".
export type DiffLineKind =
  | "deleted"
  | "added"
  | "empty"
  | "header"
  | "unchanged";
export type DiffLine = [string, DiffLineKind];

export interface FileDiffResponse {
  model_id: number;
  file_path: string;
  status: DiffStatus;
  old: DiffLine[];
  new: DiffLine[];
}

// Logical drives / volume roots (GET /api/fs/drives) — picker shortcuts.
export interface DriveEntry {
  name: string;
  path: string;
}

// Source-Level Test Code Injection (/api/injection/*) ----------------------
export interface TestProject {
  id: number;
  name: string;
  created_at: string;
  file_count: number;
  injection_count: number;
}

export interface TestProjectFile {
  rel_path: string;
  size: number;
  ext: string | null;
}

export interface SourceFileInfo {
  rel_path: string;
  size: number;
  ext: string | null;
}

// A hook, annotated by the backend with its live resolution. confidence is out
// of 4: 4 = both anchors, 3 = single anchor, 0 = conflict (render a placeholder).
export interface InjectionHook {
  id: number;
  test_project_id: number;
  src_file_path: string;
  function_name: string;
  line_above_code: string;
  line_below_code: string;
  injected_code: string;
  offset_lines: number;
  created_at: string;
  resolved_index: number | null;
  confidence: number;
  anchor: "both" | "above" | "below" | "none";
}

export interface ResolveResult {
  index: number | null;
  confidence: number;
  anchor: "both" | "above" | "below" | "none";
}

export interface ShiftResult {
  ok: boolean;
  reason?: string;
  index?: number;
  line_above_code?: string;
  line_below_code?: string;
  offset_lines?: number;
}

export type TerminalKind = "cmd" | "powershell" | "bash" | "wsl";

export interface BuildSettings {
  terminal: TerminalKind;
  wsl_distro: string;
  build_command: string;
  build_cwd: string;
}

// AI providers (GET /api/ai/providers) — mirrors backend/routers/ai.py.
export interface AIModel {
  id: string;
  name?: string;
  context_tokens?: number;
  [k: string]: unknown;
}

export interface AIProvider {
  id: string;
  label: string;
  configured: boolean;
  supports_tools: boolean;
  models: AIModel[];
}

export interface ProvidersResponse {
  providers: AIProvider[];
}

export interface AIPrompts {
  rules: string;
  prompt: string;
  chat_rules: string;
}

export interface MindmapMeta {
  source_hash: string | null;
  diff_hash: string | null;
  builder_version: string | null;
  char_count: number | null;
  updated_at: string | null;
}

export interface MindmapStatus {
  model_id: number | null;
  release_id: number | null;
  has_mindmap: boolean;
  has_source?: boolean;
  meta: MindmapMeta | null;
}

export interface CompareRelease {
  previous_release_id: number | null;
  default_previous_release_id: number | null;
}

// Test Case Design (/api/testdesign/*) — mirrors backend/routers/testdesign.py.
export interface TestDesignSettings {
  project_title: string;
  design_template: string;
  operation_grouping: string; // "grouped" | "independent"
}

export interface TestDesignPreview {
  row_count: number;
  unit_label: string; // "Port" | "Row"
  index: number;
  title: string;
  body: string;
  status: string; // "ok" | "empty" | "retired" | "deleted"
  message: string;
}

export interface TestDesignSuggestions {
  completions: string[];
  prefix: string;
}

export interface TestDesignExportResult {
  output_dir: string;
  files: string[];
  file_count: number;
}

// Parsed HLT design file (POST /api/ai/parse-hlt).
export interface HltTestCase {
  index: number;
  id: string;
  title: string;
  raw: string;
  has_lowlevel: boolean;
}

export interface HltParseResult {
  model_name: string;
  title: string;
  path: string;
  test_cases: HltTestCase[];
}

// SSE event payload off /api/events
export interface BusEvent {
  event: string; // "db-changed" | "lock" | "job" | ...
  data: Record<string, unknown>;
}

// A background-job snapshot streamed over the "job" SSE event (mirrors
// backend/jobs.py Job.to_dict). `progress` is 0..100 or null (indeterminate).
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export interface JobPayload {
  job_id: string;
  kind: string;
  status: JobStatus;
  progress: number | null;
  message: string;
  error?: string;
}
