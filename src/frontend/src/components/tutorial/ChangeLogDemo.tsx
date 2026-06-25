import { TutorialShell, type TutorialStep } from "./TutorialShell";

// Interactive walkthrough of the Change Log — a side-by-side diff between two
// releases of the same model, with an optional AI-written summary.

type Highlight = "stage" | "compute" | "filelist" | "diff" | "ai";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What the Change Log is",
    highlight: "stage",
    body: (
      <>
        The Change Log shows exactly <strong>what changed between two releases</strong>{" "}
        of the same firmware — file by file, line by line — so you can review a
        build before signing it off.
      </>
    ),
  },
  {
    title: "1 · Choose releases to compare",
    highlight: "compute",
    body: (
      <>
        Pick a <strong>previous release</strong> to compare against the active one,
        then click <strong>Compute Release Diff</strong>. The result is cached, so
        re-opening it later is instant.
      </>
    ),
  },
  {
    title: "2 · Browse the changed files",
    highlight: "filelist",
    body: (
      <>
        The sidebar lists every changed file with a badge:{" "}
        <span className="demo-badge-inline a">A</span> added,{" "}
        <span className="demo-badge-inline m">M</span> modified,{" "}
        <span className="demo-badge-inline d">D</span> deleted. Click one to open
        its diff.
      </>
    ),
  },
  {
    title: "3 · Read the side-by-side diff",
    highlight: "diff",
    body: (
      <>
        The diff pane shows the old release on the left and the new one on the
        right. Removed lines are <span className="demo-inl-del">red</span>, added
        lines are <span className="demo-inl-add">green</span> — aligned so changes
        line up.
      </>
    ),
  },
  {
    title: "4 · Read the AI summary",
    highlight: "ai",
    body: (
      <>
        Expand <strong>AI Summary</strong> for a plain-language change log of the
        selected file — what changed and why it matters — generated from the diff.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        Choose two releases, compute the diff, walk the changed files, and let the
        AI summarize each one. Replay any time from{" "}
        <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

interface F {
  name: string;
  badge: "a" | "m" | "d";
}
const FILES: F[] = [
  { name: "adc.c", badge: "m" },
  { name: "pwm.c", badge: "m" },
  { name: "diag.c", badge: "a" },
  { name: "legacy_io.c", badge: "d" },
];

// Aligned diff rows: [oldLine, newLine, kind]
const DIFF: [string, string, "same" | "del" | "add"][] = [
  ['uint16_t Adc_ReadChannel(uint8_t ch) {', 'uint16_t Adc_ReadChannel(uint8_t ch) {', "same"],
  ['    Adc_StartConversion(ch);', '    Adc_StartConversion(ch);', "same"],
  ['    return Adc_GetResult();', '', "del"],
  ['', '    uint16_t v = Adc_GetResult();', "add"],
  ['', '    Diag_Log(v);', "add"],
  ['', '    return v;', "add"],
  ['}', '}', "same"],
];

export function ChangeLogDemo({ onClose }: { onClose: () => void }) {
  return (
    <TutorialShell title="Change Log — interactive walkthrough" steps={STEPS} onClose={onClose}>
      {({ step, hl }) => {
        const computed = step >= 2;
        const aiOpen = step >= 4;

        return (
          <>
            {/* Sidebar: file list */}
            <div className={"demo-sidebar" + hl("filelist")} data-demo="filelist">
              <div className="demo-search demo-cm-search">⌕ Search 4 files…</div>
              <div className="demo-pane-body demo-fnlist">
                {computed ? (
                  FILES.map((f, i) => (
                    <div key={f.name} className={"demo-cl-file" + (i === 0 ? " sel" : "")}>
                      <span className={"demo-cl-badge " + f.badge}>{f.badge.toUpperCase()}</span>
                      <span>{f.name}</span>
                    </div>
                  ))
                ) : (
                  <div className="demo-muted">Compute a diff to list files.</div>
                )}
              </div>
            </div>

            {/* Center */}
            <div className="demo-center">
              <div className={"demo-scopebar" + hl("compute")} data-demo="compute">
                <span className="demo-release-pick">Compare: v2.0 (previous) ▾</span>
                <span className="demo-muted">→ v2.4 (active)</span>
                <div className="demo-spacer" />
                <span className="demo-btn primary">
                  {computed ? "✓ Diff computed" : "Compute Release Diff"}
                </span>
              </div>

              <div className={"demo-diff-pane" + hl("diff")} data-demo="diff">
                <div className="demo-panel-head">
                  adc.c<span className="demo-panel-sub">src/drivers/adc.c</span>
                </div>
                {computed ? (
                  <div className="demo-diff-cols">
                    <div className="demo-diff-col">
                      {DIFF.map(([o, , k], i) => (
                        <div key={i} className={"demo-diffline " + (k === "del" ? "del" : k === "add" ? "blank" : "")}>
                          <span className="demo-gutter">{o ? i : ""}</span>
                          <span className="demo-codetext">{o}</span>
                        </div>
                      ))}
                    </div>
                    <div className="demo-diff-col">
                      {DIFF.map(([, n, k], i) => (
                        <div key={i} className={"demo-diffline " + (k === "add" ? "add" : k === "del" ? "blank" : "")}>
                          <span className="demo-gutter">{n ? i : ""}</span>
                          <span className="demo-codetext">{n}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="demo-editor-empty">Select a file to view its diff.</div>
                )}
              </div>

              <div className={"demo-ai-panel" + (aiOpen ? "" : " collapsed") + hl("ai")} data-demo="ai">
                <div className="demo-ai-head">
                  <span>{aiOpen ? "▾" : "▸"}</span> AI Summary
                </div>
                {aiOpen && (
                  <div className="demo-ai-body">
                    <strong>adc.c</strong> — <code>Adc_ReadChannel</code> now logs each
                    reading via <code>Diag_Log</code> before returning. Adds a diagnostic
                    side-effect; return value unchanged.
                  </div>
                )}
              </div>
            </div>
          </>
        );
      }}
    </TutorialShell>
  );
}
