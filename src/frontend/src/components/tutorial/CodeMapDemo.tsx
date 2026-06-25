import { TutorialShell, type TutorialStep } from "./TutorialShell";

// Interactive walkthrough of the Code Map — a call-graph + read-only IDE built
// from the firmware's symbols and source for the active release.

type Highlight = "stage" | "status" | "fnlist" | "graph" | "focus" | "ide";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What the Code Map is",
    highlight: "stage",
    body: (
      <>
        The Code Map turns the active release into a navigable{" "}
        <strong>call graph</strong> plus a read-only <strong>IDE</strong>. It's how
        you explore what calls what — without leaving the app or touching the
        source.
      </>
    ),
  },
  {
    title: "1 · Check what's available",
    highlight: "status",
    body: (
      <>
        The badges show whether <strong>Source</strong> and a{" "}
        <strong>Mind Map</strong> are loaded for this release. With source, the map
        is built from the real call tree; without it, it falls back to symbols.
      </>
    ),
  },
  {
    title: "2 · Find a function",
    highlight: "fnlist",
    body: (
      <>
        Search the function list and click one to <strong>focus</strong> it. Here{" "}
        <code>Adc_ReadChannel</code> becomes the center of the graph and opens in
        the editor.
      </>
    ),
  },
  {
    title: "3 · Read the call graph",
    highlight: "graph",
    body: (
      <>
        The focused function sits in the middle. <strong>Callers</strong> (who calls
        it) are on the left, <strong>Callees</strong> (what it calls) on the right —
        so you can trace a dependency in both directions at a glance.
      </>
    ),
  },
  {
    title: "4 · Click to re-center",
    highlight: "focus",
    body: (
      <>
        Click any node — or <strong>Ctrl/Cmd-click</strong> a symbol in the editor —
        to make it the new focus. The graph re-centers, letting you walk the call
        tree node by node.
      </>
    ),
  },
  {
    title: "5 · Inspect the source",
    highlight: "ide",
    body: (
      <>
        The IDE panel shows the focused function's source (read-only). Hover a
        symbol for its <code>#define</code> or signature; the details card below
        summarizes its callers and callees.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        Pick a function, read its callers and callees, click to walk the tree, and
        read the source inline. Replay any time from{" "}
        <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

const FNS = ["Adc_ReadChannel", "Adc_StartConversion", "Pwm_SetDuty", "Can_Transmit", "main"];
const CODE = [
  "uint16_t Adc_ReadChannel(uint8_t ch) {",
  "    Adc_StartConversion(ch);",
  "    while (!Adc_Ready()) { }",
  "    return Adc_GetResult();",
  "}",
];

export function CodeMapDemo({ onClose }: { onClose: () => void }) {
  return (
    <TutorialShell title="Code Map — interactive walkthrough" steps={STEPS} onClose={onClose}>
      {({ step, hl }) => {
        const fnSelected = step >= 2;
        const recentered = step >= 4;
        const focus = recentered ? "Adc_StartConversion" : "Adc_ReadChannel";
        const callers = recentered ? ["Adc_ReadChannel"] : ["main", "Bms_Sample"];
        const callees = recentered ? ["Adc_MuxSelect", "Adc_Trigger"] : ["Adc_StartConversion", "Adc_Ready", "Adc_GetResult"];

        return (
          <>
            {/* Sidebar */}
            <div className="demo-sidebar">
              <div className={"demo-cm-status" + hl("status")} data-demo="status">
                <span className="demo-stat-badge on"><span className="demo-stat-dot" /> Source</span>
                <span className="demo-stat-badge on"><span className="demo-stat-dot" /> Mind Map</span>
              </div>
              <div className="demo-search demo-cm-search">⌕ Search 5 functions…</div>
              <div className={"demo-pane-body demo-fnlist" + hl("fnlist")} data-demo="fnlist">
                {FNS.map((f, i) => (
                  <div key={f} className={"demo-fn" + (fnSelected && i === 0 ? " sel" : "")}>
                    {f}
                  </div>
                ))}
              </div>
            </div>

            {/* Center: graph + IDE */}
            <div className="demo-center">
              <div className={"demo-graph-panel" + hl("graph") + hl("focus")} data-demo="graph">
                <div className="demo-panel-head">
                  Call Graph
                  <span className="demo-legend">
                    <i className="caller" /> Callers <i className="center" /> Focus{" "}
                    <i className="callee" /> Callees
                  </span>
                </div>
                {fnSelected ? (
                  <div className="demo-graph-body">
                    <div className="demo-graph-col">
                      {callers.map((c) => (
                        <span key={c} className="demo-node caller">{c}</span>
                      ))}
                    </div>
                    <div className="demo-graph-edge" />
                    <div className="demo-graph-col">
                      <span className="demo-node center">{focus}</span>
                    </div>
                    <div className="demo-graph-edge" />
                    <div className="demo-graph-col">
                      {callees.map((c) => (
                        <span key={c} className="demo-node callee">{c}</span>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="demo-editor-empty">Select a function to focus the graph.</div>
                )}
              </div>

              <div className={"demo-ide-panel" + hl("ide")} data-demo="ide">
                <div className="demo-panel-head">
                  {fnSelected ? focus : "—"}
                  {fnSelected && <span className="demo-panel-sub">adc.c</span>}
                </div>
                <div className="demo-code">
                  {fnSelected ? (
                    CODE.map((l, i) => (
                      <div className="demo-codeline" key={i}>
                        <span className="demo-gutter">{i + 1}</span>
                        <span className="demo-codetext">{l}</span>
                      </div>
                    ))
                  ) : (
                    <div className="demo-editor-empty">No function focused.</div>
                  )}
                </div>
              </div>
            </div>
          </>
        );
      }}
    </TutorialShell>
  );
}
