import { useRef, useState } from "react";
import {
  ACCENTS,
  applyAccent,
  applyMode,
  getAccent,
  getMode,
  isCustomAccent,
  type ThemeMode,
} from "../theme";
import { ColorPicker } from "./ColorPicker";

type Category = "appearance" | "ai" | "paths";
type PreviewVariant = "light" | "dark" | "system";

const CATEGORIES: { key: Category; label: string; icon: string }[] = [
  { key: "appearance", label: "Appearance", icon: "🎨" },
  { key: "ai", label: "AI Settings", icon: "✦" },
  { key: "paths", label: "Paths", icon: "🗂" },
];

const MODES: { key: ThemeMode; label: string; variant: PreviewVariant }[] = [
  { key: "light", label: "Light", variant: "light" },
  { key: "dark", label: "Dark", variant: "dark" },
  { key: "auto", label: "System", variant: "system" },
];

// Mini app-window thumbnail used inside the theme preview cards.
function MiniWindow({ dark }: { dark: boolean }) {
  return (
    <div className={"mini " + (dark ? "mini-dark" : "mini-light")}>
      <div className="mini-bar">
        <i className="d1" />
        <i className="d2" />
        <i className="d3" />
      </div>
      <div className="mini-body">
        <span className="mini-line accent" />
        <span className="mini-line g" />
        <span className="mini-line r" />
        <span className="mini-line n" />
      </div>
    </div>
  );
}

function ThemePreview({ variant }: { variant: PreviewVariant }) {
  if (variant === "system") {
    return (
      <div className="mini-system">
        <MiniWindow dark={false} />
        <div className="mini-clip">
          <MiniWindow dark />
        </div>
      </div>
    );
  }
  return <MiniWindow dark={variant === "dark"} />;
}

// Split-column preferences dialog: categories on the left, settings on the right.
export function Preferences({
  onClose,
  onCloseProject,
}: {
  onClose: () => void;
  onCloseProject?: () => void;
}) {
  const [category, setCategory] = useState<Category>("appearance");
  const [mode, setMode] = useState<ThemeMode>(getMode());
  const [accent, setAccent] = useState<string>(getAccent());
  const [picker, setPicker] = useState<{ x: number; y: number } | null>(null);
  const rainbowRef = useRef<HTMLButtonElement>(null);

  function pickMode(m: ThemeMode) {
    setMode(m);
    applyMode(m); // live preview + persist
  }
  function pickAccent(color: string) {
    setAccent(color);
    applyAccent(color); // overrides --accent / --v-accent on :root, live
  }

  const custom = isCustomAccent(accent);
  const selectedAccentName = custom
    ? "Distro Hop (Custom)"
    : ACCENTS.find((a) => a.color.toLowerCase() === accent.toLowerCase())?.label ?? "";

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal prefs" onMouseDown={(e) => e.stopPropagation()}>
        <div className="prefs-sidebar">
          <div className="prefs-title">Preferences</div>
          {CATEGORIES.map((c) => (
            <button
              key={c.key}
              className={"prefs-cat" + (c.key === category ? " active" : "")}
              onClick={() => setCategory(c.key)}
            >
              <span className="prefs-cat-icon">{c.icon}</span>
              {c.label}
            </button>
          ))}
          {onCloseProject && (
            <>
              <div style={{ flex: 1 }} />
              <button className="prefs-close-proj-btn" onClick={onCloseProject}>
                Close Project
              </button>
            </>
          )}
        </div>

        <div className="prefs-content">
          <div className="prefs-head">
            <span>{CATEGORIES.find((c) => c.key === category)?.label}</span>
            <button className="prefs-close" onClick={onClose} title="Close">
              ✕
            </button>
          </div>

          {category === "appearance" && (
            <div className="prefs-body">
              <div className="prefs-field">
                <div className="prefs-label">Theme</div>
                <div className="theme-cards">
                  {MODES.map((m) => (
                    <button
                      key={m.key}
                      className={"theme-card" + (mode === m.key ? " active" : "")}
                      onClick={() => pickMode(m.key)}
                    >
                      <span className="theme-thumb">
                        <ThemePreview variant={m.variant} />
                      </span>
                      <span className="theme-radio-row">
                        <span className={"theme-radio" + (mode === m.key ? " on" : "")} />
                        {m.label}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="prefs-field">
                <div className="prefs-row">
                  <div className="prefs-label">Accent color</div>
                  <div className="accent-row">
                    {ACCENTS.map((a) => (
                      <button
                        key={a.key}
                        className={
                          "accent-pill" +
                          (!custom && accent.toLowerCase() === a.color.toLowerCase()
                            ? " selected"
                            : "")
                        }
                        style={{ background: a.color }}
                        aria-label={a.label}
                        onClick={() => pickAccent(a.color)}
                      />
                    ))}

                    {/* Distro Hop (Custom): multicolor pill → in-app color picker */}
                    <button
                      ref={rainbowRef}
                      className={"accent-pill rainbow" + (custom ? " selected" : "")}
                      aria-label="Distro Hop (Custom)"
                      onClick={() => {
                        const r = rainbowRef.current!.getBoundingClientRect();
                        setPicker({
                          x: Math.min(r.left, window.innerWidth - 232),
                          y: r.bottom + 8,
                        });
                      }}
                    />
                  </div>
                </div>
                <div className="accent-name">{selectedAccentName}</div>
              </div>
            </div>
          )}

          {category === "ai" && (
            <div className="prefs-body">
              <div className="prefs-placeholder">
                AI provider configuration moves here in a later slice.
              </div>
            </div>
          )}

          {category === "paths" && (
            <div className="prefs-body">
              <div className="prefs-placeholder">
                Default project / source folder paths will live here.
              </div>
            </div>
          )}
        </div>

        {/* Rendered inside .prefs so its clicks don't bubble to the overlay
            (whose onMouseDown would otherwise close the whole dialog). */}
        {picker && (
          <ColorPicker
            value={custom ? accent : "#888888"}
            x={picker.x}
            y={picker.y}
            onChange={pickAccent}
            onClose={() => setPicker(null)}
          />
        )}
      </div>
    </div>
  );
}
