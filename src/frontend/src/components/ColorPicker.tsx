import { useEffect, useRef, useState } from "react";

// A small in-app HSV colour picker (saturation/value square + hue slider + hex),
// styled with the app's tokens — replaces the native OS colour dialog so the
// "Distro Hop (Custom)" accent matches the design language.

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let r = 0, g = 0, b = 0;
  if (h < 60) [r, g] = [c, x];
  else if (h < 120) [r, g] = [x, c];
  else if (h < 180) [g, b] = [c, x];
  else if (h < 240) [g, b] = [x, c];
  else if (h < 300) [r, b] = [x, c];
  else [r, b] = [c, x];
  return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
}

function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map((n) => clamp(n, 0, 255).toString(16).padStart(2, "0")).join("");
}

function hexToHsv(hex: string): { h: number; s: number; v: number } {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return { h: 210, s: 0.8, v: 1 };
  const int = parseInt(m[1], 16);
  const r = ((int >> 16) & 255) / 255, g = ((int >> 8) & 255) / 255, b = (int & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max ? d / max : 0, v: max };
}

export function ColorPicker({
  value,
  x,
  y,
  onChange,
  onClose,
}: {
  value: string;
  x: number;
  y: number;
  onChange: (hex: string) => void;
  onClose: () => void;
}) {
  const init = hexToHsv(value);
  const [h, setH] = useState(init.h);
  const [s, setS] = useState(init.s);
  const [v, setV] = useState(init.v);
  const [hexText, setHexText] = useState(value);
  const ref = useRef<HTMLDivElement>(null);
  const svRef = useRef<HTMLDivElement>(null);
  const hueRef = useRef<HTMLDivElement>(null);

  const hex = rgbToHex(...hsvToRgb(h, s, v));

  // Push the live colour up (drives --v-accent in real time).
  useEffect(() => {
    onChange(hex);
    setHexText(hex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [h, s, v]);

  // Close on outside click / Escape.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  function dragSV(e: React.MouseEvent) {
    const rect = svRef.current!.getBoundingClientRect();
    const move = (cx: number, cy: number) => {
      setS(clamp((cx - rect.left) / rect.width, 0, 1));
      setV(clamp(1 - (cy - rect.top) / rect.height, 0, 1));
    };
    move(e.clientX, e.clientY);
    const mm = (ev: MouseEvent) => move(ev.clientX, ev.clientY);
    const mu = () => {
      document.removeEventListener("mousemove", mm);
      document.removeEventListener("mouseup", mu);
    };
    document.addEventListener("mousemove", mm);
    document.addEventListener("mouseup", mu);
  }

  function dragHue(e: React.MouseEvent) {
    const rect = hueRef.current!.getBoundingClientRect();
    const move = (cx: number) => setH(clamp((cx - rect.left) / rect.width, 0, 1) * 360);
    move(e.clientX);
    const mm = (ev: MouseEvent) => move(ev.clientX);
    const mu = () => {
      document.removeEventListener("mousemove", mm);
      document.removeEventListener("mouseup", mu);
    };
    document.addEventListener("mousemove", mm);
    document.addEventListener("mouseup", mu);
  }

  function commitHex(t: string) {
    setHexText(t);
    if (/^#?[0-9a-f]{6}$/i.test(t.trim())) {
      const hv = hexToHsv(t);
      setH(hv.h);
      setS(hv.s);
      setV(hv.v);
    }
  }

  return (
    <div className="colorpicker" ref={ref} style={{ left: x, top: y }}>
      <div
        className="cp-sv"
        ref={svRef}
        onMouseDown={dragSV}
        style={{
          background:
            `linear-gradient(to top, #000, transparent), ` +
            `linear-gradient(to right, #fff, hsl(${h}, 100%, 50%))`,
        }}
      >
        <span className="cp-sv-thumb" style={{ left: `${s * 100}%`, top: `${(1 - v) * 100}%` }} />
      </div>

      <div className="cp-hue" ref={hueRef} onMouseDown={dragHue}>
        <span className="cp-hue-thumb" style={{ left: `${(h / 360) * 100}%` }} />
      </div>

      <div className="cp-foot">
        <span className="cp-swatch" style={{ background: hex }} />
        <input
          className="cp-hex"
          value={hexText}
          spellCheck={false}
          onChange={(e) => commitHex(e.target.value)}
        />
        <button className="save-btn" onClick={onClose}>Done</button>
      </div>
    </div>
  );
}
