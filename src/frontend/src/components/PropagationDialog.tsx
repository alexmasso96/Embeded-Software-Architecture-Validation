import { useEffect, useRef, useState } from "react";

// One "In Work" port the backend flagged as eligible to follow a model's status
// change (POST /api/models/{id}/state/preview → affected_ports).
export interface AffectedPort {
  row_index: number;
  port_name: string;
  column: string;
}

// macOS-style confirmation modal for the model-state cascade (#8.2). Instead of
// silently sweeping every "In Work" port along with the model, the user picks
// which ports follow. Selection is tracked by row_index (port names can repeat
// or be blank); on Propagate we map the checked rows back to their port names.
export function PropagationDialog({
  modelName,
  newStatus,
  ports,
  busy,
  onPropagate,
  onCancel,
}: {
  modelName: string;
  newStatus: string;
  ports: AffectedPort[];
  busy: boolean;
  onPropagate: (selectedPortNames: string[]) => void;
  onCancel: () => void;
}) {
  const [checked, setChecked] = useState<Set<number>>(
    () => new Set(ports.map((p) => p.row_index)),
  );
  const allRef = useRef<HTMLInputElement>(null);

  const allChecked = checked.size === ports.length;
  const someChecked = checked.size > 0;

  // Tri-state the "Select all" box when only some ports are picked.
  useEffect(() => {
    if (allRef.current) allRef.current.indeterminate = someChecked && !allChecked;
  }, [someChecked, allChecked]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  function toggle(rowIndex: number) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(rowIndex)) next.delete(rowIndex);
      else next.add(rowIndex);
      return next;
    });
  }

  function toggleAll() {
    setChecked(allChecked ? new Set() : new Set(ports.map((p) => p.row_index)));
  }

  function propagate() {
    const names = ports
      .filter((p) => checked.has(p.row_index))
      .map((p) => p.port_name);
    onPropagate(names);
  }

  return (
    <div className="modal-overlay" onMouseDown={onCancel}>
      <div className="modal propdlg" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">Propagate status to ports</div>

        <div className="pd-intro">
          Setting <b>{modelName}</b> to <b>{newStatus}</b> can update{" "}
          {ports.length} “In Work” port{ports.length === 1 ? "" : "s"}. Choose
          which ports should follow.
        </div>

        <label className="pd-all">
          <input
            ref={allRef}
            type="checkbox"
            checked={allChecked}
            onChange={toggleAll}
          />
          Select all
        </label>

        <div className="pd-list">
          {ports.map((p) => (
            <label key={p.row_index} className="pd-row">
              <input
                type="checkbox"
                checked={checked.has(p.row_index)}
                onChange={() => toggle(p.row_index)}
              />
              <span className="pd-name">
                {p.port_name || `Row ${p.row_index}`}
              </span>
              <span className="pd-col">{p.column}</span>
            </label>
          ))}
        </div>

        <div className="pd-foot">
          <button onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <div className="spacer" />
          <button
            className="primary"
            onClick={propagate}
            disabled={busy || !someChecked}
          >
            {busy ? "Propagating…" : `Propagate (${checked.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}
