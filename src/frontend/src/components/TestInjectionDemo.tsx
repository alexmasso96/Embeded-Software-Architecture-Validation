import { TutorialShell, type TutorialStep } from "./tutorial/TutorialShell";

// Self-contained, click-through tutorial for the Test Injection workflow.
// Nothing here touches real data or the backend — it renders a simplified mock
// of the Test Injection screen and reveals the workflow one step at a time, so
// the user can learn it safely even with no project open. The mock's state is
// derived purely from the current step index, so Back/Next stay consistent.

type Highlight =
  | "stage"
  | "projects"
  | "source"
  | "modeswitch"
  | "snippet"
  | "testfiles"
  | "export";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What Test Injection does",
    highlight: "stage",
    body: (
      <>
        It lets you splice extra C code — instrumentation, stubs, a test harness —
        into your firmware <strong>without ever editing the real source files</strong>.
        Your edits are saved as <em>hooks</em> in the project and applied only to
        generated copies. This walkthrough shows the full flow end to end.
      </>
    ),
  },
  {
    title: "1 · Create a test project",
    highlight: "projects",
    body: (
      <>
        Click <strong>＋</strong> next to <strong>Test Projects</strong> to make a
        container for one set of hooks, helper files and build settings. You can
        keep several (e.g. a coverage build vs. a unit harness). Select one to make
        it active — everything else on the screen follows it.
      </>
    ),
  },
  {
    title: "2 · Open a production source file",
    highlight: "source",
    body: (
      <>
        The <strong>Production Source</strong> list shows your firmware's real
        source for the active release (read-only). Click a file — here{" "}
        <code>adc.c</code> — to open it in the center editor. This is{" "}
        <em>what you inject into</em>.
      </>
    ),
  },
  {
    title: "3 · Switch to Edit and add a hook",
    highlight: "modeswitch",
    body: (
      <>
        The editor opens in <strong>Inject</strong> mode (safe preview). Switch to{" "}
        <strong>Edit</strong>, place your cursor where the code should go, and click{" "}
        <strong>＋ Hook at cursor</strong>. A hook is anchored to the surrounding
        lines, so it can re-find its spot even if the source shifts later.
      </>
    ),
  },
  {
    title: "4 · Write the injected snippet",
    highlight: "snippet",
    body: (
      <>
        Edit the hook's snippet on the right and <strong>Save</strong>. It appears
        inline in the preview (highlighted green) at the anchor point — but again,
        the real <code>adc.c</code> on disk is untouched.
      </>
    ),
  },
  {
    title: "5 · Import helper files (optional)",
    highlight: "testfiles",
    body: (
      <>
        If your injected code calls mocks or a harness, import those{" "}
        <code>.c/.h</code> files with <strong>⤓</strong> under{" "}
        <strong>Test Files</strong>. They ride along into the export but are kept
        separate from production code.
      </>
    ),
  },
  {
    title: "6 · Export the test code",
    highlight: "export",
    body: (
      <>
        Click <strong>Export</strong> and choose how:{" "}
        <strong>Modified</strong> writes only the files that have hooks;{" "}
        <strong>Reconstruct</strong> writes the whole source tree with hooks
        applied. Point it at an output folder and you get build-ready code — your
        originals stay clean.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        That's the whole loop: <strong>create a project → open source → hook in
        your code → export</strong>. Because hooks live in the project (not the
        files), you can tweak or remove them any time and re-export. Replay this
        any time from <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

const SRC_LINES = [
  '#include "adc.h"',
  "",
  "uint16_t Adc_ReadChannel(uint8_t ch) {",
  "    Adc_StartConversion(ch);",
  "    while (!Adc_Ready()) { }",
];
const SRC_TAIL = ["    return Adc_GetResult();", "}"];

export function TestInjectionDemo({ onClose }: { onClose: () => void }) {
  const snippet = 'test_log("ADC read: %d", Adc_GetResult());';

  return (
    <TutorialShell
      title="Test Injection — interactive walkthrough"
      steps={STEPS}
      onClose={onClose}
    >
      {({ step, isRecap, hl }) => {
        // Cumulative state derived from the step index.
        const projectCreated = step >= 1;
        const fileOpen = step >= 2;
        const hookAdded = step >= 3;
        const snippetWritten = step >= 4;
        const helpersImported = step >= 5;
        const showExport = step >= 6;

        return (
          <>
            <div className="demo-sidebar">
              {/* Test Projects */}
              <div className={"demo-pane" + hl("projects")} data-demo="projects">
                <div className="demo-sect-head">
                  <span>Test Projects</span>
                  <span className="demo-iconbtn pulse-if-hl">＋</span>
                </div>
                <div className="demo-pane-body">
                  {projectCreated ? (
                    <div className="demo-proj sel">
                      <span>Demo Test Project</span>
                      <span className="demo-proj-meta">
                        {helpersImported
                          ? "1f · 1h"
                          : "0f · " + (hookAdded ? "1h" : "0h")}
                      </span>
                    </div>
                  ) : (
                    <div className="demo-muted">No test projects yet.</div>
                  )}
                </div>
              </div>

              {/* Production Source */}
              <div className={"demo-pane" + hl("source")} data-demo="source">
                <div className="demo-sect-head">
                  <span>Production Source</span>
                </div>
                <div className="demo-pane-body">
                  {["adc.c", "pwm.c", "main.c"].map((f) => (
                    <div
                      key={f}
                      className={
                        "demo-file" + (fileOpen && f === "adc.c" ? " sel" : "")
                      }
                    >
                      <span className="demo-file-ico src" />
                      {f}
                    </div>
                  ))}
                </div>
              </div>

              {/* Test Files */}
              <div className={"demo-pane" + hl("testfiles")} data-demo="testfiles">
                <div className="demo-sect-head">
                  <span>Test Files</span>
                  <span className="demo-iconbtn pulse-if-hl">⤓</span>
                </div>
                <div className="demo-pane-body">
                  {helpersImported ? (
                    <div className="demo-file">
                      <span className="demo-file-ico test" />
                      test_helpers.c
                    </div>
                  ) : (
                    <div className="demo-muted">No helper files imported.</div>
                  )}
                </div>
              </div>
            </div>

            {/* Center: tabs + editor */}
            <div className="demo-center">
              <div className="demo-tabbar">
                {fileOpen && (
                  <div className="demo-tab active">
                    <span className="demo-tab-dot src" />
                    adc.c
                  </div>
                )}
                <div className="demo-spacer" />
                {fileOpen && (
                  <div
                    className={"demo-modeswitch" + hl("modeswitch")}
                    data-demo="modeswitch"
                  >
                    <span className={hookAdded ? "" : "active"}>Inject</span>
                    <span className={hookAdded ? "active" : ""}>Edit</span>
                    {hookAdded && (
                      <span className="demo-hookbtn">＋ Hook at cursor</span>
                    )}
                  </div>
                )}
              </div>

              <div className="demo-editorrow">
                <div className="demo-editor">
                  {!fileOpen ? (
                    <div className="demo-editor-empty">
                      Select a source or test file to begin.
                    </div>
                  ) : (
                    <div className="demo-code">
                      {SRC_LINES.map((l, i) => (
                        <div className="demo-codeline" key={i}>
                          <span className="demo-gutter">{i + 1}</span>
                          <span className="demo-codetext">{l}</span>
                        </div>
                      ))}
                      {hookAdded && (
                        <div className="demo-codeline injected">
                          <span className="demo-gutter">+</span>
                          <span className="demo-codetext">
                            {"    "}
                            {snippetWritten ? snippet : "/* test code */"}
                          </span>
                        </div>
                      )}
                      {SRC_TAIL.map((l, i) => (
                        <div className="demo-codeline" key={"t" + i}>
                          <span className="demo-gutter">
                            {SRC_LINES.length + i + 1}
                          </span>
                          <span className="demo-codetext">{l}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right: snippet editor for the selected hook */}
                {hookAdded && (
                  <div className={"demo-snippet" + hl("snippet")} data-demo="snippet">
                    <div className="demo-snippet-head">Hook snippet</div>
                    <div className="demo-snippet-box">
                      {snippetWritten ? snippet : "/* test code */"}
                      {!snippetWritten && <span className="demo-caret" />}
                    </div>
                    <button className="demo-save">Save</button>
                  </div>
                )}
              </div>

              <div className={"demo-buildbar" + hl("export")} data-demo="export">
                <span className="demo-build-label">Build Console</span>
                <div className="demo-spacer" />
                <span className="demo-btn">Build</span>
                <span className="demo-btn primary">Export</span>
              </div>
            </div>

            {/* Export sheet overlay */}
            {showExport && !isRecap && (
              <div className="demo-modalcard">
                <div className="demo-modalcard-head">Export test code</div>
                <label className="demo-radio">
                  <span className="demo-radio-dot on" /> Modified files only
                </label>
                <label className="demo-radio">
                  <span className="demo-radio-dot" /> Reconstruct full tree
                </label>
                <div className="demo-field">
                  Output folder: <code>~/build/instrumented</code>
                </div>
                <div className="demo-export-ok">
                  ✓ Exported 1 file (adc.c) — originals untouched
                </div>
              </div>
            )}
          </>
        );
      }}
    </TutorialShell>
  );
}
