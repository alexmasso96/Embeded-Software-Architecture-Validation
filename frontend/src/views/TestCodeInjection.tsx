import Editor, { type OnMount } from "@monaco-editor/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, ApiError } from "../api/client";
import { useSSE } from "../api/useSSE";
import type {
  BuildSettings,
  InjectionHook,
  SourceFileInfo,
  TerminalKind,
  TestProject,
  TestProjectFile,
} from "../api/types";
import { FolderPicker } from "../components/FolderPicker";

// Monaco's editor instance type, kept loose to avoid importing monaco's full
// type surface (it ships its own .d.ts but we only touch a few members).
type MonacoEditor = Parameters<OnMount>[0];
type MonacoNs = Parameters<OnMount>[1];

// Monaco theme follows the app's resolved light/dark (mirrors CodeMap.tsx).
function useMonacoTheme(): "vs" | "vs-dark" {
  const read = (): "vs" | "vs-dark" =>
    document.documentElement.getAttribute("data-theme") === "dark"
      ? "vs-dark"
      : "vs";
  const [theme, setTheme] = useState<"vs" | "vs-dark">(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme(read()));
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);
  return theme;
}

const TERMINALS: { value: TerminalKind; label: string }[] = [
  { value: "cmd", label: "CMD" },
  { value: "powershell", label: "PowerShell" },
  { value: "bash", label: "Bash" },
  { value: "wsl", label: "WSL" },
];

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

type TabKind = "src" | "test";
interface OpenTab {
  key: string;
  kind: TabKind;
  relPath: string;
}

// A contiguous block in the *preview* document, mapped back to its hook.
interface PreviewBlock {
  hookId: number;
  start: number; // 1-based first line in the preview
  end: number; // 1-based last line in the preview
  conflict: boolean;
}

interface Preview {
  value: string;
  blocks: PreviewBlock[];
}

// Splice every resolvable hook's snippet into the source for the read-only
// inject preview; flag conflicts as a single "+line" placeholder near the target
// function. Returns the preview text plus the per-hook line ranges for
// decoration / shift overlays.
function buildPreview(content: string, hooks: InjectionHook[]): Preview {
  const lines = content.split("\n");
  const resolved = hooks
    .filter((h) => h.resolved_index != null)
    .sort((a, b) => (a.resolved_index as number) - (b.resolved_index as number));

  const byIndex = new Map<number, InjectionHook[]>();
  for (const h of resolved) {
    const i = h.resolved_index as number;
    const arr = byIndex.get(i) ?? [];
    arr.push(h);
    byIndex.set(i, arr);
  }

  const out: string[] = [];
  const blocks: PreviewBlock[] = [];
  for (let i = 0; i <= lines.length; i++) {
    for (const h of byIndex.get(i) ?? []) {
      const snip = (h.injected_code || "").split("\n");
      const start = out.length + 1;
      for (const s of snip) out.push(s);
      blocks.push({ hookId: h.id, start, end: out.length, conflict: false });
    }
    if (i < lines.length) out.push(lines[i]);
  }

  // Conflicts: drop a placeholder line just inside the named function (or at the
  // file end if we can't locate it). Shift any block recorded after it down 1.
  for (const h of hooks.filter((x) => x.resolved_index == null)) {
    let at = out.length;
    if (h.function_name) {
      const re = new RegExp("\\b" + escapeRe(h.function_name) + "\\s*\\(");
      const fi = out.findIndex((l) => re.test(l));
      if (fi >= 0) at = fi + 1;
    }
    const label = `    /* +inject (conflict): ${h.function_name || "unanchored"} — reposition this block */`;
    out.splice(at, 0, label);
    for (const b of blocks) {
      if (b.start >= at + 1) {
        b.start += 1;
        b.end += 1;
      }
    }
    blocks.push({ hookId: h.id, start: at + 1, end: at + 1, conflict: true });
  }

  return { value: out.join("\n"), blocks };
}

function confidenceBadge(c: number): { text: string; cls: string } {
  if (c >= 4) return { text: "exact", cls: "ok" };
  if (c >= 3) return { text: "fuzzy", cls: "warn" };
  return { text: "conflict", cls: "err" };
}

