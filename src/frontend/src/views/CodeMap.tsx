import Editor, { type OnMount } from "@monaco-editor/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ApiError, api } from "../api/client";
import { useSSE } from "../api/useSSE";
import type {
  CodeMapGraph,
  CodeMapResponse,
  FunctionDetail,
  GraphNode,
  MindmapStatus,
  ModelsResponse,
  ReleasesResponse,
  SourceResponse,
} from "../api/types";
import { FolderPicker } from "../components/FolderPicker";

type ListState = "loading" | "ready" | "needs-build" | "error";

// Monaco theme follows the app's resolved light/dark (<html data-theme>).
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

// ---------------------------------------------------------------------------
// Call-graph SVG — manual column layout: callers on the left, focus in the
// centre, callees on the right (one column per graph level). Double-clicking a
// caller/callee node re-focuses on it.
// ---------------------------------------------------------------------------
const NODE_W = 150;
const NODE_H = 34;
const COL_GAP = 56;
const ROW_GAP = 16;
const PAD = 20;

function CallGraph({
  graph,
  focus,
  onFocus,
}: {
  graph: CodeMapGraph | null;
  focus: string | null;
  onFocus: (name: string) => void;
}) {
  const layout = useMemo(() => {
    if (!graph || graph.nodes.length === 0) return null;
    // Group nodes by level, columns ordered left→right by ascending level.
    const byLevel = new Map<number, GraphNode[]>();
    for (const n of graph.nodes) {
      const arr = byLevel.get(n.level) ?? [];
      arr.push(n);
      byLevel.set(n.level, arr);
    }
    const levels = [...byLevel.keys()].sort((a, b) => a - b);
    for (const lvl of levels) {
      byLevel.get(lvl)!.sort((a, b) => a.name.localeCompare(b.name));
    }
    const maxRows = Math.max(...levels.map((l) => byLevel.get(l)!.length));
    const width = PAD * 2 + levels.length * NODE_W + (levels.length - 1) * COL_GAP;
    const height = PAD * 2 + maxRows * NODE_H + (maxRows - 1) * ROW_GAP;

    const pos = new Map<string, { x: number; y: number; node: GraphNode }>();
    levels.forEach((lvl, ci) => {
      const col = byLevel.get(lvl)!;
      const x = PAD + ci * (NODE_W + COL_GAP);
      const colHeight = col.length * NODE_H + (col.length - 1) * ROW_GAP;
      const y0 = (height - colHeight) / 2;
      col.forEach((node, ri) => {
        pos.set(node.name, { x, y: y0 + ri * (NODE_H + ROW_GAP), node });
      });
    });

    const edges = graph.edges
      .map((e) => ({ a: pos.get(e.source), b: pos.get(e.target) }))
      .filter((e) => e.a && e.b) as {
      a: { x: number; y: number };
      b: { x: number; y: number };
    }[];

    return { pos, edges, width, height };
  }, [graph]);

  if (!layout) {
    return <div className="cm-graph-empty">No call graph for this function.</div>;
  }

  const { pos, edges, width, height } = layout;

  return (
    <svg
      className="cm-graph-svg"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      width="100%"
      height="100%"
    >
      <g className="cm-edges">
        {edges.map((e, i) => (
          <line
            key={i}
            x1={e.a.x + NODE_W}
            y1={e.a.y + NODE_H / 2}
            x2={e.b.x}
            y2={e.b.y + NODE_H / 2}
          />
        ))}
      </g>
      <g className="cm-nodes">
        {[...pos.values()].map(({ x, y, node }) => {
          const isFocus = node.type === "center" || node.name === focus;
          return (
            <g
              key={node.name}
              className={"cm-node " + node.type + (isFocus ? " focus" : "")}
              transform={`translate(${x},${y})`}
              onDoubleClick={() => !isFocus && onFocus(node.name)}
            >
              <title>
                {node.name}
                {isFocus ? "" : " — double-click to focus"}
              </title>
              <rect rx={7} width={NODE_W} height={NODE_H} />
              <text x={NODE_W / 2} y={NODE_H / 2}>
                {node.name.length > 20 ? node.name.slice(0, 19) + "…" : node.name}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Details inspector card — metadata + clickable callers/callees + globals.
// ---------------------------------------------------------------------------
function DetailsCard({
  detail,
  source,
  onFocus,
}: {
  detail: FunctionDetail | null;
  source: SourceResponse | null;
  onFocus: (name: string) => void;
}) {
  if (!detail) return null;
  const hexAddr =
    detail.address && detail.address > 0
      ? "0x" + detail.address.toString(16)
      : "—";
  return (
    <div className="cm-details">
      <div className="cm-det-title">{detail.name}</div>
      {detail.signature && <code className="cm-det-sig">{detail.signature}</code>}

      <div className="cm-det-meta">
        <span title="Address">addr {hexAddr}</span>
        <span title="Size">size {detail.size || 0} B</span>
        {detail.return_type && <span>returns {detail.return_type}</span>}
        {detail.file && (
          <span title={detail.file}>
            {detail.file.split(/[\\/]/).pop()}
            {detail.line_start ? `:${detail.line_start}` : ""}
          </span>
        )}
      </div>

      {source && !source.found && source.reason && (
        <div className="cm-det-note">Source: {source.reason}</div>
      )}

      <div className="cm-det-cols">
        <div>
          <div className="cm-det-h">Callers ({detail.callers.length})</div>
          {detail.callers.length === 0 ? (
            <div className="cm-det-empty">none</div>
          ) : (
            detail.callers.map((c) => (
              <button key={c} className="cm-chip" onClick={() => onFocus(c)}>
                {c}
              </button>
            ))
          )}
        </div>
        <div>
          <div className="cm-det-h">Callees ({detail.callees.length})</div>
          {detail.callees.length === 0 ? (
            <div className="cm-det-empty">none</div>
          ) : (
            detail.callees.map((c) => (
              <button key={c} className="cm-chip" onClick={() => onFocus(c)}>
                {c}
              </button>
            ))
          )}
        </div>
        <div>
          <div className="cm-det-h">Globals ({detail.globals.length})</div>
          {detail.globals.length === 0 ? (
            <div className="cm-det-empty">none</div>
          ) : (
            detail.globals.map((g) => (
              <div key={g.name} className="cm-global" title={g.type}>
                <span className="cm-global-name">{g.name}</span>
                <span className="cm-global-type">{g.type}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Code Map view.
// ---------------------------------------------------------------------------
export function CodeMap({
  toast,
  focusTarget = null,
  onFocusConsumed,
}: {
  toast: (msg: string) => void;
  // A function name to jump to, set when the user picks "Show in Code Map" in
  // the Workspace. Consumed once (cleared via onFocusConsumed) so it doesn't
  // re-fire on later re-renders.
  focusTarget?: string | null;
  onFocusConsumed?: () => void;
}) {
  const [listState, setListState] = useState<ListState>("loading");
  const [listError, setListError] = useState<string | null>(null);
  const [functions, setFunctions] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [focused, setFocused] = useState<string | null>(null);

  const [graph, setGraph] = useState<CodeMapGraph | null>(null);
  const [detail, setDetail] = useState<FunctionDetail | null>(null);
  const [source, setSource] = useState<SourceResponse | null>(null);

  const [buildOpen, setBuildOpen] = useState(false);
  const [building, setBuilding] = useState(false);
  // Whether the active release already has source stored in the DB — when true
  // the build uses it directly instead of prompting for a folder.
  const [relHasSource, setRelHasSource] = useState(false);
  // Whether a code mind map exists for the active model/release (drives the
  // availability badge so the user can see what AI grounding is ready).
  const [mindmapOn, setMindmapOn] = useState(false);

  const theme = useMonacoTheme();

  // Function-name set, read by the Monaco link provider / navigation (kept in a
  // ref so the editor providers — registered once — always see the latest list).
  const functionSetRef = useRef<Set<string>>(new Set());
  const navigateRef = useRef<(name: string) => void>(() => {});
  // Monaco disposables (link provider, opener, listeners) torn down on unmount,
  // and a recompute hook so the highlight decorations refresh when the source or
  // function set changes (the model content may be identical across switches).
  const disposablesRef = useRef<{ dispose(): void }[]>([]);
  const recomputeHighlightsRef = useRef<() => void>(() => {});

  const loadList = useCallback(async () => {
    setListState("loading");
    try {
      const cm = await api.get<CodeMapResponse>("/codemap");
      functionSetRef.current = new Set(cm.functions);
      setFunctions(cm.functions);
      setFocused((prev) =>
        prev && cm.functions.includes(prev)
          ? prev
          : cm.functions.includes("main")
            ? "main"
            : (cm.functions[0] ?? null),
      );
      setListState("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setListState("needs-build");
      } else {
        setListError((e as Error).message);
        setListState("error");
      }
    }
  }, []);

  // Track whether the active release already has source stored in the DB so the
  // build flow can index it directly (no folder prompt). Stays in sync with the
  // Release Manager's Import/Drop Source actions via the db-changed SSE below.
  const refreshSourceStatus = useCallback(async () => {
    try {
      const [releases, mm] = await Promise.all([
        api.get<ReleasesResponse>("/releases"),
        api.get<MindmapStatus>("/ai/mindmap").catch(() => null),
      ]);
      const rel = releases.releases.find(
        (r) => r.id === releases.active_release_id,
      );
      setRelHasSource(Boolean(rel?.has_source));
      setMindmapOn(Boolean(mm?.has_mindmap));
    } catch {
      /* leave previous value on a transient failure */
    }
  }, []);

  useEffect(() => {
    loadList();
    refreshSourceStatus();
  }, [loadList, refreshSourceStatus]);

  // Honor a "Show in Code Map" jump from the Workspace: focus the requested
  // function and clear the search box, then tell the parent it's consumed.
  useEffect(() => {
    if (!focusTarget) return;
    setSearch("");
    setFocused(focusTarget);
    onFocusConsumed?.();
  }, [focusTarget, onFocusConsumed]);

  // Fetch graph + details + source whenever the focused function changes.
  useEffect(() => {
    if (listState !== "ready" || !focused) return;
    let alive = true;
    const fn = encodeURIComponent(focused);
    (async () => {
      try {
        const [g, d, s] = await Promise.all([
          api.get<CodeMapGraph>(`/codemap/graph?fn=${fn}&back=1&fwd=1`),
          api.get<FunctionDetail>(`/codemap/function/${fn}`),
          api.get<SourceResponse>(`/source/function/${fn}`),
        ]);
        if (!alive) return;
        setGraph(g);
        setDetail(d);
        setSource(s);
      } catch (e) {
        if (alive) toast(`Code Map: ${(e as Error).message}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [focused, listState, toast]);

  const navigate = useCallback(
    (name: string) => {
      if (functionSetRef.current.has(name)) setFocused(name);
    },
    [],
  );
  navigateRef.current = navigate;

  // Refresh the navigable-function highlight decorations when the loaded source
  // or the known-function set changes (content can be identical across switches,
  // so an onDidChangeModelContent listener alone would miss some updates).
  useEffect(() => {
    recomputeHighlightsRef.current();
  }, [source, functions]);

  // Tear down all Monaco registrations when the view unmounts (e.g. tab switch),
  // so we don't leak duplicate "c" link providers across remounts.
  useEffect(() => {
    const bag = disposablesRef.current;
    return () => {
      bag.forEach((d) => d.dispose());
      bag.length = 0;
    };
  }, []);

  // Reload the map when a build_code_map job finishes, and keep the release's
  // source status fresh when source is imported/dropped (Release Manager) or a
  // build auto-imports it.
  useSSE(
    useCallback(
      (e) => {
        if (e.event === "db-changed") {
          refreshSourceStatus();
          return;
        }
        if (e.event !== "job" || e.data?.kind !== "build_code_map") return;
        const st = e.data.status;
        if (st === "done") {
          setBuilding(false);
          refreshSourceStatus();
          loadList();
        } else if (st === "failed" || st === "cancelled") {
          setBuilding(false);
        }
      },
      [loadList, refreshSourceStatus],
    ),
  );

  async function startBuild(sourceDir: string) {
    setBuildOpen(false);
    try {
      const [models, releases] = await Promise.all([
        api.get<ModelsResponse>("/models"),
        api.get<ReleasesResponse>("/releases"),
      ]);
      if (models.active_model_id == null) {
        toast("No active model to build a Code Map for.");
        return;
      }
      const relId = releases.active_release_id;
      const rel = releases.releases.find((r) => r.id === relId);
      await api.post("/jobs/build_code_map", {
        model_id: models.active_model_id,
        release_id: relId,
        elf_hash: rel?.elf_hash ?? null,
        elf_path: rel?.elf_path ?? null,
        source_dir: sourceDir,
      });
      setBuilding(true);
      toast("Building Code Map…");
    } catch (e) {
      toast(`Build failed to start: ${(e as Error).message}`);
    }
  }

  const onEditorMount: OnMount = (editor, monaco) => {
    editor.updateOptions({ readOnly: true });
    // Guard against mounting inside a still-collapsing flex container: Monaco
    // caches the container size at mount and `automaticLayout` can miss a late
    // first sizing, leaving the editor stuck at its 5×5 minimum. Re-measure on
    // the next frames so it fills the pane once layout settles.
    requestAnimationFrame(() => editor.layout());
    setTimeout(() => editor.layout(), 100);

    // Single pass over the file's identifiers, keeping only those that name a
    // known function. Shared by the link provider (native Ctrl/Cmd-hover
    // underline + click) and the always-on highlight decorations — O(file)
    // instead of O(functions × file) re-scans.
    const collect = (model: ReturnType<typeof editor.getModel>) => {
      const out: { fn: string; range: InstanceType<typeof monaco.Range> }[] = [];
      if (!model) return out;
      const fns = functionSetRef.current;
      if (fns.size === 0) return out;
      const text = model.getValue();
      const re = /[A-Za-z_]\w*/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(text)) !== null) {
        if (!fns.has(m[0])) continue;
        const s = model.getPositionAt(m.index);
        const e = model.getPositionAt(m.index + m[0].length);
        out.push({
          fn: m[0],
          range: new monaco.Range(s.lineNumber, s.column, e.lineNumber, e.column),
        });
      }
      return out;
    };

    // Native links: Monaco underlines these and shows a pointer when Ctrl/Cmd is
    // held, and opens them on Ctrl/Cmd+click — exactly the navigation gesture.
    const NAV_SCHEME = "codemap";
    const linkProvider = monaco.languages.registerLinkProvider("c", {
      provideLinks(model: import("monaco-editor").editor.ITextModel) {
        return {
          links: collect(model).map(({ fn, range }) => ({
            range,
            url: monaco.Uri.from({ scheme: NAV_SCHEME, path: "/" + encodeURIComponent(fn) }),
            tooltip: `Ctrl/Cmd + Click to navigate to ${fn}`,
          })),
        };
      },
    });

    // Route our codemap: links back into the React focus state.
    const linkOpener = monaco.editor.registerLinkOpener({
      open(resource: import("monaco-editor").Uri) {
        if (resource.scheme !== NAV_SCHEME) return false;
        navigateRef.current(decodeURIComponent(resource.path.replace(/^\//, "")));
        return true;
      },
    });

    // Always-on rich highlight + discoverability hover for navigable calls.
    const decorations = editor.createDecorationsCollection();
    const recompute = () => {
      const model = editor.getModel();
      decorations.set(
        collect(model).map(({ fn, range }) => ({
          range,
          options: {
            inlineClassName: "cm-navigable-fn-token",
            hoverMessage: { value: `**${fn}**\n\nCtrl/Cmd + Click to navigate` },
            stickiness:
              monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
          },
        })),
      );
    };
    recomputeHighlightsRef.current = recompute;
    const contentSub = editor.onDidChangeModelContent(() => recompute());
    recompute();

    disposablesRef.current.push(linkProvider, linkOpener, contentSub, {
      dispose: () => decorations.clear(),
    });
  };

  // ---- Render branches -----------------------------------------------------
  if (listState === "loading") {
    return (
      <div className="center-msg">
        <span className="spin" /> Loading Code Map…
      </div>
    );
  }

  if (listState === "error") {
    return (
      <div className="center-msg" style={{ color: "var(--red)" }}>
        Failed to load Code Map: {listError}
      </div>
    );
  }

  if (listState === "needs-build") {
    return (
      <>
        <div className="cm-empty">
          <div className="cm-empty-card">
            <div className="cm-empty-title">No Code Map for this model/release</div>
            <p className="cm-empty-sub">
              {relHasSource
                ? "Source is imported for this release — build the code map to " +
                  "explore the call graph and browse each function."
                : "Build a code map to explore the call graph and browse the C " +
                  "source for each function. The source folder you choose is " +
                  "imported and saved with this release."}
            </p>
            <button
              className="save-btn"
              disabled={building}
              onClick={() => (relHasSource ? startBuild("") : setBuildOpen(true))}
            >
              {building
                ? "Building…"
                : relHasSource
                  ? "Build Code Map"
                  : "Choose Source & Build"}
            </button>
            {relHasSource && (
              <button
                className="link-btn"
                disabled={building}
                onClick={() => setBuildOpen(true)}
              >
                Use a different source folder…
              </button>
            )}
          </div>
        </div>
        {buildOpen && (
          <FolderPicker
            mode="folder"
            title="Build Code Map — choose the C source folder"
            hint="Navigate to the folder containing the C source"
            onCancel={() => setBuildOpen(false)}
            onConfirm={(path) => startBuild(path)}
          />
        )}
      </>
    );
  }

  // ready
  const q = search.trim().toLowerCase();
  const shown = q
    ? functions.filter((f) => f.toLowerCase().includes(q))
    : functions;

  return (
    <div className="cm-root">
      <aside className="cm-sidebar">
        <div className="cm-status">
          <span
            className={"cm-stat-badge " + (relHasSource ? "on" : "off")}
            title={
              relHasSource
                ? "C/H source is imported for the active release"
                : "No source imported for the active release"
            }
          >
            <span className="cm-stat-dot" /> Source
          </span>
          <span
            className={"cm-stat-badge " + (mindmapOn ? "on" : "off")}
            title={
              mindmapOn
                ? "A code mind map is available for AI grounding"
                : "No mind map yet — build one in AI Generation"
            }
          >
            <span className="cm-stat-dot" /> Mind Map
          </span>
        </div>
        <div className="cm-search">
          <input
            type="text"
            placeholder={`Search ${functions.length} functions…`}
            spellCheck={false}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="cm-fnlist">
          {shown.length === 0 ? (
            <div className="cm-det-empty">No matches</div>
          ) : (
            shown.map((f) => (
              <button
                key={f}
                className={"cm-fn" + (f === focused ? " sel" : "")}
                title={f}
                onClick={() => setFocused(f)}
              >
                {f}
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="cm-center">
        <div className="cm-graph-panel">
          <div className="cm-panel-head">
            Call Graph
            <div className="cm-legend">
              <span className="cm-leg caller">
                <i /> Callers
              </span>
              <span className="cm-leg center">
                <i /> Focus
              </span>
              <span className="cm-leg callee">
                <i /> Callees
              </span>
            </div>
          </div>
          <div className="cm-graph-body">
            <CallGraph graph={graph} focus={focused} onFocus={setFocused} />
          </div>
        </div>

        <div className="cm-ide-panel">
          <div className="cm-panel-head">
            {focused ?? "—"}
            {detail?.file && (
              <span className="cm-panel-sub">{detail.file}</span>
            )}
          </div>
          <div className="cm-editor">
            <Editor
              language="c"
              theme={theme}
              value={source?.found ? source.source : ""}
              onMount={onEditorMount}
              options={{
                readOnly: true,
                domReadOnly: true,
                minimap: { enabled: false },
                fontSize: 12,
                lineNumbers: "on",
                scrollBeyondLastLine: false,
                renderLineHighlight: "none",
                automaticLayout: true,
              }}
            />
            {source && !source.found && (
              <div className="cm-nosource">
                {source.reason ?? "No source available for this function."}
              </div>
            )}
          </div>
          <DetailsCard detail={detail} source={source} onFocus={setFocused} />
        </div>
      </div>
    </div>
  );
}
