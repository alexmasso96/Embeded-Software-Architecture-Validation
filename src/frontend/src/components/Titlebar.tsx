import { getIconLabels, useSetting } from "../settings";

export const TABS = [
  "Workspace",
  "Test Design",
  "AI Generation",
  "AI Chat",
  "Code Map",
  "Test Injection",
  "Change Log",
] as const;
export type Tab = (typeof TABS)[number];

// Unified macOS-style toolbar: document title, the six-view segmented control,
// import/columns toolbar icons, and Save.
export function Titlebar({
  projectName,
  release,
  activeTab,
  onTab,
  onSave,
  canSave,
  saving,
  onImport,
  onColumns,
  onPrefs,
}: {
  projectName: string;
  release: string | null;
  activeTab: Tab;
  onTab: (t: Tab) => void;
  onSave: () => void;
  canSave: boolean;
  saving: boolean;
  onImport: () => void;
  onColumns: () => void;
  onPrefs: () => void;
}) {
  const showLabels = useSetting(getIconLabels);
  return (
    <div className={"titlebar" + (showLabels ? " labelled" : "")}>
      <div className="doc-title">
        {projectName}
        <small>Architecture Validator Pro{release ? ` — ${release}` : ""}</small>
      </div>

      <div className="seg">
        {TABS.map((t) => {
          return (
            <button
              key={t}
              className={t === activeTab ? "active" : ""}
              onClick={() => onTab(t)}
            >
              {t}
            </button>
          );
        })}
      </div>

      {/* Right-side actions are grouped so the left title and this group can be
          given equal flex basis — that keeps the segmented control centred in
          the window regardless of how wide each side grows (e.g. when icon
          labels are shown). */}
      <div className="titlebar-actions">
        <button className="tb-icon" title="Import" onClick={onImport}>
          <span className="tb-glyph">⇪</span>
          {showLabels && <span className="tb-label">Import</span>}
        </button>
        <button className="tb-icon" title="Columns" onClick={onColumns}>
          <span className="tb-glyph">▦</span>
          {showLabels && <span className="tb-label">Columns</span>}
        </button>
        <button className="tb-icon" title="Preferences" onClick={onPrefs}>
          <span className="tb-glyph">⚙</span>
          {showLabels && <span className="tb-label">Settings</span>}
        </button>
        <button className="save-btn" onClick={onSave} disabled={!canSave || saving}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
