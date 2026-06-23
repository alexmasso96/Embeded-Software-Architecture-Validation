import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  AIPrompts,
  AIProvider,
  CompareRelease,
  HltParseResult,
  JobPayload,
  MindmapStatus,
  ProvidersResponse,
  ReleasesResponse,
} from "../api/types";
import { useSSE } from "../api/useSSE";
import { FolderPicker } from "../components/FolderPicker";

function modelLabel(m: { id: string; name?: string }): string {
  return m.name || m.id;
}

// ---------------------------------------------------------------------------
// AI Generation view — left pane: editable generation prompt/rules + the code
// mind-map builder; right pane: pick an HLT design file, choose test cases, and
// run the generate_tests job with a live progress terminal. The "previous
// release" selector is shared with the Change Log (defaults to the lineage
// parent) and feeds the mind-map diff.
// ---------------------------------------------------------------------------
export function AIGeneration({ toast }: { toast: (msg: string) => void }) {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [providerId, setProviderId] = useState("");
  const [model, setModel] = useState("");

  // Editable prompt + rules (persisted in the project DB via /api/ai/prompts).
  const [prompt, setPrompt] = useState("");
  const [rules, setRules] = useState("");
  const [promptsDirty, setPromptsDirty] = useState(false);
  const [savingPrompts, setSavingPrompts] = useState(false);

  // Releases + the shared compare/previous-release selection.
  const [releases, setReleases] = useState<ReleasesResponse | null>(null);
  const [prevReleaseId, setPrevReleaseId] = useState<number | null>(null);

  // Mind-map status + build job.
  const [mindmap, setMindmap] = useState<MindmapStatus | null>(null);
  const [mmJobId, setMmJobId] = useState<string | null>(null);
  const [mmBuilding, setMmBuilding] = useState(false);
  const [mmMsg, setMmMsg] = useState<string>("");

  // HLT file + checklist.
  const [pickerOpen, setPickerOpen] = useState(false);
  const [hltPath, setHltPath] = useState<string | null>(null);
  const [parsed, setParsed] = useState<HltParseResult | null>(null);
  const [parsing, setParsing] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Generation job.
  const [genJobId, setGenJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);

  const provider = providers.find((p) => p.id === providerId) ?? null;

  // ---- Initial load -------------------------------------------------------
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [pr, pmpts, rel, cmp, mm] = await Promise.all([
          api.get<ProvidersResponse>("/ai/providers"),
          api.get<AIPrompts>("/ai/prompts"),
          api.get<ReleasesResponse>("/releases"),
          api.get<CompareRelease>("/releases/compare"),
          api.get<MindmapStatus>("/ai/mindmap"),
        ]);
        if (!alive) return;
        setProviders(pr.providers);
        const def = pr.providers.find((p) => p.configured) ?? pr.providers[0] ?? null;
        if (def) {
          setProviderId(def.id);
          setModel(def.models[0]?.id ?? "");
        }
        setPrompt(pmpts.prompt);
        setRules(pmpts.rules);
        setReleases(rel);
        setPrevReleaseId(cmp.previous_release_id ?? cmp.default_previous_release_id);
        setMindmap(mm);
      } catch (e) {
        if (alive) toast(`AI Generation: ${(e as Error).message}`);
      }
    })();
    return () => {
      alive = false;
    };
  }, [toast]);

  useEffect(() => {
    if (!provider) return;
    if (!provider.models.some((m) => m.id === model)) {
      setModel(provider.models[0]?.id ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId]);

  const refreshMindmap = useCallback(async () => {
    try {
      setMindmap(await api.get<MindmapStatus>("/ai/mindmap"));
    } catch {
      /* leave previous */
    }
  }, []);

  // ---- Prompts save -------------------------------------------------------
  async function savePrompts() {
    setSavingPrompts(true);
    try {
      await api.put<AIPrompts>("/ai/prompts", { prompt, rules });
      setPromptsDirty(false);
      toast("Prompt & rules saved.");
    } catch (e) {
      toast(`Save failed: ${(e as Error).message}`);
    } finally {
      setSavingPrompts(false);
    }
  }

  // ---- Previous release (shared with Change Log) --------------------------
  async function changePrevRelease(id: number | null) {
    setPrevReleaseId(id);
    try {
      await api.put("/releases/compare", { previous_release_id: id });
    } catch (e) {
      toast(`Could not save previous release: ${(e as Error).message}`);
    }
  }

  // ---- Mind map build -----------------------------------------------------
  async function buildMindmap() {
    setMmBuilding(true);
    setMmMsg("Starting mind-map build…");
    try {
      const job = await api.post<JobPayload>("/jobs/build_mind_map", {
        previous_release_id: prevReleaseId,
      });
      setMmJobId(job.job_id);
    } catch (e) {
      setMmBuilding(false);
      setMmMsg("");
      toast(`Mind map failed to start: ${(e as Error).message}`);
    }
  }

  // ---- HLT parse ----------------------------------------------------------
  const parseHlt = useCallback(
    async (path: string) => {
      setParsing(true);
      setParsed(null);
      setSelected(new Set());
      try {
        const r = await api.post<HltParseResult>("/ai/parse-hlt", { file_path: path });
        setParsed(r);
        setSelected(new Set(r.test_cases.map((tc) => tc.id)));
      } catch (e) {
        toast(`Parse HLT: ${(e as Error).message}`);
      } finally {
        setParsing(false);
      }
    },
    [toast],
  );

  function onPicked(path: string) {
    setPickerOpen(false);
    setHltPath(path);
    parseHlt(path);
  }

  const allSelected =
    parsed != null &&
    parsed.test_cases.length > 0 &&
    selected.size === parsed.test_cases.length;

  function toggleAll() {
    if (!parsed) return;
    setSelected(allSelected ? new Set() : new Set(parsed.test_cases.map((tc) => tc.id)));
  }
  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  // ---- Job SSE (both mind-map build and test generation) ------------------
  useSSE(
    useCallback(
      (e) => {
        if (e.event === "db-changed") {
          refreshMindmap();
          return;
        }
        if (e.event !== "job") return;
        const job = e.data as unknown as JobPayload;
        if (job.kind === "build_mind_map" && job.job_id === mmJobId) {
          if (job.message) setMmMsg(job.message);
          if (job.status === "done") {
            setMmBuilding(false);
            setMmMsg("✓ Mind map built.");
            refreshMindmap();
            toast("Code mind map built.");
          } else if (job.status === "failed") {
            setMmBuilding(false);
            setMmMsg(`✗ ${job.error || "Mind-map build failed."}`);
          } else if (job.status === "cancelled") {
            setMmBuilding(false);
            setMmMsg("■ Cancelled.");
          }
        } else if (job.kind === "generate_tests" && job.job_id === genJobId) {
          if (job.message) {
            setLog((prev) =>
              prev[prev.length - 1] === job.message ? prev : [...prev, job.message],
            );
          }
          if (job.status === "done") {
            setRunning(false);
            setLog((prev) => [...prev, "✓ Generation complete."]);
            toast("Low-level tests generated.");
          } else if (job.status === "failed") {
            setRunning(false);
            setLog((prev) => [...prev, `✗ ${job.error || "Generation failed."}`]);
          } else if (job.status === "cancelled") {
            setRunning(false);
            setLog((prev) => [...prev, "■ Cancelled."]);
          }
        }
      },
      [mmJobId, genJobId, refreshMindmap, toast],
    ),
  );

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ block: "end" });
  }, [log]);

  // ---- Generation ---------------------------------------------------------
  async function generate() {
    if (!providerId || !model || !hltPath) return;
    setRunning(true);
    setLog(["Starting generation…"]);
    try {
      const job = await api.post<JobPayload>("/jobs/generate_tests", {
        provider_id: providerId,
        model,
        hlt_path: hltPath,
        test_case_ids: Array.from(selected),
        previous_release_id: prevReleaseId,
      });
      setGenJobId(job.job_id);
    } catch (e) {
      setRunning(false);
      setLog((prev) => [...prev, `✗ ${(e as Error).message}`]);
      toast(`Could not start generation: ${(e as Error).message}`);
    }
  }
  async function cancelGen() {
    if (!genJobId) return;
    try {
      await api.post(`/jobs/${genJobId}/cancel`);
    } catch (e) {
      toast(`Cancel failed: ${(e as Error).message}`);
    }
  }

  const canGenerate = !!providerId && !!model && !!hltPath && selected.size > 0 && !running;
  const hltName = hltPath?.split(/[\\/]/).pop() ?? null;
  const selectableReleases =
    releases?.releases.filter((r) => r.selectable !== false) ?? [];
  const mmUpdated = mindmap?.meta?.updated_at?.replace("T", " ").slice(0, 16) ?? null;

  return (
    <div className="aig-view">
      {/* Config bar */}
      <div className="aig-config">
        <label className="aig-field">
          <span>Provider</span>
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
                {p.configured ? "" : " (not configured)"}
              </option>
            ))}
          </select>
        </label>
        <label className="aig-field">
          <span>Model</span>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={!provider || provider.models.length === 0}
          >
            {provider?.models.length ? (
              provider.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {modelLabel(m)}
                </option>
              ))
            ) : (
              <option value="">No models</option>
            )}
          </select>
        </label>
        <label className="aig-field">
          <span>Previous release (diff base)</span>
          <select
            value={prevReleaseId ?? ""}
            onChange={(e) =>
              changePrevRelease(e.target.value === "" ? null : Number(e.target.value))
            }
          >
            <option value="">— none —</option>
            {selectableReleases.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
                {r.is_active ? " (current)" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      {provider && !provider.configured && (
        <div className="banner warn">
          ⚠ {provider.label} is not configured. Link a key in Preferences → AI
          Settings before generating.
        </div>
      )}

      <div className="aig-split">
        {/* Left: prompts + mind map */}
        <div className="aig-side">
          <div className="aig-side-sec">
            <div className="aig-side-head">
              <span>Generation Prompt</span>
              <button
                className="save-btn sm"
                disabled={!promptsDirty || savingPrompts}
                onClick={savePrompts}
              >
                {savingPrompts ? "Saving…" : promptsDirty ? "Save" : "Saved"}
              </button>
            </div>
            <textarea
              className="aig-prompt-area"
              spellCheck={false}
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
                setPromptsDirty(true);
              }}
              rows={6}
            />
            <div className="aig-side-sub">Rules</div>
            <textarea
              className="aig-prompt-area rules"
              spellCheck={false}
              value={rules}
              onChange={(e) => {
                setRules(e.target.value);
                setPromptsDirty(true);
              }}
              rows={8}
            />
          </div>

          <div className="aig-side-sec">
            <div className="aig-side-head">
              <span>Code Mind Map</span>
            </div>
            <div className="aig-mm-status">
              <span className={"aig-dot " + (mindmap?.has_mindmap ? "ok" : "off")} />
              {mindmap?.has_mindmap
                ? `Available${mmUpdated ? ` · built ${mmUpdated}` : ""}`
                : "Not built for this model/release"}
            </div>
            <div className="aig-mm-status">
              <span className={"aig-dot " + (mindmap?.has_source ? "ok" : "off")} />
              {mindmap?.has_source ? "Source imported" : "No source imported"}
            </div>
            <button
              className="scope-btn"
              disabled={mmBuilding || !mindmap?.has_source}
              onClick={buildMindmap}
              title={
                mindmap?.has_source
                  ? undefined
                  : "Import source for the active release first (Release Manager)."
              }
            >
              {mmBuilding
                ? "Building…"
                : mindmap?.has_mindmap
                  ? "Regenerate Mind Map"
                  : "Generate Mind Map"}
            </button>
            {mmMsg && <div className="aig-mm-msg">{mmMsg}</div>}
          </div>
        </div>

        {/* Right: HLT checklist + generation */}
        <div className="aig-main">
          <div className="aig-panel-head">
            <span>Test Cases</span>
            <button className="scope-btn sm" onClick={() => setPickerOpen(true)}>
              {hltName ? `📄 ${hltName}` : "Choose HLT .md…"}
            </button>
            {parsed && parsed.test_cases.length > 0 && (
              <label className="aig-selall">
                <input type="checkbox" checked={allSelected} onChange={toggleAll} />
                Select All
              </label>
            )}
          </div>
          <div className="aig-checklist-body">
            {parsing ? (
              <div className="center-msg">
                <span className="spin" /> Parsing HLT…
              </div>
            ) : !parsed ? (
              <div className="td-preview-empty">
                Choose an HLT design file to list its test cases.
              </div>
            ) : parsed.test_cases.length === 0 ? (
              <div className="td-preview-empty">No test cases found in this file.</div>
            ) : (
              <>
                <div className="aig-model-name">
                  Model: <strong>{parsed.model_name}</strong>
                </div>
                {parsed.test_cases.map((tc) => (
                  <label
                    key={tc.id}
                    className={"aig-tc" + (selected.has(tc.id) ? " sel" : "")}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(tc.id)}
                      onChange={() => toggleOne(tc.id)}
                    />
                    <span className="aig-tc-title">{tc.title}</span>
                    {tc.has_lowlevel && (
                      <span className="aig-tc-badge" title="Already has low-level tests">
                        ✓ LL
                      </span>
                    )}
                  </label>
                ))}
              </>
            )}
          </div>
          <div className="aig-actions">
            <span className="aig-count">
              {parsed ? `${selected.size} of ${parsed.test_cases.length} selected` : ""}
            </span>
            <div className="spacer" />
            {running && (
              <button className="scope-btn" onClick={cancelGen}>
                Cancel
              </button>
            )}
            <button className="save-btn" disabled={!canGenerate} onClick={generate}>
              {running ? "Generating…" : "Generate Low-Level Tests"}
            </button>
          </div>
          <div className="aig-terminal">
            {log.length === 0 ? (
              <div className="aig-terminal-empty">
                Generation progress will stream here.
              </div>
            ) : (
              log.map((line, i) => (
                <div className="aig-term-line" key={i}>
                  {line}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>

      {pickerOpen && (
        <FolderPicker
          mode="import"
          exts={[".md"]}
          title="Choose an HLT design (.md) file"
          hint="Select a *_Test_Case_Design.md file"
          onCancel={() => setPickerOpen(false)}
          onConfirm={(path) => onPicked(path)}
        />
      )}
    </div>
  );
}
