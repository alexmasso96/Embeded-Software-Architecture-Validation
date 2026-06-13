export const TABS = [
  "Workspace",
  "Test Design",
  "AI Generation",
  "AI Chat",
  "Code Map",
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
}) {
  return (
    <div className="titlebar">
      <div className="doc-title">
        {projectName}
        <small>Architecture Validator Pro{release ? ` — ${release}` : ""}</small>
      </div>

      <div className="seg">
        {TABS.map((t) => (
          <button
            key={t}
            className={t === activeTab ? "active" : ""}
            disabled={t !== "Workspace"}
            title={t !== "Workspace" ? "Coming in a later Phase 2 slice" : undefined}
            onClick={() => onTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      <button className="tb-icon" title="Import" onClick={onImport}>
        ⇪
      </button>
      <button className="tb-icon" title="Columns" onClick={onColumns}>
        ▦
      </button>
      <button className="save-btn" onClick={onSave} disabled={!canSave || saving}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
