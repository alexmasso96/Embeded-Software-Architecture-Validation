import type { ProjectStatus } from "../api/types";

export function StatusBar({
  status,
  modelName,
  modelStatus,
  rowCount,
  reviewedCount,
}: {
  status: ProjectStatus;
  modelName: string | null;
  modelStatus: string | null;
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
      <span className="right">
        <span>
          {status.active_release ?? "—"}
          {modelName
            ? ` · Model: ${modelName}${modelStatus ? ` (${modelStatus})` : ""}`
            : ""}
        </span>
        <span>
          {rowCount} ports · {reviewedCount} reviewed
        </span>
      </span>
    </div>
  );
}
