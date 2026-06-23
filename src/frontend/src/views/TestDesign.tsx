import Editor, { type OnMount } from "@monaco-editor/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  TestDesignExportResult,
  TestDesignPreview,
  TestDesignSettings,
  TestDesignSuggestions,
} from "../api/types";
import { useSSE } from "../api/useSSE";
import { renderMarkdown } from "../markdown";

type MonacoNs = Parameters<OnMount>[1];

// Only the members the completion provider touches — keeps us off monaco's full
// type surface (it ships its own .d.ts but we use a sliver of it).
interface CompletionModel {
  getValueInRange(range: {
    startLineNumber: number;
    startColumn: number;
    endLineNumber: number;
    endColumn: number;
  }): string;
}
interface CursorPosition {
  lineNumber: number;
  column: number;
}

// Monaco theme follows the app's resolved light/dark (mirrors CodeMap.tsx).
function useMonacoTheme(): "vs" | "vs-dark" {
  const read = (): "vs" | "vs-dark" =>
    document.documentElement.getAttribute("data-theme") === "dark"
      ? "vs-dark"
      : "vs";
  const [theme, setTheme] = useState<"vs" | "vs-dark">(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setTheme(read()));
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);
  return theme;
}

const GROUPINGS: { value: string; label: string }[] = [
  { value: "grouped", label: "Grouped (one test case per port)" },
  { value: "independent", label: "Independent (one per row)" },
];

