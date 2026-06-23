import { useState } from "react";
import { TestInjectionDemo } from "./TestInjectionDemo";

// "Tutorials" preferences section: a list of interactive guides. Each card
// launches a self-contained, click-through demo (no real data is touched).
interface Tutorial {
  key: string;
  title: string;
  blurb: string;
  icon: string;
  render: (onClose: () => void) => React.ReactNode;
}

const TUTORIALS: Tutorial[] = [
  {
    key: "test-injection",
    title: "Test Injection workflow",
    blurb:
      "Create a test project, hook test code into a source file, and export build-ready output — step by step, on a simulated screen.",
    icon: "💉",
    render: (onClose) => <TestInjectionDemo onClose={onClose} />,
  },
];

export function Tutorials() {
  const [active, setActive] = useState<Tutorial | null>(null);

  return (
    <div className="prefs-body">
      <div className="prefs-field">
        <div className="prefs-hint">
          Interactive walkthroughs of the app's features. Each one runs in a safe
          sandbox — nothing in your real projects is changed.
        </div>
      </div>

      <div className="tut-list">
        {TUTORIALS.map((t) => (
          <button key={t.key} className="tut-card" onClick={() => setActive(t)}>
            <span className="tut-card-icon">{t.icon}</span>
            <span className="tut-card-text">
              <span className="tut-card-title">{t.title}</span>
              <span className="tut-card-blurb">{t.blurb}</span>
            </span>
            <span className="tut-card-go">Start ▸</span>
          </button>
        ))}
      </div>

      {active && active.render(() => setActive(null))}
    </div>
  );
}
