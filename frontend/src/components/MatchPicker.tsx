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

  // Debounced query → /api/symbols, cancel-on-change/unmount.
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
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query, kind]);

  return (
    <div className="menu matchpicker" ref={ref} style={{ left: x, top: y }}>
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
