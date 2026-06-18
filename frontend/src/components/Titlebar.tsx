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
  return (
    <div className="titlebar">
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

      <button className="tb-icon" title="Import" onClick={onImport}>
        ⇪
      </button>
      <button className="tb-icon" title="Columns" onClick={onColumns}>
        ▦
      </button>
      <button className="tb-icon" title="Preferences" onClick={onPrefs}>
        ⚙
      </button>
      <button className="save-btn" onClick={onSave} disabled={!canSave || saving}>
        {saving ? "Saving…" : "Save"}
      </button>
    </div>
  );
}
