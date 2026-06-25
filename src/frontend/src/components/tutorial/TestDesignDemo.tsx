import { TutorialShell, type TutorialStep } from "./TutorialShell";

// Interactive walkthrough of Test Design — author one markdown template with
// placeholders, and the app expands it into a test-case document for every
// validated port, previewed live and exported in bulk.

type Highlight = "stage" | "title" | "template" | "grouping" | "preview" | "export";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What Test Design does",
    highlight: "stage",
    body: (
      <>
        Test Design turns your validated ports into <strong>test-case documents</strong>.
        You write <em>one</em> template with placeholders; the app fills it in for
        every port and grouping, so a whole test spec stays consistent.
      </>
    ),
  },
  {
    title: "1 · Name the document",
    highlight: "title",
    body: (
      <>
        Set a <strong>Project Title</strong>. It can use the same placeholders as
        the body — here <code>[Model] — [Input Port]</code> — so each generated
        case gets a meaningful heading.
      </>
    ),
  },
  {
    title: "2 · Write the template",
    highlight: "template",
    body: (
      <>
        Author the <strong>Design Template</strong> in markdown. Tokens like{" "}
        <code>[Input Port]</code>, <code>[Data Type]</code> and{" "}
        <code>[Operation]</code> are replaced per row. Autocomplete suggests every
        available token.
      </>
    ),
  },
  {
    title: "3 · Choose the grouping",
    highlight: "grouping",
    body: (
      <>
        <strong>Operation grouping</strong> controls how rows are batched into
        cases — one per port, one per operation, and so on. The pager count
        updates to match.
      </>
    ),
  },
  {
    title: "4 · Check the live preview",
    highlight: "preview",
    body: (
      <>
        The <strong>Preview</strong> renders the filled-in markdown for the current
        row. Page through with <strong>‹ ›</strong> to spot-check how each case
        will read before exporting.
      </>
    ),
  },
  {
    title: "5 · Export the test cases",
    highlight: "export",
    body: (
      <>
        <strong>Export Test Cases</strong> writes the current model's documents;{" "}
        <strong>Export All Models</strong> does the whole project at once — ready to
        drop into your test management tool.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        One template → every port → a full, consistent test spec. Replay any time
        from <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

const TEMPLATE = [
  "## Verify [Input Port]",
  "",
  "**Type:** [Data Type]",
  "**Operation:** [Operation]",
  "",
  "1. Stimulate [Input Port]",
  "2. Assert response is valid",
];

export function TestDesignDemo({ onClose }: { onClose: () => void }) {
  return (
    <TutorialShell title="Test Design — interactive walkthrough" steps={STEPS} onClose={onClose}>
      {({ step, hl }) => {
        const titled = step >= 1;
        const templated = step >= 2;
        const previewing = step >= 4;
        const grouping = step >= 3 ? "Per operation" : "Per port";

        return (
          <>
            <div className="demo-center demo-td-full">
              {/* Toolbar */}
              <div className="demo-scopebar">
                <span className={"demo-td-group" + hl("grouping")} data-demo="grouping">
                  Operation grouping: <b>{grouping} ▾</b>
                </span>
                <div className="demo-spacer" />
                <span className="demo-btn">Export All Models</span>
                <span className={"demo-btn primary" + hl("export")} data-demo="export">
                  Export Test Cases
                </span>
              </div>

              <div className="demo-td-split">
                {/* Editor */}
                <div className="demo-td-editor">
                  <div className={"demo-td-field" + hl("title")} data-demo="title">
                    <span className="demo-td-flabel">Project Title</span>
                    <div className="demo-td-input">
                      {titled ? "BMS_Controller — [Input Port]" : (
                        <span className="demo-muted">e.g. [Model] — [Input Port]</span>
                      )}
                    </div>
                  </div>
                  <div className="demo-td-flabel">Design Template</div>
                  <div className={"demo-code demo-td-tmpl" + hl("template")} data-demo="template">
                    {(templated ? TEMPLATE : ["", "", "    Start typing your template…"]).map((l, i) => (
                      <div className="demo-codeline" key={i}>
                        <span className="demo-gutter">{i + 1}</span>
                        <span className="demo-codetext demo-md">{renderTokens(l)}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Preview */}
                <div className={"demo-td-preview" + hl("preview")} data-demo="preview">
                  <div className="demo-panel-head">
                    Preview
                    <div className="demo-spacer" />
                    <span className="demo-pager">‹ Port {previewing ? 2 : 1} of 4 ›</span>
                  </div>
                  <div className="demo-td-md">
                    {templated ? (
                      <>
                        <h4>Verify Pwm_SetDuty</h4>
                        <p><b>Type:</b> uint8<br /><b>Operation:</b> Write</p>
                        <ol>
                          <li>Stimulate Pwm_SetDuty</li>
                          <li>Assert response is valid</li>
                        </ol>
                      </>
                    ) : (
                      <div className="demo-editor-empty">Write a template to preview.</div>
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

// Highlight [Token] spans inside a template line.
function renderTokens(line: string) {
  const parts = line.split(/(\[[^\]]+\])/g);
  return parts.map((p, i) =>
    /^\[[^\]]+\]$/.test(p) ? (
      <span key={i} className="demo-token">{p}</span>
    ) : (
      <span key={i}>{p}</span>
    ),
  );
}
