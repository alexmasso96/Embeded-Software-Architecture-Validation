import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useSSE } from "../api/useSSE";
import type {
  ChangelogResponse,
  CompareRelease,
  DiffLineKind,
  FileDiffResponse,
  ModelsResponse,
  ReleasesResponse,
} from "../api/types";

type LoadState = "loading" | "ready" | "error";

// ---------------------------------------------------------------------------
// Minimal Markdown → HTML. The AI change log is a small, trusted document, but
// we still escape first so arbitrary text can't inject markup, then layer a few
// inline/block rules on top (headings, bold/italic, inline code, bullet lists).
// ---------------------------------------------------------------------------
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderInline(s: string): string {
  return escapeHtml(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
}

function renderMarkdown(md: string): string {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let inList = false;
  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
    } else if (bullet) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${renderInline(bullet[1])}</li>`);
    } else if (line.trim() === "") {
      closeList();
    } else {
      closeList();
      html.push(`<p>${renderInline(line)}</p>`);
    }
  }
  closeList();
  return html.join("\n");
}

// status → badge letter + class
const STATUS_BADGE: Record<string, { letter: string; cls: string }> = {
  modified: { letter: "M", cls: "modified" },
  added: { letter: "A", cls: "added" },
  deleted: { letter: "D", cls: "deleted" },
};

function badgeFor(status: string): { letter: string; cls: string } {
  return STATUS_BADGE[status] ?? { letter: "?", cls: "modified" };
}

// ---------------------------------------------------------------------------
// Side-by-side diff with synchronized vertical scrolling. Both aligned columns
// always have the same row count, so syncing scrollTop keeps them lined up. A
// lock flag avoids the programmatic-scroll feedback loop.
// ---------------------------------------------------------------------------
function DiffColumns({ diff }: { diff: FileDiffResponse }) {
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const syncing = useRef(false);

  const sync = (from: "left" | "right") => () => {
    if (syncing.current) {
      syncing.current = false;
      return;
    }
    const src = from === "left" ? leftRef.current : rightRef.current;
    const dst = from === "left" ? rightRef.current : leftRef.current;
    if (src && dst && dst.scrollTop !== src.scrollTop) {
      syncing.current = true;
      dst.scrollTop = src.scrollTop;
    }
  };

  const column = (
    side: { 0: string; 1: DiffLineKind }[],
    ref: React.RefObject<HTMLDivElement>,
    onScroll: () => void,
  ) => (
    <div className="cl-diff-col" ref={ref} onScroll={onScroll}>
      {side.map((ln, i) => (
        <div key={i} className={`cl-diff-line ${ln[1]}`}>
          {ln[0] === "" ? " " : ln[0]}
        </div>
      ))}
    </div>
  );

  return (
    <div className="cl-diff-container">
      {column(diff.old, leftRef, sync("left"))}
      {column(diff.new, rightRef, sync("right"))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Change Log view.
// ---------------------------------------------------------------------------
export function ChangeLog({ toast }: { toast: (msg: string) => void }) {
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ChangelogResponse | null>(null);

  const [search, setSearch] = useState("");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [diff, setDiff] = useState<FileDiffResponse | null>(null);
  const [aiOpen, setAiOpen] = useState(true);

  // Compute-diff placeholder state.
  const [releases, setReleases] = useState<ReleasesResponse | null>(null);
  const [activeReleaseId, setActiveReleaseId] = useState<number | null>(null);
  const [selectedReleaseId, setSelectedReleaseId] = useState<number | null>(null);
  const [computing, setComputing] = useState(false);

  const refreshAll = useCallback(async () => {
    setState("loading");
    try {
      const models = await api.get<ModelsResponse>("/models");
      const mid = models.active_model_id;
      if (mid == null) {
        setError("No active architecture model.");
        setState("error");
        return;
      }
      const cl = await api.get<ChangelogResponse>(
        `/changelog?model_id=${mid}`,
      );
      setData(cl);
      // Keep the current file selection if it still exists, else pick the first.
      setSelectedFile((prev) =>
        prev && cl.files.some((f) => f.file_path === prev)
          ? prev
          : (cl.files[0]?.file_path ?? null),
      );
      setState("ready");
    } catch (e) {
      setError((e as Error).message);
      setState("error");
    }
  }, []);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // Load releases for the compute-diff dropdown only when no diff exists yet.
  useEffect(() => {
    if (state !== "ready" || (data && data.diff_hash)) return;
    let alive = true;
    (async () => {
      try {
        const [rels, cmp] = await Promise.all([
          api.get<ReleasesResponse>("/releases"),
          api.get<CompareRelease>("/releases/compare"),
        ]);
        if (!alive) return;
        setReleases(rels);
        setActiveReleaseId(rels.active_release_id);
        // Use the shared "previous release" selection (defaults to the lineage
        // parent) so the Change Log and AI Generation stay in sync.
        const others = rels.releases.filter(
          (r) => r.id !== rels.active_release_id && r.selectable !== false,
        );
        setSelectedReleaseId(
          cmp.previous_release_id ??
            cmp.default_previous_release_id ??
            others[0]?.id ??
            null,
        );
      } catch (e) {
        if (alive) toast(`Change Log: ${(e as Error).message}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [state, data, toast]);

  // Fetch the selected file's aligned diff.
  useEffect(() => {
    if (state !== "ready" || !data?.diff_hash || !selectedFile) {
      setDiff(null);
      return;
    }
    let alive = true;
    (async () => {
      try {
        const d = await api.get<FileDiffResponse>(
          `/changelog/diff?file=${encodeURIComponent(selectedFile)}&model_id=${data.model_id}`,
        );
        if (alive) setDiff(d);
      } catch (e) {
        if (alive) toast(`Change Log: ${(e as Error).message}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [state, data, selectedFile, toast]);

  // Reload once the release_diff job finishes.
  useSSE(
    useCallback(
      (e) => {
        if (e.event !== "job" || e.data?.kind !== "release_diff") return;
        const st = e.data.status;
        if (st === "done") {
          setComputing(false);
          refreshAll();
        } else if (st === "failed" || st === "cancelled") {
          setComputing(false);
        }
      },
      [refreshAll],
    ),
  );

  async function computeDiff() {
    if (activeReleaseId == null || selectedReleaseId == null) return;
    try {
      await api.post("/jobs/release_diff", {
        current_release_id: activeReleaseId,
        previous_release_id: selectedReleaseId,
      });
      setComputing(true);
      toast("Computing release diff…");
    } catch (e) {
      toast(`Compute failed to start: ${(e as Error).message}`);
    }
  }

  const filteredFiles = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return q
      ? data.files.filter((f) => f.file_path.toLowerCase().includes(q))
      : data.files;
  }, [data, search]);

  const aiHtml = useMemo(
    () => (data?.ai_change_log ? renderMarkdown(data.ai_change_log) : ""),
    [data],
  );

  // ---- Render branches -----------------------------------------------------
  if (state === "loading") {
    return (
      <div className="center-msg">
        <span className="spin" /> Loading Change Log…
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="center-msg" style={{ color: "var(--red)" }}>
        Failed to load Change Log: {error}
      </div>
    );
  }

  // No diffs yet — placeholder + compute workflow.
  if (!data?.diff_hash) {
    const others =
      releases?.releases.filter(
        (r) => r.id !== activeReleaseId && r.selectable !== false,
      ) ?? [];
    return (
      <div className="cm-empty">
        <div className="cm-empty-card">
          <div className="cm-empty-title">
            No release diffs computed for this model.
          </div>
          <p className="cm-empty-sub">
            Pick a previous release to compare against the active release, then
            compute the side-by-side diff and AI change log.
          </p>
          <div className="cl-compute-row">
            <select
              className="cl-release-select"
              value={selectedReleaseId ?? ""}
              disabled={computing || others.length === 0}
              onChange={(e) => {
                const id = e.target.value === "" ? null : Number(e.target.value);
                setSelectedReleaseId(id);
                // Persist so AI Generation prefills the same previous release.
                api
                  .put("/releases/compare", { previous_release_id: id })
                  .catch(() => {});
              }}
            >
              {others.length === 0 ? (
                <option value="">No other releases</option>
              ) : (
                others.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))
              )}
            </select>
            <button
              className="save-btn"
              disabled={
                computing || selectedReleaseId == null || activeReleaseId == null
              }
              onClick={computeDiff}
            >
              {computing ? "Computing…" : "Compute Release Diff"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Diff exists — split interface.
  return (
    <div className="changelog-view">
      <aside className="cl-sidebar">
        <div className="cm-search">
          <input
            type="text"
            placeholder={`Search ${data.files.length} files…`}
            spellCheck={false}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="cl-filelist">
          {filteredFiles.length === 0 ? (
            <div className="cm-det-empty">No matches</div>
          ) : (
            filteredFiles.map((f) => {
              const b = badgeFor(f.status);
              return (
                <button
                  key={f.file_path}
                  className={
                    "cl-file" + (f.file_path === selectedFile ? " sel" : "")
                  }
                  title={f.file_path}
                  onClick={() => setSelectedFile(f.file_path)}
                >
                  <span className={"cl-badge " + b.cls} title={f.status}>
                    {b.letter}
                  </span>
                  <span className="cl-file-name">
                    {f.file_path.split(/[\\/]/).pop()}
                  </span>
                </button>
              );
            })
          )}
        </div>
      </aside>

      <div className="cl-workspace">
        <div className="cl-diff-pane">
          <div className="cm-panel-head">
            {selectedFile ? (
              <>
                {selectedFile.split(/[\\/]/).pop()}
                <span className="cm-panel-sub">{selectedFile}</span>
              </>
            ) : (
              "Select a file"
            )}
          </div>
          {diff ? (
            <DiffColumns diff={diff} />
          ) : (
            <div className="center-msg">
              {selectedFile ? (
                <>
                  <span className="spin" /> Loading diff…
                </>
              ) : (
                "Select a file to view its diff."
              )}
            </div>
          )}
        </div>

        <div className={"cl-ai-panel" + (aiOpen ? "" : " collapsed")}>
          <button
            className="cl-ai-head"
            onClick={() => setAiOpen((v) => !v)}
            title={aiOpen ? "Collapse" : "Expand"}
          >
            <span className="cl-ai-caret">{aiOpen ? "▾" : "▸"}</span>
            AI Summary
          </button>
          {aiOpen &&
            (aiHtml ? (
              <div
                className="cl-ai-body"
                dangerouslySetInnerHTML={{ __html: aiHtml }}
              />
            ) : (
              <div className="cm-det-empty">No AI change log available.</div>
            ))}
        </div>
      </div>
    </div>
  );
}
