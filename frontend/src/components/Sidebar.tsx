import type { ModelInfo, ReleaseInfo } from "../api/types";

// Left source-list: models (with row-count badges), release picker, ELF/source
// indicators, and the per-project side actions.
export function Sidebar({
  models,
  activeModelId,
  onSelectModel,
  onManageModels,
  releases,
  activeReleaseId,
  onSelectRelease,
  canEdit,
  width,
}: {
  models: ModelInfo[];
  activeModelId: number | null;
  onSelectModel: (id: number) => void;
  onManageModels: () => void;
  releases: ReleaseInfo[];
  activeReleaseId: number | null;
  onSelectRelease: (id: number) => void;
  canEdit: boolean;
  width: number;
}) {
  const activeRelease = releases.find((r) => r.id === activeReleaseId);
  const hasSource = Boolean(activeRelease?.has_source);

  return (
    <div className="sidebar" style={{ width }}>
      <div className="sl-head">
        Models
        <button title="Manage models" onClick={onManageModels}>
          ＋
        </button>
      </div>

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
          title={m.status}
        >
          <span className="sl-icon">▣</span>
          {m.name}
          <span className="badge">{m.row_count}</span>
        </div>
      ))}

      <div className="sl-sep" />
      <div className="sl-head">Release</div>
      <div className="release-pick">
        <select
          value={activeReleaseId ?? ""}
          onChange={(e) => onSelectRelease(Number(e.target.value))}
          disabled={releases.length === 0}
        >
          {releases.length === 0 && <option value="">No releases</option>}
          {releases
            .filter((r) => r.selectable !== false)
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
                {r.is_active ? " (active)" : ""}
              </option>
            ))}
        </select>
      </div>

      <div className="sl-status">
        <span>Source</span>
        <b className={hasSource ? "" : "off"}>{hasSource ? "✓ linked" : "— none"}</b>
      </div>

      <div className="side-actions">
        <button className="primary" disabled={!canEdit}>
          Generate Test Cases
        </button>
        <button>Create Baseline…</button>
        <button>Load Baseline…</button>
      </div>
    </div>
  );
}