export function TestCodeInjection({
  toast,
  canEdit,
}: {
  toast: (m: string) => void;
  canEdit: boolean;
}) {
  const theme = useMonacoTheme();

  // -- data ----------------------------------------------------------------
  const [projects, setProjects] = useState<TestProject[]>([]);
  const [activeProject, setActiveProject] = useState<number | null>(null);
  const [sourceFiles, setSourceFiles] = useState<SourceFileInfo[]>([]);
  const [sourceErr, setSourceErr] = useState<string | null>(null);
  const [testFiles, setTestFiles] = useState<TestProjectFile[]>([]);
  const [hooks, setHooks] = useState<InjectionHook[]>([]);

  // -- editor / tabs -------------------------------------------------------
  const [tabs, setTabs] = useState<OpenTab[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [docContent, setDocContent] = useState<string>("");
  const [mode, setMode] = useState<"inject" | "edit">("inject");
  const [selectedHook, setSelectedHook] = useState<number | null>(null);
  const [snippetDraft, setSnippetDraft] = useState<string>("");
  const [placing, setPlacing] = useState<{ hookId: number; line: number } | null>(
    null,
  );
  const [editorReady, setEditorReady] = useState(0); // bumps when Editor mounts

  // -- build console -------------------------------------------------------
  const [consoleOpen, setConsoleOpen] = useState(true);
  const [buildLogs, setBuildLogs] = useState<string[]>([]);
  const [building, setBuilding] = useState(false);
  const [settings, setSettings] = useState<BuildSettings>({
    terminal: "bash",
    wsl_distro: "",
    build_command: "",
    build_cwd: "",
  });
  const [importOpen, setImportOpen] = useState(false);

  const editorRef = useRef<MonacoEditor | null>(null);
  const monacoRef = useRef<MonacoNs | null>(null);
  const decoRef = useRef<ReturnType<MonacoEditor["createDecorationsCollection"]> | null>(
    null,
  );
  const symbolsRef = useRef<Set<string>>(new Set());
  const logRef = useRef<HTMLDivElement>(null);
  const completionRegistered = useRef(false);

  const activeTabObj = tabs.find((t) => t.key === activeTab) ?? null;
  const isSrcTab = activeTabObj?.kind === "src";

  // -- loaders -------------------------------------------------------------
  const loadProjects = useCallback(async () => {
    try {
      const r = await api.get<{ projects: TestProject[] }>(
        "/injection/projects",
      );
      setProjects(r.projects);
      setActiveProject((cur) =>
        cur != null && r.projects.some((p) => p.id === cur)
          ? cur
          : (r.projects[0]?.id ?? null),
      );
    } catch (e) {
      toast(`Failed to load test projects: ${(e as Error).message}`);
    }
  }, [toast]);

  const loadSource = useCallback(async () => {
    try {
      const r = await api.get<{ files: SourceFileInfo[] }>(
        "/injection/source/files",
      );
      setSourceFiles(r.files);
      setSourceErr(null);
    } catch (e) {
      setSourceFiles([]);
      setSourceErr(
        e instanceof ApiError ? e.detail : (e as Error).message,
      );
    }
  }, []);

  const loadProjectFiles = useCallback(async (pid: number) => {
    const r = await api.get<{ files: TestProjectFile[] }>(
      `/injection/projects/${pid}/files`,
    );
    setTestFiles(r.files);
  }, []);

  const loadHooks = useCallback(async (pid: number) => {
    const r = await api.get<{ injections: InjectionHook[] }>(
      `/injection/projects/${pid}/injections`,
    );
    setHooks(r.injections);
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      setSettings(await api.get<BuildSettings>("/injection/settings"));
    } catch {
      /* keep defaults */
    }
  }, []);

  useEffect(() => {
    loadProjects();
    loadSource();
    loadSettings();
  }, [loadProjects, loadSource, loadSettings]);

  useEffect(() => {
    if (activeProject == null) {
      setTestFiles([]);
      setHooks([]);
      return;
    }
    loadProjectFiles(activeProject);
    loadHooks(activeProject);
  }, [activeProject, loadProjectFiles, loadHooks]);

  // Hooks for the file currently open in the editor.
  const fileHooks = useMemo(
    () =>
      activeTabObj && isSrcTab
        ? hooks.filter((h) => h.src_file_path === activeTabObj.relPath)
        : [],
    [hooks, activeTabObj, isSrcTab],
  );

  // -- document loading ----------------------------------------------------
  const openFile = useCallback(
    async (kind: TabKind, relPath: string) => {
      const key = `${kind}:${relPath}`;
      setTabs((prev) =>
        prev.some((t) => t.key === key) ? prev : [...prev, { key, kind, relPath }],
      );
      setActiveTab(key);
    },
    [],
  );

  useEffect(() => {
    if (!activeTabObj) {
      setDocContent("");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const url =
          activeTabObj.kind === "src"
            ? `/injection/source/content?rel_path=${encodeURIComponent(activeTabObj.relPath)}`
            : `/injection/projects/${activeProject}/files/content?rel_path=${encodeURIComponent(activeTabObj.relPath)}`;
        const r = await api.get<{ content: string }>(url);
        if (!cancelled) {
          setDocContent(r.content);
          // Feed the autocomplete provider with identifiers from this file.
          harvestSymbols(r.content);
        }
      } catch (e) {
        if (!cancelled) {
          setDocContent(`/* Failed to load: ${(e as Error).message} */`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, activeProject]);

  function harvestSymbols(text: string) {
    const set = symbolsRef.current;
    const re = /[A-Za-z_]\w{2,}/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) set.add(m[0]);
    for (const f of testFiles) set.add(f.rel_path.split("/").pop() ?? "");
  }

  // -- preview + decorations ----------------------------------------------
  const preview = useMemo<Preview>(() => {
    if (!isSrcTab) return { value: docContent, blocks: [] };
    return buildPreview(docContent, fileHooks);
  }, [docContent, fileHooks, isSrcTab]);

  const editorValue = mode === "inject" && isSrcTab ? preview.value : docContent;

  // Apply inject-preview decorations directly in an effect. Parent effects run
  // after the child Editor has committed its controlled value, so the model line
  // count already matches `preview` here — no rAF/stale-closure dance needed.
  useEffect(() => {
    const ed = editorRef.current;
    const monaco = monacoRef.current;
    if (!ed || !monaco || !ed.getModel()) return;
    if (!decoRef.current) decoRef.current = ed.createDecorationsCollection();
    if (mode !== "inject" || !isSrcTab) {
      decoRef.current.set([]);
      return;
    }
    const decos = preview.blocks.map((b) => ({
      range: new monaco.Range(b.start, 1, b.end, 1),
      options: {
        isWholeLine: true,
        className: b.conflict ? "tci-line-conflict" : "tci-line-inject",
        linesDecorationsClassName: b.conflict
          ? "tci-glyph-conflict"
          : "tci-glyph-inject",
        hoverMessage: {
          value: b.conflict
            ? "Conflict — anchors no longer match. Reposition this block."
            : "Injected test code (preview).",
        },
      },
    }));
    if (placing) {
      decos.push({
        range: new monaco.Range(placing.line, 1, placing.line, 1),
        options: {
          isWholeLine: true,
          className: "tci-line-placing",
          linesDecorationsClassName: "tci-glyph-placing",
          hoverMessage: { value: "Click ↑/↓ then Place to anchor here." },
        },
      });
    }
    decoRef.current.set(decos);
  }, [preview, mode, isSrcTab, placing, editorValue, editorReady]);

  // -- SSE: build logs -----------------------------------------------------
  useSSE(
    useCallback((e) => {
      if (e.event !== "build") return;
      const d = e.data as Record<string, unknown>;
      const kind = d.event as string;
      if (kind === "start") {
        setBuilding(true);
        setConsoleOpen(true);
        setBuildLogs((p) => [...p, `$ ${(d.argv as string[])?.join(" ") ?? ""}`]);
      } else if (kind === "log" || kind === "error") {
        setBuildLogs((p) => [...p, String(d.line ?? "")]);
      } else if (kind === "done") {
        setBuilding(false);
        setBuildLogs((p) => [...p, `— build exited (code ${d.returncode}) —`]);
      }
    }, []),
    true,
  );

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [buildLogs]);

  // -- editor mount --------------------------------------------------------
  const onEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    // Bind a fresh decorations collection to THIS editor instance (a stale one
    // from a previous mount would silently apply to a disposed editor).
    decoRef.current = editor.createDecorationsCollection();
    requestAnimationFrame(() => editor.layout());
    setTimeout(() => editor.layout(), 100);

    // Repositioning a conflicted hook: clicking a line sets the candidate anchor.
    editor.onMouseDown((e) => {
      const pos = e.target.position;
      if (!pos) return;
      setPlacing((cur) => (cur ? { ...cur, line: pos.lineNumber } : cur));
    });

    if (!completionRegistered.current) {
      completionRegistered.current = true;
      const provider: import("monaco-editor").languages.CompletionItemProvider = {
        provideCompletionItems(model, position) {
          const word = model.getWordUntilPosition(position);
          const range = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn,
          };
          const suggestions = Array.from(symbolsRef.current)
            .filter(Boolean)
            .slice(0, 2000)
            .map((label) => ({
              label,
              kind: monaco.languages.CompletionItemKind.Function,
              insertText: label,
              range,
              detail: "CodeIndex symbol",
            }));
          return { suggestions };
        },
      };
      monaco.languages.registerCompletionItemProvider("c", provider);
    }
    // Decorations are applied by the effect below once preview/model are ready.
    setEditorReady((n) => n + 1);
  };

  // -- mutations -----------------------------------------------------------
  async function createProject() {
    const name = window.prompt("New test project name:")?.trim();
    if (!name) return;
    try {
      await api.post("/injection/projects", { name });
      toast(`Created “${name}”`);
      await loadProjects();
    } catch (e) {
      toast(`Create failed: ${(e as Error).message}`);
    }
  }

  async function deleteProject(pid: number) {
    if (!window.confirm("Delete this test project and all its hooks?")) return;
    try {
      await api.del(`/injection/projects/${pid}`);
      await loadProjects();
    } catch (e) {
      toast(`Delete failed: ${(e as Error).message}`);
    }
  }

  async function importHelpers(folder: string) {
    if (activeProject == null) return;
    setImportOpen(false);
    try {
      const r = await api.post<{ imported: number }>(
        `/injection/projects/${activeProject}/import`,
        { folder },
      );
      toast(`Imported ${r.imported} helper file(s)`);
      await loadProjectFiles(activeProject);
      await loadProjects();
    } catch (e) {
      toast(`Import failed: ${(e as Error).message}`);
    }
  }

  // Create a hook at the editor cursor (Edit Mode): anchor to the surrounding
  // source lines so the fuzzy resolver can re-find the splice point.
  async function addHookAtCursor() {
    if (activeProject == null || !activeTabObj || !isSrcTab) return;
    const ed = editorRef.current;
    const pos = ed?.getPosition();
    if (!pos) return;
    const lines = docContent.split("\n");
    const idx = pos.lineNumber - 1; // splice before this line
    const above = lines[idx - 1] ?? "";
    const below = lines[idx] ?? "";
    try {
      const r = await api.post<{ injection_id: number }>(
        `/injection/projects/${activeProject}/injections`,
        {
          src_file_path: activeTabObj.relPath,
          function_name: "",
          line_above_code: above,
          line_below_code: below,
          injected_code: "/* test code */",
        },
      );
      await loadHooks(activeProject);
      setSelectedHook(r.injection_id);
      setSnippetDraft("/* test code */");
      setMode("inject");
      toast("Hook added — edit the snippet on the right");
    } catch (e) {
      toast(`Add hook failed: ${(e as Error).message}`);
    }
  }

  async function saveSnippet() {
    if (activeProject == null || selectedHook == null) return;
    const h = hooks.find((x) => x.id === selectedHook);
    if (!h) return;
    try {
      await api.post(`/injection/projects/${activeProject}/injections`, {
        injection_id: selectedHook,
        src_file_path: h.src_file_path,
        function_name: h.function_name,
        line_above_code: h.line_above_code,
        line_below_code: h.line_below_code,
        injected_code: snippetDraft,
        offset_lines: h.offset_lines,
      });
      await loadHooks(activeProject);
      toast("Snippet saved");
    } catch (e) {
      toast(`Save failed: ${(e as Error).message}`);
    }
  }

  async function shiftHook(id: number, direction: "up" | "down") {
    try {
      await api.post(`/injection/injections/${id}/shift`, { direction });
      if (activeProject != null) await loadHooks(activeProject);
    } catch (e) {
      toast(
        e instanceof ApiError ? e.detail : `Shift failed: ${(e as Error).message}`,
      );
    }
  }

  async function deleteHook(id: number) {
    try {
      await api.del(`/injection/injections/${id}`);
      if (activeProject != null) await loadHooks(activeProject);
      if (selectedHook === id) setSelectedHook(null);
    } catch (e) {
      toast(`Delete failed: ${(e as Error).message}`);
    }
  }

  // Re-anchor a conflicted hook to the currently-highlighted line.
  async function placeHere() {
    if (!placing || activeProject == null) return;
    const h = hooks.find((x) => x.id === placing.hookId);
    if (!h) return;
    const lines = preview.value.split("\n");
    const above = lines[placing.line - 2] ?? "";
    const below = lines[placing.line - 1] ?? "";
    try {
      await api.post(`/injection/projects/${activeProject}/injections`, {
        injection_id: h.id,
        src_file_path: h.src_file_path,
        function_name: h.function_name,
        line_above_code: above,
        line_below_code: below,
        injected_code: h.injected_code,
        offset_lines: h.offset_lines,
      });
      setPlacing(null);
      await loadHooks(activeProject);
      toast("Hook re-anchored");
    } catch (e) {
      toast(`Reposition failed: ${(e as Error).message}`);
    }
  }

  async function saveSettings(patch: Partial<BuildSettings>) {
    const next = { ...settings, ...patch };
    setSettings(next);
    try {
      await api.post("/injection/settings", patch);
    } catch (e) {
      toast(`Settings save failed: ${(e as Error).message}`);
    }
  }

  async function runBuild() {
    if (activeProject == null) return;
    try {
      await api.post(`/injection/projects/${activeProject}/build`, {});
    } catch (e) {
      toast(
        e instanceof ApiError ? e.detail : `Build failed: ${(e as Error).message}`,
      );
    }
  }

  async function runExport(modeSel: "modified" | "reconstruct", outDir: string) {
    if (activeProject == null) return;
    try {
      const r = await api.post<{ count: number; conflicts: unknown[] }>(
        `/injection/projects/${activeProject}/export`,
        { mode: modeSel, out_dir: outDir, overwrite: true },
      );
      toast(
        `Exported ${r.count} file(s)` +
          (r.conflicts.length ? ` (${r.conflicts.length} conflict(s) skipped)` : ""),
      );
    } catch (e) {
      toast(`Export failed: ${(e as Error).message}`);
    }
  }

  const selected = hooks.find((h) => h.id === selectedHook) ?? null;
  useEffect(() => {
    setSnippetDraft(selected?.injected_code ?? "");
  }, [selectedHook]); // eslint-disable-line react-hooks/exhaustive-deps

  // -- render --------------------------------------------------------------
  return (
    <div className="tci-root">
      {/* Sidebar: test projects + file tree */}
      <aside className="tci-sidebar">
        <div className="tci-sect-head">
          <span>Test Projects</span>
          <button
            className="tci-icon-btn"
            title="New test project"
            disabled={!canEdit}
            onClick={createProject}
          >
            ＋
          </button>
        </div>
        <div className="tci-projlist">
          {projects.length === 0 && (
            <div className="tci-empty">No test projects yet.</div>
          )}
          {projects.map((p) => (
            <div
              key={p.id}
              className={"tci-proj" + (p.id === activeProject ? " sel" : "")}
              onClick={() => setActiveProject(p.id)}
            >
              <span className="tci-proj-name">{p.name}</span>
              <span className="tci-proj-meta">
                {p.file_count}f · {p.injection_count}h
              </span>
              <button
                className="tci-icon-btn danger"
                title="Delete"
                disabled={!canEdit}
                onClick={(ev) => {
                  ev.stopPropagation();
                  deleteProject(p.id);
                }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <div className="tci-sect-head">
          <span>Production Source</span>
        </div>
        <div className="tci-filetree">
          {sourceErr && <div className="tci-empty err">{sourceErr}</div>}
          {sourceFiles.map((f) => (
            <button
              key={f.rel_path}
              className={
                "tci-file" +
                (activeTab === `src:${f.rel_path}` ? " sel" : "")
              }
              title={f.rel_path}
              onClick={() => openFile("src", f.rel_path)}
            >
              <span className="tci-file-name">{f.rel_path}</span>
            </button>
          ))}
        </div>

        <div className="tci-sect-head">
          <span>Test Files</span>
          <button
            className="tci-icon-btn"
            title="Import .c/.h helpers"
            disabled={!canEdit || activeProject == null}
            onClick={() => setImportOpen(true)}
          >
            ⤓
          </button>
        </div>
        <div className="tci-filetree">
          {testFiles.length === 0 && (
            <div className="tci-empty">No helper files imported.</div>
          )}
          {testFiles.map((f) => (
            <button
              key={f.rel_path}
              className={
                "tci-file" +
                (activeTab === `test:${f.rel_path}` ? " sel" : "")
              }
              title={f.rel_path}
              onClick={() => openFile("test", f.rel_path)}
            >
              <span className="tci-file-name">{f.rel_path}</span>
            </button>
          ))}
        </div>
      </aside>

      {/* Center: tabs + editor + build console */}
      <div className="tci-center">
        <div className="tci-tabbar">
          {tabs.map((t) => (
            <div
              key={t.key}
              className={"tci-tab" + (t.key === activeTab ? " active" : "")}
              onClick={() => setActiveTab(t.key)}
            >
              <span className={"tci-tab-dot " + t.kind} />
              <span className="tci-tab-label">{t.relPath.split("/").pop()}</span>
              <button
                className="tci-tab-x"
                onClick={(e) => {
                  e.stopPropagation();
                  setTabs((prev) => prev.filter((x) => x.key !== t.key));
                  if (activeTab === t.key) setActiveTab(null);
                }}
              >
                ✕
              </button>
            </div>
          ))}
          <div className="tci-tab-spacer" />
          {isSrcTab && (
            <div className="tci-modeswitch">
              <button
                className={mode === "inject" ? "active" : ""}
                onClick={() => setMode("inject")}
              >
                Inject
              </button>
              <button
                className={mode === "edit" ? "active" : ""}
                disabled={!canEdit}
                onClick={() => setMode("edit")}
              >
                Edit
              </button>
            </div>
          )}
          {isSrcTab && mode === "edit" && (
            <button className="tci-mini-btn" onClick={addHookAtCursor}>
              ＋ Hook at cursor
            </button>
          )}
        </div>

        <div className="tci-editor-wrap">
          <div className="tci-editor">
            {activeTabObj ? (
              <Editor
                language="c"
                theme={theme}
                value={editorValue}
                onMount={onEditorMount}
                options={{
                  readOnly: !(mode === "edit" && canEdit),
                  domReadOnly: !(mode === "edit" && canEdit),
                  minimap: { enabled: false },
                  fontSize: 12,
                  lineNumbers: "on",
                  glyphMargin: true,
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
              />
            ) : (
              <div className="center-msg">
                Select a source or test file to begin.
              </div>
            )}
          </div>

          {/* Hook inspector */}
          {isSrcTab && (
            <div className="tci-hooks">
              <div className="tci-panel-head">
                Injection Hooks ({fileHooks.length})
              </div>
              <div className="tci-hooklist">
                {fileHooks.length === 0 && (
                  <div className="tci-empty">
                    {mode === "edit"
                      ? "Place the cursor and click “Hook at cursor”."
                      : "Switch to Edit mode to add a hook."}
                  </div>
                )}
                {fileHooks.map((h) => {
                  const badge = confidenceBadge(h.confidence);
                  const conflict = h.confidence < 3;
                  return (
                    <div
                      key={h.id}
                      className={
                        "tci-hook" + (h.id === selectedHook ? " sel" : "")
                      }
                      onClick={() => setSelectedHook(h.id)}
                    >
                      <div className="tci-hook-top">
                        <span className={"tci-badge " + badge.cls}>
                          {badge.text}
                        </span>
                        <code className="tci-hook-snip">
                          {(h.injected_code || "").split("\n")[0] || "—"}
                        </code>
                      </div>
                      <div className="tci-hook-ctl">
                        {conflict ? (
                          <button
                            className="tci-mini-btn"
                            disabled={!canEdit}
                            onClick={(e) => {
                              e.stopPropagation();
                              setPlacing({ hookId: h.id, line: 1 });
                              setSelectedHook(h.id);
                            }}
                          >
                            Reposition
                          </button>
                        ) : (
                          <>
                            <button
                              className="tci-mini-btn"
                              title="Shift up"
                              disabled={!canEdit}
                              onClick={(e) => {
                                e.stopPropagation();
                                shiftHook(h.id, "up");
                              }}
                            >
                              ↑
                            </button>
                            <button
                              className="tci-mini-btn"
                              title="Shift down"
                              disabled={!canEdit}
                              onClick={(e) => {
                                e.stopPropagation();
                                shiftHook(h.id, "down");
                              }}
                            >
                              ↓
                            </button>
                          </>
                        )}
                        <button
                          className="tci-mini-btn danger"
                          disabled={!canEdit}
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteHook(h.id);
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {placing && (
                <div className="tci-placing-bar">
                  <span>Repositioning to line {placing.line}</span>
                  <button
                    className="tci-mini-btn"
                    onClick={() =>
                      setPlacing((p) =>
                        p ? { ...p, line: Math.max(1, p.line - 1) } : p,
                      )
                    }
                  >
                    ↑
                  </button>
                  <button
                    className="tci-mini-btn"
                    onClick={() =>
                      setPlacing((p) => (p ? { ...p, line: p.line + 1 } : p))
                    }
                  >
                    ↓
                  </button>
                  <button className="save-btn" onClick={placeHere}>
                    Place
                  </button>
                  <button className="tci-mini-btn" onClick={() => setPlacing(null)}>
                    Cancel
                  </button>
                </div>
              )}

              {selected && (
                <div className="tci-snippet">
                  <div className="tci-panel-head">Snippet</div>
                  <textarea
                    className="tci-snippet-area"
                    spellCheck={false}
                    value={snippetDraft}
                    disabled={!canEdit}
                    onChange={(e) => setSnippetDraft(e.target.value)}
                  />
                  <button
                    className="save-btn"
                    disabled={!canEdit}
                    onClick={saveSnippet}
                  >
                    Save snippet
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Build console */}
        <div className={"tci-console" + (consoleOpen ? " open" : "")}>
          <div className="tci-console-bar">
            <button
              className="tci-mini-btn"
              onClick={() => setConsoleOpen((o) => !o)}
            >
              {consoleOpen ? "▾" : "▸"} Build Console
            </button>
            <select
              className="tci-select"
              value={settings.terminal}
              disabled={!canEdit}
              onChange={(e) =>
                saveSettings({ terminal: e.target.value as TerminalKind })
              }
            >
              {TERMINALS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            {settings.terminal === "wsl" && (
              <input
                className="tci-input"
                placeholder="distro"
                value={settings.wsl_distro}
                disabled={!canEdit}
                onChange={(e) => saveSettings({ wsl_distro: e.target.value })}
              />
            )}
            <input
              className="tci-input grow"
              placeholder="build command (e.g. make all)"
              value={settings.build_command}
              disabled={!canEdit}
              onChange={(e) => saveSettings({ build_command: e.target.value })}
            />
            <input
              className="tci-input"
              placeholder="working dir"
              value={settings.build_cwd}
              disabled={!canEdit}
              onChange={(e) => saveSettings({ build_cwd: e.target.value })}
            />
            <button
              className="save-btn"
              disabled={building || activeProject == null}
              onClick={runBuild}
            >
              {building ? "Building…" : "Build"}
            </button>
            <button
              className="tci-mini-btn"
              disabled={activeProject == null}
              title="Export injected source"
              onClick={() => {
                const out = window.prompt("Export to directory:");
                if (out) runExport("modified", out);
              }}
            >
              Export
            </button>
            <button
              className="tci-mini-btn"
              onClick={() => setBuildLogs([])}
              title="Clear"
            >
              Clear
            </button>
          </div>
          {consoleOpen && (
            <div className="tci-console-log" ref={logRef}>
              {buildLogs.length === 0 ? (
                <div className="tci-empty">No build output yet.</div>
              ) : (
                buildLogs.map((line, i) => (
                  <div key={i} className="tci-log-line">
                    {line}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {importOpen && (
        <FolderPicker
          mode="folder"
          title="Import test helpers — choose a folder of .c/.h files"
          hint="Navigate to the folder containing the test helper sources"
          onCancel={() => setImportOpen(false)}
          onConfirm={(path) => importHelpers(path)}
        />
      )}
    </div>
  );
}
