import type { ModelInfo, ReleaseInfo } from "../api/types";

const MANAGE = "__manage__"; // sentinel <option> value → open the manager panel

// Model status → status-dot tone class (green = Released, amber = In Work,
// grey = Retired, red = Deleted). Unknown statuses fall back to grey.
const STATUS_DOT: Record<string, string> = {
  Released: "ok",
  "In Work": "warn",
  Retired: "grey",
  Deleted: "err",
};

// Left source-list: models (with row-count badges), release picker, ELF/source
// indicators, and the per-project side actions.
export function Sidebar({
  models,
  activeModelId,
  onSelectModel,
  onManageModels,
  releases,
  activeReleaseId,
  recentReleaseIds,
  onSelectRelease,
  onManageReleases,
  canEdit,
  width,
}: {
  models: ModelInfo[];
  activeModelId: number | null;
  onSelectModel: (id: number) => void;
  onManageModels: () => void;
  releases: ReleaseInfo[];
  activeReleaseId: number | null;
  recentReleaseIds: number[];
  onSelectRelease: (id: number) => void;
  onManageReleases: () => void;
  canEdit: boolean;
  width: number;
}) {
  const activeRelease = releases.find((r) => r.id === activeReleaseId);
  const hasSource = Boolean(activeRelease?.has_source);

  // Smart filter: active release + up to 5 most-recently-accessed, in that
  // order (deduped). Keeps the dropdown short even with 50+ historical versions;
  // "Manage all…" opens the full lineage manager.
  const selectable = releases.filter((r) => r.selectable !== false);
  const byId = new Map(selectable.map((r) => [r.id, r]));
  const shown: ReleaseInfo[] = [];
  const seen = new Set<number>();
  const push = (id: number | null | undefined) => {
    if (id == null || seen.has(id)) return;
    const r = byId.get(id);
    if (!r) return;
    shown.push(r);
    seen.add(id);
  };
  push(activeReleaseId);
  for (const id of recentReleaseIds) push(id);

  return (
    <div className="sidebar" style={{ width }}>
      <div className="sl-head">
        Models
        <button className="sl-manage" title="Manage models…" onClick={onManageModels}>
          Manage
        </button>
      </div>

      <div className="sl-list">
        {models.length === 0 && (
          <div className="sl-status">
            <span>No models yet</span>
          </div>
        )}
        {models.map((m) => (
          <div
            key={m.id}
            className={
              "sl-row" +
              (m.id === activeModelId ? " active" : "") +
              (m.is_deleted ? " deleted" : "")
            }
            onClick={() => onSelectModel(m.id)}
            title={`${m.name} — ${m.status} · ${m.row_count} ports`}
          >
            <span className="sl-icon">▣</span>
            <span
              className={`sl-status-dot ${STATUS_DOT[m.status] ?? "grey"}`}
              title={m.status}
            />
            <span className="sl-name">{m.name}</span>
            <span className="badge">{m.row_count}</span>
          </div>
        ))}
      </div>

      <div className="sl-foot">
        <div className="sl-head">Release</div>
        <div className="release-pick">
          <select
            value={activeReleaseId ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              if (v === MANAGE) onManageReleases();
              else onSelectRelease(Number(v));
            }}
            disabled={releases.length === 0}
          >
            {releases.length === 0 && <option value="">No releases</option>}
            {shown.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id === activeReleaseId ? "✓ " : ""}
                {r.name}
              </option>
            ))}
            {releases.length > 0 && (
              <option value={MANAGE}>Manage all…</option>
            )}
          </select>
          <button
            className="release-gear"
            title="Manage releases & baselines…"
            onClick={onManageReleases}
          >
            ⚙
          </button>
        </div>

        <div className="sl-status">
          <span>Source</span>
          <b className={hasSource ? "" : "off"}>{hasSource ? "✓ linked" : "— none"}</b>
        </div>

        <div className="side-actions">
          <button className="primary" disabled={!canEdit}>
            Generate Test Cases
          </button>
        </div>
      </div>
    </div>
  );
}
