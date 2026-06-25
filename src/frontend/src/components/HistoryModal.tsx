import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { HistoryEntry, HistoryResponse } from "../api/types";

type LoadState = "loading" | "ready" | "error";

// Format an ISO-8601 UTC timestamp as "YYYY-MM-DD HH:MM:SS UTC" (matches the
// PyQt history dialog). Falls back to the raw string if it can't be parsed.
function formatTs(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ` +
    `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} UTC`
  );
}

// Read-only ASPICE change-history viewer. `query` is the querystring (incl. the
// leading "?") that scopes the fetch — model-wide or filtered to one port.
export function HistoryModal({
  title,
  subtitle,
  query,
  onClose,
}: {
  title: string;
  subtitle?: string;
  query: string;
  onClose: () => void;
}) {
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    setState("loading");
    (async () => {
      try {
        const res = await api.get<HistoryResponse>(`/history${query}`);
        if (!alive) return;
        setEntries(res.entries);
        setState("ready");
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message);
        setState("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [query]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.description.toLowerCase().includes(q) ||
        e.user.toLowerCase().includes(q) ||
        e.model.toLowerCase().includes(q),
    );
  }, [entries, search]);

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        className="modal history-modal"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          {title}
          {subtitle ? <span className="hist-sub">{subtitle}</span> : null}
          <button className="prefs-close" onClick={onClose} title="Close">
            ✕
          </button>
        </div>

        <div className="hist-toolbar">
          <input
            type="text"
            placeholder="Filter entries…"
            spellCheck={false}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <span className="hist-count">
            {filtered.length}
            {filtered.length !== entries.length ? ` / ${entries.length}` : ""}{" "}
            entries
          </span>
        </div>

        <div className="hist-body">
          {state === "loading" ? (
            <div className="center-msg">
              <span className="spin" />
              &nbsp;Loading history…
            </div>
          ) : state === "error" ? (
            <div className="center-msg" style={{ color: "var(--red)" }}>
              {error}
            </div>
          ) : filtered.length === 0 ? (
            <div className="center-msg">No history entries.</div>
          ) : (
            <table className="hist-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>User</th>
                  <th>Architecture Model</th>
                  <th>Change Description</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((e, i) => (
                  <tr key={i}>
                    <td className="hist-ts">{formatTs(e.timestamp)}</td>
                    <td>{e.user}</td>
                    <td>{e.model || "N/A"}</td>
                    <td className="hist-desc">{e.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="hist-foot">
          This log is read-only and permanently tracks all modifications to the
          architecture (ASPICE traceability).
        </div>
      </div>
    </div>
  );
}
