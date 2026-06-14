import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { ColumnSpec } from "../api/types";
import { SEARCH_KEYS } from "../columns";
import { FolderPicker } from "./FolderPicker";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const DONT = "__ignore"; // sentinel: do not import this column
const CREATE = "__create"; // sentinel: create a new column named after the source

interface AnalyzeResult {
  format: "excel" | "rhapsody" | "csv";
  sheets?: string[];
  columns?: string[];
  path_col?: string;
  required_col?: string | null;
  ops_col?: string | null;
  models?: { name: string; port_count: number }[];
}
interface ReadResult {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  is_rhapsody: boolean;
  path_col: string | null;
}

type Step =
  | { k: "pick" }
  | { k: "analyzing" }
  // New ELF/JSON = a new software version → offer to baseline the current one first.
  | { k: "elf_baseline"; file: string; name: string }
  | { k: "release"; file: string; name: string }
  | { k: "mapping"; file: string }
  | { k: "running"; msg: string }
  | { k: "done"; msg: string };

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

// The single import entry (plan §3.3, "no menu items" — one button does it all):
//   • .elf / .json  → a NEW software version: baseline the current ELF/table first
//     (only when a release already exists), then import symbols into a new release.
//   • .xlsx/.xls/.csv → port import: column-mapping → bulk + rematch (no baseline —
//     adding ports to the current version isn't a version bump).
export function ImportWizard({
  activeModelId,
  activeModelName,
  currentRelease,
  columns,
  onChanged,
  onClose,
}: {
  activeModelId: number | null;
  activeModelName: string | null;
  currentRelease: string | null;
  columns: ColumnSpec[];
  onChanged: () => void;
  onClose: () => void;
}) {
  const [step, setStep] = useState<Step>({ k: "pick" });
  const [err, setErr] = useState<string | null>(null);

  // Excel state (kept across baseline → mapping steps)
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [read, setRead] = useState<ReadResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [baselineName, setBaselineName] = useState("");

  const isRhapsody = analysis?.format === "rhapsody";
  const pathCol = analysis?.path_col ?? null;
  const funcCol = columns.find((c) => c.type === "Function Search")?.name ?? null;

  const destCols = columns.map((c) => c.name);
  const searchCol = columns.find((c) => SEARCH_KEYS.includes(c.type))?.name ?? null;

  // ---- entry: file chosen ----
  async function onFile(path: string) {
    setErr(null);
    const lower = path.toLowerCase();
    if (lower.endsWith(".elf") || lower.endsWith(".json")) {
      // A new ELF is a new software version. If a release (ELF) already exists,
      // offer to baseline the current table+ELF first; otherwise go straight to
      // naming the release (first/onboarding import — nothing to baseline yet).
      const base = path.split(/[\\/]/).pop() ?? "release";
      const name = base.replace(/\.(elf|json)$/i, "");
      if (currentRelease) {
        // Pre-fill a valid baseline name so Create Baseline is active immediately.
        // The snapshot is mandatory (ASPICE) — there is no skip.
        setBaselineName(`${currentRelease} (baseline)`);
        setStep({ k: "elf_baseline", file: path, name });
      } else {
        setStep({ k: "release", file: path, name });
      }
      return;
    }
    // tabular → analyze (detects Rhapsody multi-model), then straight to mapping.
    setStep({ k: "analyzing" });
    try {
      const a = await api.post<AnalyzeResult>("/import/analyze", { file_path: path });
      setAnalysis(a);
      await gotoMapping(path, a);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setStep({ k: "pick" });
    }
  }

  // ---- ELF/JSON: create release + import symbols ----
  async function runReleaseImport(file: string, name: string) {
    setStep({ k: "running", msg: "Creating release…" });
    setErr(null);
    try {
      const rel = await api.post<{ id: number }>("/releases", { name });
      await api.post(`/releases/${rel.id}/activate`);
      setStep({ k: "running", msg: "Importing symbols…" });
      const started = await api.post<{ job_id: string }>("/jobs/import_symbols", {
        file_path: file,
        release_id: rel.id,
      });
      for (;;) {
        await sleep(250);
        const j = await api.get<{ status: string; error?: string }>(`/jobs/${started.job_id}`);
        if (j.status === "done") break;
        if (j.status === "failed" || j.status === "cancelled")
          throw new Error(j.error || "Import failed.");
      }
      onChanged();
      setStep({ k: "done", msg: `Release “${name}” imported. Re-match symbols to apply it.` });
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setStep({ k: "release", file, name });
    }
  }

  // ---- read rows + auto-map → mapping step ----
  async function gotoMapping(file: string, a: AnalyzeResult | null) {
    setStep({ k: "analyzing" });
    setErr(null);
    try {
      const r = await api.post<ReadResult>("/import/read", { file_path: file });
      setRead(r);
      // auto-map: exact name match; "Port Name"-like → Port Search col;
      // Rhapsody "Operations" → the Function Search col (operations are functions).
      const aPathCol = a?.path_col ?? null;
      const opsCol = a?.ops_col ?? null;
      const m: Record<string, string> = {};
      for (const src of r.columns) {
        if (src === aPathCol) continue; // path column drives the model split — not mappable
        const exact = destCols.find((d) => norm(d) === norm(src));
        if (exact) m[src] = exact;
        else if (opsCol && src === opsCol && funcCol) m[src] = funcCol;
        else if (searchCol && norm(src).includes("portname")) m[src] = searchCol;
        else m[src] = DONT;
      }
      setMapping(m);
      setStep({ k: "mapping", file });
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setStep({ k: "pick" });
    }
  }

  // ---- ELF baseline step: snapshot the current release+table, then name the new release ----
  async function createBaselineThenRelease(file: string, name: string) {
    const bname = baselineName.trim();
    if (!bname) return;
    setStep({ k: "running", msg: "Baselining current version…" });
    setErr(null);
    try {
      await api.post("/baselines", { name: bname });
      onChanged();
      setStep({ k: "release", file, name });
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setStep({ k: "elf_baseline", file, name });
    }
  }

  // ---- mapping → import (Rhapsody multi-model split, or plain single-model) ----
  async function runPortImport(file: string) {
    if (!read) return;
    const used = Object.entries(mapping).filter(([, d]) => d && d !== DONT);
    if (used.length === 0) {
      setErr("Map at least one column before importing.");
      return;
    }
    setErr(null);
    try {
      // Auto-create any columns the user mapped to "➕ Create new column".
      // New columns are Static Text named after the source (uniquified), appended
      // to the layout (PUT /columns) so the bulk/rhapsody insert can target them.
      const existing = new Set(columns.map((c) => c.name));
      const newCols: ColumnSpec[] = [];
      const effective: Record<string, string> = {};
      for (const [src, dest] of used) {
        if (dest === CREATE) {
          let cn = src;
          let n = 1;
          while (existing.has(cn)) cn = `${src} (${n++})`;
          existing.add(cn);
          newCols.push({ name: cn, type: "Static Text", visible: true, width: 140 });
          effective[src] = cn;
        } else {
          effective[src] = dest;
        }
      }
      if (newCols.length) {
        setStep({ k: "running", msg: `Creating ${newCols.length} column(s)…` });
        await api.put("/columns", { columns: [...columns, ...newCols] });
      }
      const usedEff = Object.entries(effective);

      if (isRhapsody && pathCol) {
        // Server-side split: each package → its own model (create/append).
        setStep({ k: "running", msg: "Splitting packages into models…" });
        const colMapping = Object.fromEntries(usedEff);
        const r = await api.post<{ total_models: number; total_added: number; model_ids: number[] }>(
          "/import/rhapsody",
          {
            file_path: file,
            col_mapping: colMapping,
            path_col: pathCol,
            ops_col: analysis?.ops_col ?? null,
            required_col: analysis?.required_col ?? null,
          },
        );
        if (r.model_ids.length) {
          setStep({ k: "running", msg: `Re-matching ${r.model_ids.length} models…` });
          await api.post("/jobs/fuzzy_rematch", { model_ids: r.model_ids });
        }
        onChanged();
        setStep({
          k: "done",
          msg: `Imported ${r.total_added} rows across ${r.total_models} models.`,
        });
        return;
      }

      // Plain Excel/CSV → bulk into the active model.
      if (activeModelId === null) {
        setErr("No active model to import into.");
        return;
      }
      setStep({ k: "running", msg: `Importing ${read.total} rows…` });
      const rows = read.rows.map((srcRow) => {
        const out: Record<string, string> = {};
        for (const [src, dest] of usedEff) {
          const v = srcRow[src];
          out[dest] = v == null ? "" : String(v);
        }
        return out;
      });
      await api.post(`/models/${activeModelId}/ports/bulk`, { rows });
      setStep({ k: "running", msg: "Re-matching symbols…" });
      await api.post("/jobs/fuzzy_rematch", { model_id: activeModelId });
      onChanged();
      setStep({ k: "done", msg: `Imported ${read.total} rows into “${activeModelName}”.` });
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : String(e));
      setStep({ k: "mapping", file });
    }
  }

  // ===== rendering =====
  if (step.k === "pick") {
    return (
      <FolderPicker
        mode="import"
        exts={[".elf", ".json", ".xlsx", ".xls", ".csv"]}
        title="Import — choose a release (.elf/.json) or ports (.xlsx/.csv)"
        hint="Select an ELF/JSON release or an Excel/CSV port file"
        onCancel={onClose}
        onConfirm={(path) => onFile(path)}
      />
    );
  }

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div className="modal importwiz" onMouseDown={(e) => e.stopPropagation()}>
        <div className="modal-head">Import</div>
        <div className="iw-body">
          {err && <div className="iw-err">{err}</div>}

          {(step.k === "analyzing" || step.k === "running") && (
            <div className="iw-center">
              <span className="spin" />
              &nbsp;{step.k === "running" ? step.msg : "Analyzing file…"}
            </div>
          )}

          {step.k === "release" && (
            <div className="iw-pane">
              <p className="iw-lead">
                Import symbols from <b>{step.file.split(/[\\/]/).pop()}</b> into a new release.
              </p>
              <label className="iw-field">
                Release name
                <input
                  autoFocus
                  value={step.name}
                  onChange={(e) => setStep({ ...step, name: e.target.value })}
                  onKeyDown={(e) =>
                    e.key === "Enter" && step.name.trim() && runReleaseImport(step.file, step.name.trim())
                  }
                />
              </label>
            </div>
          )}

          {step.k === "elf_baseline" && (
            <div className="iw-pane">
              <p className="iw-lead">
                Importing <b>{step.file.split(/[\\/]/).pop()}</b> is a{" "}
                <b>new software version</b>.
              </p>
              <p className="iw-sub">
                A snapshot of the current version (<b>{currentRelease}</b>) is required before
                moving to a new release (ASPICE) — it captures the table as it stands against the
                current ELF so you can compare against it later.
              </p>
              <label className="iw-field">
                Baseline name
                <input
                  autoFocus
                  value={baselineName}
                  onChange={(e) => setBaselineName(e.target.value)}
                  onKeyDown={(e) =>
                    e.key === "Enter" &&
                    baselineName.trim() &&
                    createBaselineThenRelease(step.file, step.name)
                  }
                />
              </label>
            </div>
          )}

          {step.k === "mapping" && read && (
            <div className="iw-pane iw-map">
              <p className="iw-lead">
                {isRhapsody ? (
                  <>
                    Rhapsody export — rows split into{" "}
                    <b>{analysis?.models?.length ?? "?"} models</b> by package.
                  </>
                ) : (
                  <>
                    Map each source column to a table column — <b>{read.total}</b> rows into{" "}
                    <b>{activeModelName}</b>.
                  </>
                )}
              </p>
              <div className="iw-maplist">
                <div className="iw-maprow iw-maphead">
                  <span>Source column</span>
                  <span>→</span>
                  <span>Table column</span>
                  <span className="iw-sample">First value</span>
                </div>
                {isRhapsody && pathCol && (
                  <div className="iw-maprow iw-pathrow">
                    <span className="iw-src">{pathCol}</span>
                    <span className="iw-arrow">→</span>
                    <span className="iw-splittag">Model name (splits packages)</span>
                    <span className="iw-sample" title={String(read.rows[0]?.[pathCol] ?? "")}>
                      {String(read.rows[0]?.[pathCol] ?? "")}
                    </span>
                  </div>
                )}
                {read.columns
                  .filter((src) => src !== pathCol)
                  .map((src) => (
                    <div className="iw-maprow" key={src}>
                      <span className="iw-src">{src}</span>
                      <span className="iw-arrow">→</span>
                      <select
                        value={mapping[src] ?? DONT}
                        onChange={(e) => setMapping((m) => ({ ...m, [src]: e.target.value }))}
                      >
                        <option value={DONT}>— Don’t import —</option>
                        <option value={CREATE}>➕ Create new column “{src}”</option>
                        {destCols.map((d) => (
                          <option key={d} value={d}>
                            {d}
                          </option>
                        ))}
                      </select>
                      <span className="iw-sample" title={String(read.rows[0]?.[src] ?? "")}>
                        {String(read.rows[0]?.[src] ?? "")}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {step.k === "done" && (
            <div className="iw-pane">
              <p className="iw-lead">✓ {step.msg}</p>
            </div>
          )}
        </div>

        <Footer
          step={step}
          baselineName={baselineName}
          canImport={isRhapsody || activeModelId !== null}
          importLabel={isRhapsody ? "Split & Import" : "Import Ports"}
          onCancel={onClose}
          onBackToPick={() => {
            setErr(null);
            setStep({ k: "pick" });
          }}
          onReleaseImport={() =>
            step.k === "release" && runReleaseImport(step.file, step.name.trim())
          }
          onBaselineCreate={() =>
            step.k === "elf_baseline" && createBaselineThenRelease(step.file, step.name)
          }
          onRunImport={() => step.k === "mapping" && runPortImport(step.file)}
        />
      </div>
    </div>
  );
}

function Footer({
  step,
  baselineName,
  canImport,
  importLabel,
  onCancel,
  onBackToPick,
  onReleaseImport,
  onBaselineCreate,
  onRunImport,
}: {
  step: Step;
  baselineName: string;
  canImport: boolean;
  importLabel: string;
  onCancel: () => void;
  onBackToPick: () => void;
  onReleaseImport: () => void;
  onBaselineCreate: () => void;
  onRunImport: () => void;
}) {
  const busy = step.k === "running" || step.k === "analyzing";
  return (
    <div className="iw-foot">
      {(step.k === "release" || step.k === "elf_baseline" || step.k === "mapping") && (
        <button className="scope-btn" onClick={onBackToPick} disabled={busy}>
          ‹ Back
        </button>
      )}
      <div className="spacer" />
      {step.k === "done" ? (
        <button className="save-btn" onClick={onCancel}>
          Done
        </button>
      ) : (
        <>
          <button className="scope-btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          {step.k === "release" && (
            <button
              className="save-btn"
              onClick={onReleaseImport}
              disabled={busy || !(step.name.trim())}
            >
              Import Release
            </button>
          )}
          {step.k === "elf_baseline" && (
            <button
              className="save-btn"
              onClick={onBaselineCreate}
              disabled={busy || !baselineName.trim()}
            >
              Create Baseline & Continue
            </button>
          )}
          {step.k === "mapping" && (
            <button className="save-btn" onClick={onRunImport} disabled={busy || !canImport}>
              {importLabel}
            </button>
          )}
        </>
      )}
    </div>
  );
}
