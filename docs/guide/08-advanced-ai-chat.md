# 8. Advanced AI Chat

The **Advanced AI Chat** tab lets you ask questions about your firmware and get
answers grounded in the *actual* C source — not guesses. It works by indexing your
code into a compact **mind map** and then letting the AI pull exactly the pieces it
needs through a small set of read-only tools.

← Back to [7. AI Test Case Generation](07-ai-test-generation.md) · Up: [User Guide](README.md)

---

> 📷 _Screenshot coming soon._

## What you need

- A **source folder** containing the C source for the release you're analysing.
- A connected AI provider (see [AI Test Case Generation](07-ai-test-generation.md)
  for sign-in / API keys — the same providers and credential store are used here).

## The layout

The tab is a two-column workspace:

- **Left — configuration:**
  - **Source** — *Current* and *Previous* source folders (Previous is optional and
    only used for diffs).
  - **Requirements** — *Import Requirements…* loads a CSV/XLSX of `ID, Description`
    rows so the mind map can bind requirements to the functions that implement them.
  - **Mind Map** — pick the architecture model, then **Generate Mind Map** (this
    model) or **Generate All**. **Generate Diffs (Current vs Previous)** computes
    file-by-file source diffs when a Previous folder is set.
  - **Prompt & Rules** — three independent editors: *Mind Map Prompt*, *Mind Map
    Rules*, and *Chat Rules*, each with a Reset-to-default.
  - **Provider** — provider/model picker, connection status, Configure / Help.
- **Right — the chat:** the conversation (rendered markdown + a trace of the tool
  calls the agent makes), a multi-line input, and **Send / Stop / Clear Context**.

## Generate the mind map

Set **Current** source to your code folder and click **Generate Mind Map**. The app
indexes the C source locally (no AI tokens) into a compact index of signatures,
call/data-flow relationships and requirement traces, and caches it in the project.
The button flips to **Regenerate Mind Map** once a map exists; regenerate after the
source changes.

> The mind map is what the AI reads by default — it's deliberately small so requests
> stay token-cheap regardless of repo size. Raw source is only fetched on demand.

## Chat about the code

Type a question and **Send** (or `Ctrl`+`Enter`). The agent answers using read-only,
sandboxed tools and shows each call inline, e.g. `→ read_file(wlc_main.c)`:

| Tool | What it does |
|------|--------------|
| `read_file` | Read a source file (sandboxed to the source root) |
| `search_code` | Grep-style search across the source |
| `get_mind_map` | The compact per-model index |
| `get_requirements` | The imported requirements |
| `get_function` / `get_call_graph` | One function's neighbourhood / a caller-callee graph |
| `get_diff` | The stored current-vs-previous diff for a file |

Every tool is read-only and confined to the configured source root by a path-jail —
the agent can read your code but never write or escape the folder.

**Example:** *"What current threshold does the pinch detection use, and which function
reads the current?"* → the agent reads the relevant file and answers with the exact
value, constant name, function, and requirement trace.

## Requirements & diffs

- **Import Requirements** to give the AI your `REQ-…` traceability; matching
  functions are bound into the mind map and pullable via `get_requirements`.
- With a **Previous** source set, **Generate Diffs** stores per-file unified diffs
  so the agent (and the [Change Log](10-change-log.md) tab) can show exactly what
  changed between two releases.

➡️ Next: **[9. Code Map](09-code-map.md)**
