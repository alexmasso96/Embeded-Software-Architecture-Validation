import { TutorialShell, type TutorialStep } from "./TutorialShell";

// Interactive walkthrough of AI Generation — generate low-level tests from a
// high-level test design, grounded in the project's code mind map.

type Highlight = "stage" | "config" | "prompt" | "mindmap" | "hlt" | "generate";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What AI Generation does",
    highlight: "stage",
    body: (
      <>
        It drafts <strong>low-level test code</strong> from your high-level test
        design — grounded in a <em>code mind map</em> of the real firmware, so the
        AI writes against functions that actually exist.
      </>
    ),
  },
  {
    title: "1 · Pick a provider and model",
    highlight: "config",
    body: (
      <>
        Choose the AI <strong>Provider</strong> and <strong>Model</strong>. Keys are
        linked in <strong>Preferences → AI Settings</strong>; unconfigured providers
        are flagged here so you don't get stuck.
      </>
    ),
  },
  {
    title: "2 · Tune the prompt and rules",
    highlight: "prompt",
    body: (
      <>
        The <strong>Generation Prompt</strong> sets the task; <strong>Rules</strong>{" "}
        pin down conventions — framework, naming, assertions. Both are saved per
        project so every run is consistent.
      </>
    ),
  },
  {
    title: "3 · Build the code mind map",
    highlight: "mindmap",
    body: (
      <>
        The <strong>Code Mind Map</strong> is the AI's grounding: a structured index
        of the release's source. Build it once (needs imported source) and every
        generation stays anchored to real code.
      </>
    ),
  },
  {
    title: "4 · Choose test cases",
    highlight: "hlt",
    body: (
      <>
        Load a high-level test design (<code>.md</code>) and tick the{" "}
        <strong>test cases</strong> to expand. Cases that already have low-level
        tests are marked <strong>✓ LL</strong> so you can skip them.
      </>
    ),
  },
  {
    title: "5 · Generate and watch",
    highlight: "generate",
    body: (
      <>
        Click <strong>Generate Low-Level Tests</strong>. Progress streams in the
        console below; the output drops into your Test Injection project, ready to
        review and export.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        Provider → prompt → mind map → pick cases → generate. The mind map keeps it
        grounded in real code. Replay any time from{" "}
        <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

const CASES = [
  { t: "TC-01 Nominal ADC read", ll: true },
  { t: "TC-02 ADC timeout handling", ll: false },
  { t: "TC-03 PWM duty clamp", ll: false },
];

export function AIGenerationDemo({ onClose }: { onClose: () => void }) {
  return (
    <TutorialShell title="AI Generation — interactive walkthrough" steps={STEPS} onClose={onClose}>
      {({ step, hl }) => {
        const mmBuilt = step >= 3;
        const hltLoaded = step >= 4;
        const generating = step >= 5;

        return (
          <>
            <div className="demo-center demo-aig-full">
              {/* Config bar */}
              <div className={"demo-scopebar" + hl("config")} data-demo="config">
                <span className="demo-aig-field">Provider: <b>Claude ▾</b></span>
                <span className="demo-aig-field">Model: <b>claude-opus-4-8 ▾</b></span>
                <span className="demo-aig-field demo-muted">Diff base: v2.0 ▾</span>
              </div>

              <div className="demo-aig-split">
                {/* Left: prompt + rules + mind map */}
                <div className="demo-aig-side">
                  <div className={"demo-aig-sec" + hl("prompt")} data-demo="prompt">
                    <div className="demo-aig-head">Generation Prompt</div>
                    <div className="demo-aig-text">
                      Write Unity test cases for the selected functions…
                    </div>
                    <div className="demo-aig-subhead">Rules</div>
                    <div className="demo-aig-text rules">
                      • One TEST() per case • Mock all HW access • Assert return + side-effects
                    </div>
                  </div>

                  <div className={"demo-aig-sec" + hl("mindmap")} data-demo="mindmap">
                    <div className="demo-aig-head">Code Mind Map</div>
                    <div className="demo-aig-status">
                      <span className={"demo-dot " + (mmBuilt ? "ok" : "off")} />
                      {mmBuilt ? "Available · built just now" : "Not built for this model/release"}
                    </div>
                    <div className="demo-aig-status">
                      <span className="demo-dot ok" /> Source imported
                    </div>
                    <span className="demo-btn">
                      {mmBuilt ? "Regenerate Mind Map" : "Generate Mind Map"}
                    </span>
                  </div>
                </div>

                {/* Right: test cases + terminal */}
                <div className="demo-aig-main">
                  <div className={"demo-aig-panel" + hl("hlt")} data-demo="hlt">
                    <div className="demo-panel-head">
                      Test Cases
                      <div className="demo-spacer" />
                      <span className="demo-btn sm">
                        {hltLoaded ? "📄 adc_hlt.md" : "Choose HLT .md…"}
                      </span>
                    </div>
                    <div className="demo-aig-list">
                      {hltLoaded ? (
                        CASES.map((c) => (
                          <div key={c.t} className={"demo-aig-tc" + (!c.ll ? " sel" : "")}>
                            <span className={"demo-check" + (!c.ll ? " on" : "")} />
                            <span>{c.t}</span>
                            {c.ll && <span className="demo-ll-badge">✓ LL</span>}
                          </div>
                        ))
                      ) : (
                        <div className="demo-editor-empty">
                          Choose an HLT design file to list its test cases.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={"demo-aig-actions" + hl("generate")} data-demo="generate">
                    <span className="demo-muted">{hltLoaded ? "2 of 3 selected" : ""}</span>
                    <div className="demo-spacer" />
                    <span className="demo-btn primary">
                      {generating ? "Generating…" : "Generate Low-Level Tests"}
                    </span>
                  </div>
                  <div className="demo-aig-term">
                    {generating ? (
                      <>
                        <div>▸ Grounding against mind map… ok</div>
                        <div>▸ TC-02 → test_adc_timeout.c ✓</div>
                        <div>▸ TC-03 → test_pwm_clamp.c ✓</div>
                      </>
                    ) : (
                      <div className="demo-muted">Generation progress will stream here.</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </>
        );
      }}
    </TutorialShell>
  );
}
