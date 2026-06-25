import { useEffect, useRef, useState } from "react";

export interface MenuItem {
  label?: string;
  onClick?: () => void;
  checked?: boolean;
  danger?: boolean;
  // A non-interactive divider. When set, the other fields are ignored.
  separator?: boolean;
  // Keep the menu open after clicking (e.g. independent visibility toggles).
  keepOpen?: boolean;
}

// A lightweight popup menu anchored at viewport coords. Closes on outside
// click or Escape. Used by status pills and the row kebab — so every action is
// reachable from a visible control, never right-click-only (plan §4.2).
export function Menu({
  x,
  y,
  items,
  onClose,
}: {
  x: number;
  y: number;
  items: MenuItem[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const [viewportHeight, setViewportHeight] = useState(window.innerHeight);
  useEffect(() => {
    const handleResize = () => setViewportHeight(window.innerHeight);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Statically calculate maximum height: each option is ~30px plus padding/borders
  const estimatedHeight = items.length * 30 + 15;
  const showAbove = y + estimatedHeight > viewportHeight;
  const topPos = showAbove ? y - 45 : y; // y - 4px padding - 37px row height - 4px gap = y - 45
  const transform = showAbove ? "translateY(-100%)" : undefined;

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div
      className="menu"
      ref={ref}
      style={{
        left: x,
        top: topPos,
        transform,
      }}
    >
      {items.map((it, i) =>
        it.separator ? (
          <div key={i} className="menu-sep" />
        ) : (
          <button
            key={i}
            className={it.danger ? "danger" : undefined}
            style={it.danger ? { color: "var(--red)" } : undefined}
            onClick={() => {
              it.onClick?.();
              if (!it.keepOpen) onClose();
            }}
          >
            <span className="check">{it.checked ? "✓" : ""}</span>
            {it.label}
          </button>
        ),
      )}
    </div>
  );
}
