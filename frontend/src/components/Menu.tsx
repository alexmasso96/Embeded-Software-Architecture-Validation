import { useEffect, useRef } from "react";

export interface MenuItem {
  label: string;
  onClick: () => void;
  checked?: boolean;
  danger?: boolean;
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
    <div className="menu" ref={ref} style={{ left: x, top: y }}>
      {items.map((it, i) => (
        <button
          key={i}
          className={it.danger ? "danger" : undefined}
          style={it.danger ? { color: "var(--red)" } : undefined}
          onClick={() => {
            it.onClick();
            onClose();
          }}
        >
          <span className="check">{it.checked ? "✓" : ""}</span>
          {it.label}
        </button>
      ))}
    </div>
  );
}
