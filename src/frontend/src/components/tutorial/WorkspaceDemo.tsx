import { TutorialShell, type TutorialStep } from "./TutorialShell";

// Interactive walkthrough of the Workspace — the architecture-validation matrix
// where Rhapsody model ports are matched against the firmware's real ELF
// symbols. The mock screen is derived purely from the step index.

type Highlight =
  | "stage"
  | "sidebar"
  | "row"
  | "rematch"
  | "addport"
  | "compare"
  | "aspice";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What the Workspace is",
    highlight: "stage",
    body: (
      <>
        The Workspace is the <strong>architecture-validation matrix</strong>. Each
        row is a <em>port</em> from your Rhapsody model; the columns confirm it
        against the firmware's real ELF symbols. The goal: prove every designed
        interface actually exists in the built software.
      </>
    ),
  },
  {
    title: "1 · Pick a model and release",
    highlight: "sidebar",
    body: (
      <>
        On the left, choose the <strong>model</strong> you're validating and the{" "}
        <strong>release</strong> to validate it against. The whole matrix follows
        this selection, so you can re-check the same architecture across builds.
      </>
    ),
  },
  {
    title: "2 · Read a port row",
    highlight: "row",
    body: (
      <>
        Every row pairs a designed port with its <strong>Symbol Match</strong> (the
        real ELF symbol it resolved to, with a confidence score) and a{" "}
        <strong>State</strong>. A green high-score match means the architecture and
        the code agree.
      </>
    ),
  },
  {
    title: "3 · Re-match symbols",
    highlight: "rematch",
    body: (
      <>
        After importing a new build, click <strong>Re-match Symbols</strong> to
        auto-link every port to the closest ELF symbol. Low-confidence rows are
        flagged so you can fix them by hand from the match picker.
      </>
    ),
  },
  {
    title: "4 · Add a port and review",
    highlight: "addport",
    body: (
      <>
        Use <strong>＋ Add Port</strong> to capture an interface the model missed,
        edit cells inline, then mark rows <strong>Reviewed</strong>. The status bar
        tracks how much of the matrix you've signed off.
      </>
    ),
  },
  {
    title: "5 · Compare against a baseline",
    highlight: "compare",
    body: (
      <>
        Load a frozen <strong>baseline</strong> release to compare. The banner marks
        the view read-only and highlights rows that <em>changed</em> since the
        baseline — so a regression in the architecture is impossible to miss.
      </>
    ),
  },
  {
    title: "6 · Read the release results",
    highlight: "aspice",
    body: (
      <>
        The <strong>Result</strong> column rolls each port up to an ASPICE-style
        verdict for the release — <em>Pass</em>, <em>Block</em>,{" "}
        <em>No Result</em> or <em>Not Run</em> — giving auditors a single column to
        scan.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        That's the loop: <strong>select model + release → re-match → review →
        compare to baseline</strong>. Everything is non-destructive, and you can
        replay this any time from <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

interface Row {
  port: string;
  dir: string;
  type: string;
  match: string;
  score: "high" | "mid" | "low";
  state: "ok" | "work";
  result: "pass" | "block" | "none";
  changed?: boolean;
  added?: boolean;
}

const BASE_ROWS: Row[] = [
  { port: "Adc_Read", dir: "Out", type: "uint16", match: "Adc_ReadChannel · 98%", score: "high", state: "ok", result: "pass" },
  { port: "Pwm_SetDuty", dir: "In", type: "uint8", match: "Pwm_SetDuty · 95%", score: "high", state: "ok", result: "pass" },
  { port: "Can_Send", dir: "Out", type: "Frame*", match: "Can_Transmit · 71%", score: "mid", state: "work", result: "block" },
  { port: "Diag_Report", dir: "Out", type: "void", match: "— unmatched", score: "low", state: "work", result: "none" },
];

export function WorkspaceDemo({ onClose }: { onClose: () => void }) {
  return (
    <TutorialShell title="Workspace — interactive walkthrough" steps={STEPS} onClose={onClose}>
      {({ step, hl }) => {
        const reMatched = step >= 3;
        const portAdded = step >= 4;
        const comparing = step >= 5 && step < 7;
        const showResult = step >= 6;

        // Derive the visible rows from the step.
        const rows: Row[] = BASE_ROWS.map((r) => {
          if (reMatched && r.port === "Diag_Report")
            return { ...r, match: "Diag_LogFault · 88%", score: "high", state: "ok", result: "pass" };
          if (reMatched && r.port === "Can_Send")
            return { ...r, match: "Can_Transmit · 96%", score: "high", state: "ok", result: "pass" };
          return r;
        });
        if (portAdded)
          rows.push({
            port: "Wdt_Kick",
            dir: "Out",
            type: "void",
            match: "Wdt_Refresh · 99%",
            score: "high",
            state: "ok",
            result: "pass",
            added: true,
          });
        if (comparing) {
          rows.forEach((r) => {
            if (r.port === "Pwm_SetDuty") r.changed = true;
          });
        }

        return (
          <>
            {/* Sidebar: models + release */}
            <div className={"demo-sidebar" + hl("sidebar")} data-demo="sidebar">
              <div className="demo-pane">
                <div className="demo-sect-head"><span>Models</span></div>
                <div className="demo-pane-body">
                  {["BMS_Controller", "Charger_FSM"].map((m, i) => (
                    <div key={m} className={"demo-file" + (i === 0 ? " sel" : "")}>
                      <span className="demo-file-ico src" />
                      {m}
                    </div>
                  ))}
                </div>
              </div>
              <div className="demo-pane">
                <div className="demo-sect-head"><span>Release</span></div>
                <div className="demo-pane-body">
                  <div className="demo-release-pick">
                    {comparing ? "v2.4 ⇄ v2.0 (baseline)" : "v2.4 ▾"}
                  </div>
                  <div className="demo-muted demo-source-row">
                    <span className="demo-file-ico test" /> firmware_v2.4.elf
                  </div>
                </div>
              </div>
            </div>

            {/* Main: scopebar + matrix */}
            <div className="demo-center">
              {comparing && (
                <div className={"demo-baseline-banner" + hl("compare")} data-demo="compare">
                  🔒 Comparing to baseline <b>v2.0</b> — read-only; changed rows flagged.
                </div>
              )}

              <div className="demo-scopebar">
                <div className="demo-search">⌕ Search ports…</div>
                <span className="demo-btn">Filter ▾</span>
                <span className={"demo-btn" + hl("rematch")} data-demo="rematch">
                  Re-match Symbols
                </span>
                <div className="demo-spacer" />
                <span className={"demo-btn primary" + hl("addport")} data-demo="addport">
                  ＋ Add Port
                </span>
              </div>

              <div className={"demo-grid" + hl("row") + hl("aspice")} data-demo="grid">
                <div className="demo-grid-head">
                  <span>Port</span>
                  <span>Dir</span>
                  <span>Type</span>
                  <span>Symbol Match</span>
                  <span>State</span>
                  {showResult && <span className="demo-result-col">Result</span>}
                </div>
                {rows.map((r) => (
                  <div
                    key={r.port}
                    className={
                      "demo-grid-row" +
                      (r.added ? " added" : "") +
                      (r.changed ? " changed" : "")
                    }
                  >
                    <span className="demo-cell-port">{r.port}</span>
                    <span>{r.dir}</span>
                    <span className="demo-mono">{r.type}</span>
                    <span className={"demo-match " + r.score}>{r.match}</span>
                    <span>
                      <span className={"demo-state-pill " + r.state}>
                        {r.state === "ok" ? "Reviewed" : "In Work"}
                      </span>
                    </span>
                    {showResult && (
                      <span className="demo-result-col">
                        <span className={"demo-result " + r.result}>
                          {r.result === "pass"
                            ? "Pass"
                            : r.result === "block"
                              ? "Block"
                              : "No Result"}
                        </span>
                      </span>
                    )}
                  </div>
                ))}
              </div>

              <div className="demo-inspector">
                <span className="demo-inspector-label">
                  {rows.length} ports · {rows.filter((r) => r.state === "ok").length} reviewed
                </span>
              </div>
            </div>
          </>
        );
      }}
    </TutorialShell>
  );
}
