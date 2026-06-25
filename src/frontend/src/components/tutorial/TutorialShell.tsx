import { useState, type ReactNode } from "react";

// Shared chrome for every interactive tutorial. It owns the modal overlay, the
// header/badge, the step callout, and the Back/Next/dots/Replay/Done controls
// and the current step index. Each view's guide supplies its own STEPS array
// and a render function that draws a simulated screen derived purely from the
// current step index — so Back/Next stay consistent in both directions and no
// real data or backend is ever touched.

export interface TutorialStep<H extends string = string> {
  title: string;
  body: ReactNode;
  // Which region of the simulated screen to spotlight on this step (or null).
  highlight: H | null;
}

interface TutorialShellProps<H extends string> {
  // Short label shown after the "Tutorial" badge in the header.
  title: string;
  steps: TutorialStep<H>[];
  onClose: () => void;
  // Draws the simulated screen for the given step. `hl(id)` returns " hl" when
  // `id` is the current step's highlight (else ""), for spotlighting a region.
  children: (ctx: {
    step: number;
    isRecap: boolean;
    highlight: H | null;
    hl: (id: H) => string;
  }) => ReactNode;
}

export function TutorialShell<H extends string>({
  title,
  steps,
  onClose,
  children,
}: TutorialShellProps<H>) {
  const [step, setStep] = useState(0);
  const last = steps.length - 1;
  const cur = steps[step];
  const isRecap = step === last;

  const hl = (id: H) => (cur.highlight === id ? " hl" : "");

  return (
    <div className="demo-overlay" onMouseDown={onClose}>
      <div className="demo-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="demo-header">
          <span className="demo-header-title">
            <span className="demo-badge">Tutorial</span>
            {title}
          </span>
          <button className="prefs-close" title="Close" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Simulated app screen */}
        <div className={"demo-stage" + (cur.highlight ? " spotlight" : "")}>
          {children({ step, isRecap, highlight: cur.highlight, hl })}
        </div>

        {/* Callout / controls */}
        <div className="demo-callout">
          <div className="demo-step-meta">
            Step {step + 1} of {steps.length}
          </div>
          <div className="demo-step-title">{cur.title}</div>
          <div className="demo-step-body">{cur.body}</div>

          <div className="demo-controls">
            <div className="demo-dots">
              {steps.map((_, i) => (
                <span
                  key={i}
                  className={
                    "demo-dot" + (i === step ? " on" : i < step ? " done" : "")
                  }
                  onClick={() => setStep(i)}
                />
              ))}
            </div>
            <div className="demo-spacer" />
            <button
              className="scope-btn"
              disabled={step === 0}
              onClick={() => setStep((s) => Math.max(0, s - 1))}
            >
              Back
            </button>
            {isRecap ? (
              <>
                <button className="scope-btn" onClick={() => setStep(0)}>
                  Replay
                </button>
                <button className="save-btn" onClick={onClose}>
                  Done
                </button>
              </>
            ) : (
              <button className="save-btn" onClick={() => setStep((s) => s + 1)}>
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
