import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { confClass, type SymbolKind } from "../columns";

interface Candidate {
  name: string;
  score: number;
}
interface SymbolsResponse {
  query: string;
  kind: string;
  elf_hash: string | null;
  candidates: Candidate[];
}

// Anchored dropdown of fuzzy symbol candidates for a Match cell. Queries
// GET /api/symbols (scoped to the active release's ELF) with a debounced,
// editable search term seeded from the row's search cell. Picking a candidate
// fires onPick("Name (NN%)") which the workspace persists (clearing any
// conflict tint). Mirrors the Qt match dropdown, minus the widget.
export function MatchPicker({
  x,
  y,
  kind,
  initialQuery,
  current,
  onPick,
  onClose,
}: {
  x: number;
  y: number;
  kind: SymbolKind;
  initialQuery: string;
  current: string; // current matched name (no score), for the ✓
  onPick: (name: string, score: number) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(initialQuery);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [noElf, setNoElf] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [viewportHeight, setViewportHeight] = useState(window.innerHeight);
  useEffect(() => {
    const handleResize = () => setViewportHeight(window.innerHeight);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Statically determine if the picker overflows the bottom of the viewport
  // using a safe maximum height threshold of 320px:
  const showAbove = y + 320 > viewportHeight;
  const topPos = showAbove ? y - 45 : y; // y - 4px padding - 37px row height - 4px gap = y - 45
  const transform = showAbove ? "translateY(-100%)" : undefined;

  // Outside-click / Esc to close (same contract as Menu).
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    inputRef.current?.focus();
    inputRef.current?.select();
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  // Query → /api/symbols, cancel-on-change/unmount. The initial (seeded) query
  // fires immediately so the picker shows real candidates as soon as the matcher
  // returns — the spinner covers however long that takes (≈2ms on a small ELF,
  // up to ~300ms on a big set / slow CPU), avoiding a flash of an empty window.
  // Only subsequent typing is debounced (180ms) to avoid a query per keystroke.
  const firstRun = useRef(true);
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setCandidates([]);
      setLoading(false);
      setNoElf(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const delay = firstRun.current ? 0 : 180;
    firstRun.current = false;
    const t = setTimeout(async () => {
      try {
        const r = await api.get<SymbolsResponse>(
          `/symbols?q=${encodeURIComponent(q)}&kind=${kind}&limit=12`,
        );
        if (cancelled) return;
        setCandidates(r.candidates);
        setNoElf(r.elf_hash === null);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, delay);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query, kind]);

  return (
    <div
      className="menu matchpicker"
      ref={ref}
      style={{
        left: x,
        top: topPos,
        transform,
      }}
    >
      <input
        ref={inputRef}
        className="matchpicker-search"
        placeholder="Search symbols…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="matchpicker-list">
        {loading ? (
          <div className="matchpicker-msg">
            <span className="spin" />
            &nbsp;Searching…
          </div>
        ) : error ? (
          <div className="matchpicker-msg" style={{ color: "var(--red)" }}>
            {error}
          </div>
        ) : noElf ? (
          <div className="matchpicker-msg">No ELF symbols for this release.</div>
        ) : candidates.length === 0 ? (
          <div className="matchpicker-msg">No matching symbols.</div>
        ) : (
          candidates.map((c) => (
            <button
              key={c.name}
              className="matchpicker-item"
              onClick={() => {
                onPick(c.name, c.score);
                onClose();
              }}
            >
              <span className="check">{c.name === current ? "✓" : ""}</span>
              <span className="mono matchpicker-name">{c.name}</span>
              <span className={confClass(c.score)}>{c.score}%</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
