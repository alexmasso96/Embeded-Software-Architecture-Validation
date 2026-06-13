import type { ProjectStatus } from "../api/types";

export function StatusBar({
  status,
  modelName,
  rowCount,
  reviewedCount,
}: {
  status: ProjectStatus;
  modelName: string | null;
  rowCount: number;
  reviewedCount: number;
}) {
  let lockClass = "lock";
  let lockText = "🔒 Exclusive Edit";
  if (status.lock_lost) {
    lockClass = "lock lost";
    lockText = "⚠ Lock lost — view only";
  } else if (status.mode === "view") {
    lockClass = "lock viewonly";
    lockText = "👁 View Only";
  }

  return (
    <div className="statusbar">
      <span className={lockClass}>{lockText}</span>
      {status.integrity_mismatch && (
        <span style={{ color: "var(--red)" }}>⚠ Integrity mismatch</span>
      )}
      <span className="right">
        <span>
          {status.active_release ?? "—"}
          {modelName ? ` · ${modelName}` : ""}
        </span>
        <span>
          {rowCount} ports · {reviewedCount} reviewed
        </span>
      </span>
    </div>
  );
}