// ---------------------------------------------------------------------------
// Test Case Design view — split editor / preview (plan §4.x). The left pane
// edits the HLT title + body template (Monaco, with condition autocomplete); the
// right pane renders the live preview for one effective row, paged Port/Row.
// ---------------------------------------------------------------------------
export function TestDesign({ toast }: { toast: (msg: string) => void }) {
  const theme = useMonacoTheme();

  const [title, setTitle] = useState("");
  const [template, setTemplate] = useState("");
  const [grouping, setGrouping] = useState("grouped");
  const [loaded, setLoaded] = useState(false);

  const [rowIndex, setRowIndex] = useState(0);
  const [preview, setPreview] = useState<TestDesignPreview | null>(null);
  const [exporting, setExporting] = useState(false);

  // Latest values, read by the async completion provider + savers without
  // re-registering the provider or re-creating callbacks on every keystroke.
  const titleRef = useRef(title);
  titleRef.current = title;
  const templateRef = useRef(template);
  templateRef.current = template;
  const groupingRef = useRef(grouping);
  groupingRef.current = grouping;

  // ---- Load persisted settings -------------------------------------------
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const s = await api.get<TestDesignSettings>("/testdesign");
        if (!alive) return;
        setTitle(s.project_title);
        setTemplate(s.design_template);
        setGrouping(s.operation_grouping || "grouped");
      } catch (e) {
        if (alive) toast(`Test Design: ${(e as Error).message}`);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [toast]);

  // ---- Save (on blur / grouping change) ----------------------------------
  const save = useCallback(async () => {
    try {
      await api.put<TestDesignSettings>("/testdesign", {
        project_title: titleRef.current,
        design_template: templateRef.current,
        operation_grouping: groupingRef.current,
      });
    } catch (e) {
      toast(`Save failed: ${(e as Error).message}`);
    }
  }, [toast]);

  // ---- Preview (debounced on edits; immediate on paging/grouping) --------
  const fetchPreview = useCallback(
    async (idx: number) => {
      try {
        const p = await api.post<TestDesignPreview>("/testdesign/preview", {
          project_title: titleRef.current,
          design_template: templateRef.current,
          operation_grouping: groupingRef.current,
          row_index: idx,
        });
        setPreview(p);
        // Clamp our local index to whatever the server resolved.
        if (p.index !== idx) setRowIndex(p.index);
      } catch (e) {
        toast(`Preview: ${(e as Error).message}`);
      }
    },
    [toast],
  );

  // Re-render the preview shortly after the template/title settle.
  const debounceRef = useRef<number | null>(null);
  useEffect(() => {
    if (!loaded) return;
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      fetchPreview(rowIndex);
    }, 350);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, template, loaded]);

  // Immediate refresh when paging or switching grouping mode.
  useEffect(() => {
    if (loaded) fetchPreview(rowIndex);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowIndex, grouping, loaded]);

  // Active-row data can change under us (edits in Workspace, a re-match job);
  // refresh the preview when the project signals a data change.
  useSSE(
    useCallback(
      (e) => {
        if (e.event === "db-changed") fetchPreview(rowIndex);
      },
      [fetchPreview, rowIndex],
    ),
  );

  // ---- Monaco: register condition autocomplete ---------------------------
  const monacoRef = useRef<MonacoNs | null>(null);
  const providerRef = useRef<{ dispose: () => void } | null>(null);

  const onEditorMount: OnMount = (_editor, monaco) => {
    monacoRef.current = monaco;
    providerRef.current?.dispose();
    providerRef.current = monaco.languages.registerCompletionItemProvider(
      "markdown",
      {
        // '[' starts a column token, '#' starts a #if, ' ' advances within a
        // condition; the backend tokenizer decides what to offer from there.
        triggerCharacters: ["[", "#", " ", "'"],
        async provideCompletionItems(
          model: CompletionModel,
          position: CursorPosition,
        ) {
          const lineText = model.getValueInRange({
            startLineNumber: position.lineNumber,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: position.column,
          });
          let data: TestDesignSuggestions;
          try {
            data = await api.get<TestDesignSuggestions>(
              `/testdesign/suggestions?line_text=${encodeURIComponent(lineText)}`,
            );
          } catch {
            return { suggestions: [] };
          }
          if (!data.completions.length) return { suggestions: [] };
          const prefixLen = data.prefix.length;
          const range = new monaco.Range(
            position.lineNumber,
            position.column - prefixLen,
            position.lineNumber,
            position.column,
          );
          return {
            suggestions: data.completions.map((c) => ({
              label: c,
              kind: monaco.languages.CompletionItemKind.Keyword,
              insertText: c,
              range,
            })),
          };
        },
      },
    );
  };

  useEffect(() => () => providerRef.current?.dispose(), []);

  // ---- Export ------------------------------------------------------------
  async function exportTestCases(scope: "current" | "all") {
    setExporting(true);
    try {
      await save();
      const res = await api.post<TestDesignExportResult>("/testdesign/export", {
        project_title: titleRef.current,
        design_template: templateRef.current,
        operation_grouping: groupingRef.current,
        scope,
      });
      if (res.file_count === 0) {
        toast("No renderable rows — nothing exported.");
      } else {
        toast(`Exported ${res.file_count} file${res.file_count === 1 ? "" : "s"} to Test Case Design/`);
      }
    } catch (e) {
      toast(`Export failed: ${(e as Error).message}`);
    } finally {
      setExporting(false);
    }
  }

  const total = preview?.row_count ?? 0;
  const unit = preview?.unit_label ?? "Port";
  const previewHtml = useMemo(
    () =>
      preview && preview.status === "ok"
        ? renderMarkdown(`# ${preview.title}\n\n${preview.body}`)
        : "",
    [preview],
  );

  return (
    <div className="td-view">
      {/* Toolbar */}
      <div className="td-toolbar">
        <label className="td-group">
          <span>Operation grouping</span>
          <select
            value={grouping}
            onChange={(e) => {
              setGrouping(e.target.value);
              setRowIndex(0);
              // Persist the mode change immediately (refs already updated next tick).
              groupingRef.current = e.target.value;
              save();
            }}
          >
            {GROUPINGS.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
        </label>
        <div className="spacer" />
        <button
          className="scope-btn"
          disabled={exporting}
          onClick={() => exportTestCases("all")}
        >
          Export All Models
        </button>
        <button
          className="save-btn"
          disabled={exporting}
          onClick={() => exportTestCases("current")}
        >
          {exporting ? "Exporting…" : "Export Test Cases"}
        </button>
      </div>

      <div className="td-split">
        {/* Left: editor */}
        <div className="td-editor-pane">
          <label className="td-field">
            <span>Project Title</span>
            <input
              type="text"
              className="td-title-input"
              spellCheck={false}
              placeholder="e.g. [Model] — [Input Port]"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={save}
            />
          </label>
          <div className="td-editor-label">Design Template</div>
          <div className="td-monaco" onBlur={save}>
            <Editor
              height="100%"
              defaultLanguage="markdown"
              theme={theme}
              value={template}
              onMount={onEditorMount}
              onChange={(v) => setTemplate(v ?? "")}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                wordWrap: "on",
                lineNumbers: "on",
                scrollBeyondLastLine: false,
                quickSuggestions: true,
                suggestOnTriggerCharacters: true,
                // Render the suggest widget in document.body (fixed position)
                // so it isn't clipped by the .td-monaco container's
                // overflow: hidden when it spills past the editor bounds.
                fixedOverflowWidgets: true,
                // Drop the completion kind-icons: this completer offers column
                // names / operators where the icon adds no meaning, and the
                // icon's layout was hiding the label in this app's Monaco build.
                suggest: { showIcons: false, showStatusBar: false },
              }}
            />
          </div>
        </div>

        {/* Right: preview */}
        <div className="td-preview-pane">
          <div className="td-preview-head">
            <span className="td-preview-title">Preview</span>
            <div className="spacer" />
            <button
              className="scope-btn"
              disabled={rowIndex <= 0}
              onClick={() => setRowIndex((i) => Math.max(0, i - 1))}
              title="Previous"
            >
              ‹
            </button>
            <span className="td-pager">
              {total === 0 ? "No rows" : `${unit} ${rowIndex + 1} of ${total}`}
            </span>
            <button
              className="scope-btn"
              disabled={total === 0 || rowIndex >= total - 1}
              onClick={() => setRowIndex((i) => Math.min(total - 1, i + 1))}
              title="Next"
            >
              ›
            </button>
          </div>
          <div className="td-preview-body">
            {preview && preview.status === "ok" ? (
              <div
                className="td-markdown"
                dangerouslySetInnerHTML={{ __html: previewHtml }}
              />
            ) : (
              <div className="td-preview-empty">
                {preview?.message || "Loading preview…"}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
