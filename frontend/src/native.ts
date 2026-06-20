// Bridge to the pywebview desktop shell (Phase 3). In a plain browser (Vite dev)
// every function reports "not desktop" / no-ops, so the dev experience — env
// token + the /api/fs FolderPicker — is unchanged. The desktop window loads the
// SPA with ?desktop=1 so we know to wait for the (async) pywebview bridge.

interface PyApi {
  get_token(): Promise<string>;
  set_title(title: string): Promise<void>;
  pick_folder(): Promise<string | null>;
  pick_open_file(fileTypes?: string[]): Promise<string | null>;
  pick_save_file(defaultName?: string): Promise<string | null>;
}

declare global {
  interface Window {
    pywebview?: { api: PyApi };
  }
}

function desktopFlagPresent(): boolean {
  return new URLSearchParams(window.location.search).has("desktop");
}

export function isDesktop(): boolean {
  return desktopFlagPresent() || Boolean(window.pywebview?.api);
}

// pywebview injects window.pywebview asynchronously and fires `pywebviewready`.
function waitForBridge(timeoutMs = 4000): Promise<PyApi | null> {
  return new Promise((resolve) => {
    if (window.pywebview?.api) return resolve(window.pywebview.api);
    let done = false;
    const finish = (v: PyApi | null) => {
      if (!done) {
        done = true;
        resolve(v);
      }
    };
    window.addEventListener(
      "pywebviewready",
      () => finish(window.pywebview?.api ?? null),
      { once: true },
    );
    setTimeout(() => finish(window.pywebview?.api ?? null), timeoutMs);
  });
}

// Pull the session token through the JS bridge (never over HTTP) and stash it
// where the API client reads it. No-op in a browser (env token is used instead).
export async function bootstrapToken(): Promise<void> {
  if (!desktopFlagPresent()) return;
  const api = await waitForBridge();
  if (!api) return;
  try {
    const t = await api.get_token();
    if (t) window.__ARCH_TOKEN__ = t;
  } catch {
    /* dev fallback — leave env token in place */
  }
}

export function nativeSetTitle(title: string): void {
  // Fire-and-forget; document.title already updates the window on most backends.
  window.pywebview?.api?.set_title(title)?.catch(() => {});
}

export async function nativePickFolder(): Promise<string | null> {
  const api = window.pywebview?.api;
  return api ? (await api.pick_folder()) ?? null : null;
}

export async function nativePickFile(fileTypes?: string[]): Promise<string | null> {
  const api = window.pywebview?.api;
  return api ? (await api.pick_open_file(fileTypes)) ?? null : null;
}

export async function nativeSaveFile(defaultName?: string): Promise<string | null> {
  const api = window.pywebview?.api;
  return api ? (await api.pick_save_file(defaultName)) ?? null : null;
}
