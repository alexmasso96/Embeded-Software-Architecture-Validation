import type { JobPayload } from "../api/types";

// Pretty job-kind names; anything not listed falls back to Title Case of the
// underscore-separated kind (e.g. "build_codemap" → "Build Codemap").
const JOB_NAMES: Record<string, string> = {
  fuzzy_rematch: "Fuzzy Re-match",
  import_symbols: "Importing Symbols",
  import_source: "Importing Source",
};

function jobTitle(kind: string): string {
  if (JOB_NAMES[kind]) return JOB_NAMES[kind];
  return kind
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Floating, bottom-right stack of running/finished background jobs (plan §4.x).
// Each card shows a name, the latest progress message, and a determinate or
// indeterminate bar. Running/queued jobs expose a ✕ cancel control.
export function JobProgressOverlay({
  jobs,
  onCancel,
}: {
  jobs: JobPayload[];
  onCancel: (jobId: string) => void;
}) {
  if (jobs.length === 0) return null;

  return (
    <div className="job-overlay-container">
      {jobs.map((job) => {
        const indeterminate = job.progress == null;
        const failed = job.status === "failed";
        const cancellable = job.status === "running" || job.status === "queued";
        const pct = Math.max(0, Math.min(100, job.progress ?? 0));
        return (
          <div className="job-card" key={job.job_id}>
            <div className="job-card-head">
              <span className="job-name">{jobTitle(job.kind)}</span>
              {cancellable && (
                <button
                  className="job-cancel"
                  title="Cancel"
                  aria-label="Cancel job"
                  onClick={() => onCancel(job.job_id)}
                >
                  ✕
                </button>
              )}
            </div>
            <div className={"job-msg" + (failed ? " err" : "")}>
              {failed
                ? job.error || job.message || "Job failed"
                : job.message || "Working…"}
            </div>
            <div className="job-bar">
              <div
                className={
                  "job-bar-fill" +
                  (indeterminate ? " indeterminate" : "") +
                  (failed ? " err" : "")
                }
                style={indeterminate ? undefined : { width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
