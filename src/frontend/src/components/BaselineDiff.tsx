import { useEffect, useState } from "react";
import { api } from "../api/client";
import { cellText } from "../columns";
import type { Row } from "../api/types";

type DiffStatus = "added" | "removed" | "changed" | "unchanged";

interface DiffRow {
  status: DiffStatus;
  key: string[];
  current_index: number | null;
  baseline_index: number | null;
  changed_columns: string[];
  current: Row | null;
  baseline: Row | null;
}

interface DiffResponse {
  baseline_id: number;
  baseline_name: string;
  model_id: number;
  key_columns: string[];
  columns: string[];
  rows: DiffRow[];
  summary: Record<DiffStatus, number>;
}

const STATUS_LABEL: Record<DiffStatus, string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  unchanged: "Unchanged",
};

// Table-level comparison of the active model against a baseline snapshot
// (GET /api/baselines/{id}/diff). Rows are paired server-side by a compound key
// + occurrence order; here we colour-code added / removed / changed rows and, in
// a changed row, show baseline→current for each differing cell.
export function BaselineDiff({
  baselineId,
  baselineName,
  onClose,
}: {
  baselineId: number;
  baselineName: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<DiffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hideUnchanged, setHideUnchanged] = useState(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let live = true;
    api
      .get<DiffResponse>(`/baselines/${baselineId}/diff`)
      .then((d) => live && setData(d))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [baselineId]);

  const rows = data?.rows ?? [];
  const shown = hideUnchanged ? rows.filter((r) => r.status !== "unchanged") : rows;

  function renderCell(r: DiffRow, col: string) {
    const isKey = data?.key_columns.includes(col);
    if (r.status === "added") {
      return <span className="mono">{cellText(r.current?.[col])}</span>;
    }
    if (r.status === "removed") {
      return <span className="mono">{cellText(r.baseline?.[col])}</span>;
    }
    // changed / unchanged → current value, with baseline shown when this cell differs
    const cur = cellText(r.current?.[col]);
    const base = cellText(r.baseline?.[col]);
    const differs = r.changed_columns.includes(col);
    if (differs) {
      return (
        <span className="bd-cellchange">
          <span className="bd-old">{base || "∅"}</span>
          <span className="bd-arrow">→</span>
          <span className="mono bd-new">{cur || "∅"}</span>
        </span>
      );
    }
    return <span className={"mono" + (isKey ? " bd-key" : "")}>{cur}</span>;
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal bd-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">Compare with baseline “{baselineName}”</div>

        {error ? (
          <div className="mm-empty" style={{ color: "var(--red)" }}>
            {error}
          </div>
        ) : !data ? (
          <div className="mm-empty">
            <span className="spin" />
            &nbsp;Computing diff…
          </div>
        ) : (
          <>
            <div className="bd-toolbar">
              <span className="bd-stat bd-added">+{data.summary.added} added</span>
              <span className="bd-stat bd-removed">−{data.summary.removed} removed</span>
              <span className="bd-stat bd-changed">~{data.summary.changed} changed</span>
              <span className="bd-stat bd-dim">{data.summary.unchanged} unchanged</span>
              <div className="spacer" />
              <label className="rm-check">
                <input
                  type="checkbox"
                  checked={hideUnchanged}
                  onChange={(e) => setHideUnchanged(e.target.checked)}
                />
                Hide unchanged
              </label>
            </div>

            <div className="bd-body">
              {shown.length === 0 ? (
                <div className="mm-empty">No differences — the table matches the baseline.</div>
              ) : (
                <table className="ptable bd-table">
                  <thead>
                    <tr>
                      <th className="bd-status-col">Change</th>
                      {data.columns.map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r, i) => (
                      <tr key={i} className={`bd-row bd-${r.status}`}>
                        <td className="bd-status-col">{STATUS_LABEL[r.status]}</td>
                        {data.columns.map((c) => (
                          <td key={c}>{renderCell(r, c)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        <div className="mm-foot">
          <div className="spacer" />
          <button className="primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
