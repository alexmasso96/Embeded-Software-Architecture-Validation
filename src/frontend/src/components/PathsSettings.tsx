import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BuildSettings, ProjectMode, TerminalKind } from "../api/types";
import { FolderPicker } from "./FolderPicker";
import { TerminalIcon } from "./Icons";

// Visual terminal options for the build runner. Each carries a brand-ish tint so
// the picker reads at a glance (issue 8).
const TERMINALS: { key: TerminalKind; label: string; tint: string }[] = [
  { key: "cmd", label: "Command Prompt", tint: "#3b4252" },
  { key: "powershell", label: "PowerShell", tint: "#1f4f8b" },
  { key: "bash", label: "Bash", tint: "#43a047" },
  { key: "wsl", label: "WSL", tint: "#e95420" },
];

// Derive a sensible build command from the make-script path + chosen terminal.
function suggestBuildCommand(script: string, terminal: TerminalKind): string {
  const p = script.trim();
  if (!p) return "";
  const q = `"${p}"`;
  const lower = p.toLowerCase();
  if (lower.endsWith("makefile") || lower.endsWith(".mk")) return `make -f ${q}`;
  if (lower.endsWith(".ps1")) return `powershell -ExecutionPolicy Bypass -File ${q}`;
  if (lower.endsWith(".bat") || lower.endsWith(".cmd")) return q;
  if (lower.endsWith(".py")) return `python ${q}`;
  if (lower.endsWith(".sh")) return terminal === "cmd" ? `bash ${q}` : `sh ${q}`;
  return q;
}

type BrowseTarget = "make_script" | "source_path";

// Preferences → Paths. Build-tooling paths are project-scoped (stored in the
// open project's meta via /injection/settings), so this panel only works with a
// project open — it shows a notice otherwise.
export function PathsSettings() {
  const [settings, setSettings] = useState<BuildSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [browse, setBrowse] = useState<BrowseTarget | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setSettings(await api.get<BuildSettings>("/injection/settings"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          setUnavailable("Open a project to configure build paths.");
        } else {
          setUnavailable((e as Error).message);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function patch(p: Partial<BuildSettings>) {
    setSettings((s) => (s ? { ...s, ...p } : s));
    try {
      await api.post("/injection/settings", p);
      setNote("Saved");
      window.setTimeout(() => setNote(null), 1400);
    } catch (e) {
      setNote(
        e instanceof ApiError && e.status === 409
          ? "Open the project for editing to change paths."
          : `Save failed: ${(e as Error).message}`,
      );
    }
  }

  function onBrowsed(path: string, _mode: ProjectMode) {
    const target = browse;
    setBrowse(null);
    if (target) patch({ [target]: path } as Partial<BuildSettings>);
  }

  if (loading) {
    return (
      <div className="prefs-body">
        <div className="center-msg">
          <span className="spin" /> Loading…
        </div>
      </div>
    );
  }
  if (!settings) {
    return (
      <div className="prefs-body">
        <div className="prefs-placeholder">{unavailable}</div>
      </div>
    );
  }

  return (
    <div className="prefs-body">
      <PathField
        label="Make script"
        hint="Build / make script to run for this project."
        value={settings.make_script}
        placeholder="/path/to/build.sh or Makefile"
        onChange={(v) => patch({ make_script: v })}
        onBrowse={() => setBrowse("make_script")}
      />

      <PathField
        label="Source code (on disk)"
        hint="Folder containing the production source on disk."
        value={settings.source_path}
        placeholder="/path/to/src"
        onChange={(v) => patch({ source_path: v })}
        onBrowse={() => setBrowse("source_path")}
      />

      <div className="prefs-field">
        <div className="prefs-label">Terminal</div>
        <div className="term-grid">
          {TERMINALS.map((t) => (
            <button
              key={t.key}
              className={"term-card" + (settings.terminal === t.key ? " active" : "")}
              onClick={() => patch({ terminal: t.key })}
            >
              <TerminalIcon tint={t.tint} />
              <span>{t.label}</span>
            </button>
          ))}
        </div>
        {settings.terminal === "wsl" && (
          <input
            className="prefs-input"
            placeholder="WSL distro (optional, e.g. Ubuntu)"
            value={settings.wsl_distro}
            onChange={(e) => setSettings({ ...settings, wsl_distro: e.target.value })}
            onBlur={(e) => patch({ wsl_distro: e.target.value })}
          />
        )}
      </div>

      <div className="prefs-field">
        <div className="prefs-row">
          <div className="prefs-label">Build command</div>
          <button
            className="prefs-prefill"
            disabled={!settings.make_script.trim()}
            title="Fill from the make script above"
            onClick={() =>
              patch({
                build_command: suggestBuildCommand(settings.make_script, settings.terminal),
                build_cwd: settings.build_cwd || settings.source_path,
              })
            }
          >
            Prefill
          </button>
        </div>
        <input
          className="prefs-input"
          placeholder="e.g. make all"
          value={settings.build_command}
          onChange={(e) => setSettings({ ...settings, build_command: e.target.value })}
          onBlur={(e) => patch({ build_command: e.target.value })}
        />
        <input
          className="prefs-input"
          placeholder="Working directory (optional)"
          value={settings.build_cwd}
          onChange={(e) => setSettings({ ...settings, build_cwd: e.target.value })}
          onBlur={(e) => patch({ build_cwd: e.target.value })}
        />
      </div>

      {note && <div className="ai-prov-toast">{note}</div>}

      {browse === "source_path" && (
        <FolderPicker
          mode="folder"
          title="Choose source folder"
          onCancel={() => setBrowse(null)}
          onConfirm={onBrowsed}
        />
      )}
      {browse === "make_script" && (
        <FolderPicker
          mode="import"
          exts={[".sh", ".bat", ".cmd", ".ps1", ".mk", ".py", ".mak", ".make"]}
          title="Choose make script"
          hint="Select the build / make script for this project."
          onCancel={() => setBrowse(null)}
          onConfirm={onBrowsed}
        />
      )}
    </div>
  );
}

function PathField({
  label,
  hint,
  value,
  placeholder,
  onChange,
  onBrowse,
}: {
  label: string;
  hint: string;
  value: string;
  placeholder: string;
  onChange: (v: string) => void;
  onBrowse: () => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <div className="prefs-field">
      <div className="prefs-label">{label}</div>
      <div className="path-row">
        <input
          className="prefs-input"
          placeholder={placeholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => onChange(draft)}
        />
        <button className="path-browse" onClick={onBrowse}>
          Browse…
        </button>
      </div>
      <div className="prefs-hint">{hint}</div>
    </div>
  );
}
