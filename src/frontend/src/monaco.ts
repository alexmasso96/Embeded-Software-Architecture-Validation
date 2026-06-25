// Bundle Monaco locally instead of letting @monaco-editor/react fetch it from a
// CDN at runtime.
//
// By default @monaco-editor/loader pulls monaco-editor (JS *and* CSS) from
// https://cdn.jsdelivr.net/npm/monaco-editor@x/min/vs. In the packaged desktop
// app — especially on locked-down/offline machines — that request can be blocked
// or intercepted: the editor JS may still load (syntax highlighting works) while
// the stylesheet doesn't, leaving widgets like the autocomplete popup rendered
// but blank. Pointing the loader at the npm-bundled monaco makes the app fully
// self-contained and identical in dev and production.

import * as monaco from "monaco-editor";
import { loader } from "@monaco-editor/react";
// Vite turns this `?worker` import into a bundled Web Worker. We only use the
// base editor worker (plain text / C / markdown tokenisation + our own
// completion providers) — no TS/JSON/CSS language services are needed.
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

self.MonacoEnvironment = {
  getWorker() {
    return new EditorWorker();
  },
};

loader.config({ monaco });
