import { TutorialShell, type TutorialStep } from "./TutorialShell";

// Interactive walkthrough of AI Chat — a conversational assistant that can be
// grounded in the project's code mind map to answer questions about the
// architecture, the code, and the validation results.

type Highlight = "stage" | "config" | "sysprompt" | "ground" | "composer" | "thread";

const STEPS: TutorialStep<Highlight>[] = [
  {
    title: "What AI Chat is",
    highlight: "stage",
    body: (
      <>
        A conversational assistant for <strong>this project</strong>. Ask about the
        architecture, a function, or why a port failed validation — and, when
        grounded, it answers from your real code rather than guessing.
      </>
    ),
  },
  {
    title: "1 · Pick a provider and model",
    highlight: "config",
    body: (
      <>
        Choose the <strong>Provider</strong> and <strong>Model</strong>, same as AI
        Generation. Keys live in <strong>Preferences → AI Settings</strong>.
      </>
    ),
  },
  {
    title: "2 · Set a system prompt",
    highlight: "sysprompt",
    body: (
      <>
        The <strong>System Prompt</strong> steers the assistant's role and tone —
        e.g. "You are a firmware reviewer; cite functions by name." It applies to
        the whole conversation.
      </>
    ),
  },
  {
    title: "3 · Ground in the mind map",
    highlight: "ground",
    body: (
      <>
        Tick <strong>Ground in Code Mind Map</strong> to give the assistant your
        indexed source as context. Answers then reference real functions and
        files — not generic boilerplate.
      </>
    ),
  },
  {
    title: "4 · Ask a question",
    highlight: "composer",
    body: (
      <>
        Type in the composer and press <strong>Enter</strong> to send (Shift+Enter
        for a newline). <strong>Stop</strong> interrupts a long answer mid-stream.
      </>
    ),
  },
  {
    title: "5 · Read the grounded reply",
    highlight: "thread",
    body: (
      <>
        The answer streams into the thread and points at real symbols. Keep the
        conversation going, or <strong>Clear Conversation</strong> to start fresh.
      </>
    ),
  },
  {
    title: "You're ready 🎉",
    highlight: null,
    body: (
      <>
        Configure, ground, and ask. Grounding is what turns it from a generic
        chatbot into one that knows <em>your</em> firmware. Replay any time from{" "}
        <strong>Preferences → Tutorials</strong>.
      </>
    ),
  },
];

export function AIChatDemo({ onClose }: { onClose: () => void }) {
  return (
    <TutorialShell title="AI Chat — interactive walkthrough" steps={STEPS} onClose={onClose}>
      {({ step, hl }) => {
        const grounded = step >= 3;
        const asked = step >= 4;
        const answered = step >= 5;

        return (
          <>
            {/* Left: config */}
            <div className="demo-sidebar demo-chat-config">
              <div className="demo-sect-head"><span>Chat Configuration</span></div>
              <div className="demo-chat-cfg">
                <div className={"demo-chat-providers" + hl("config")} data-demo="config">
                  <div className="demo-aig-field">Provider: <b>Claude ▾</b></div>
                  <div className="demo-aig-field">Model: <b>claude-opus-4-8 ▾</b></div>
                </div>
                <div className={"demo-chat-sys" + hl("sysprompt")} data-demo="sysprompt">
                  <span className="demo-td-flabel">System Prompt</span>
                  <div className="demo-aig-text">
                    You are a firmware reviewer; cite functions by name.
                  </div>
                </div>
                <label className={"demo-chat-ground" + hl("ground")} data-demo="ground">
                  <span className={"demo-check" + (grounded ? " on" : "")} />
                  Ground in Code Mind Map
                </label>
              </div>
            </div>

            {/* Right: console */}
            <div className="demo-center">
              <div className={"demo-chat-thread" + hl("thread")} data-demo="thread">
                {asked ? (
                  <>
                    <div className="demo-chat-msg user">
                      <div className="demo-chat-role">You</div>
                      <div className="demo-chat-bubble">
                        Which functions read the ADC, and is each one validated?
                      </div>
                    </div>
                    <div className="demo-chat-msg assistant">
                      <div className="demo-chat-role">Assistant</div>
                      <div className="demo-chat-bubble md">
                        {answered ? (
                          <>
                            <code>Adc_ReadChannel</code> is the only ADC reader; it calls{" "}
                            <code>Adc_StartConversion</code> and <code>Adc_GetResult</code>.
                            Its port <b>Adc_Read</b> matched at 98% and is marked{" "}
                            <b>Reviewed</b> ✓.
                          </>
                        ) : (
                          <span className="demo-chat-typing">▍</span>
                        )}
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="demo-editor-empty">
                    Ask a question about the architecture, the code, or the validation results.
                  </div>
                )}
              </div>

              <div className={"demo-chat-composer" + hl("composer")} data-demo="composer">
                <div className="demo-chat-input">
                  {asked
                    ? "Which functions read the ADC, and is each one validated?"
                    : "Send a message…  (Enter to send, Shift+Enter for newline)"}
                </div>
                <span className="demo-btn primary">Send</span>
              </div>
            </div>
          </>
        );
      }}
    </TutorialShell>
  );
}
