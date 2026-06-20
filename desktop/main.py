"""
Phase 3 desktop shell: native pywebview window over the FastAPI worker (plan §5).

    python -m desktop.main

Spawns the worker process, waits for it to report its port and become ready,
then opens a native window pointing at the worker's statically-served React
build. The session token and native file dialogs are exposed to the SPA through
pywebview's ``js_api`` (so the token never travels over HTTP).
"""
from __future__ import annotations

import logging
import sys

import webview

from backend.security import generate_token
from desktop.worker import spawn_worker, wait_until_ready

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Architecture Validator"


class JsApi:
    """Bridge exposed to the SPA as ``window.pywebview.api``.

    ``get_token`` hands the per-session bearer token to the frontend without it
    ever crossing HTTP. The ``pick_*`` methods open real OS dialogs so the app
    can resolve actual filesystem paths (needed for ``.arch``/ELF/source on
    network shares — browser file inputs can't).
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def get_token(self) -> str:
        return self._token

    def set_title(self, title: str) -> None:
        # Best-effort native title sync (document.title already drives this on
        # most backends; this guarantees it on the rest).
        if self._window and title:
            try:
                self._window.set_title(title)
            except Exception:
                pass

    def pick_folder(self) -> str | None:
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return res[0] if res else None

    def pick_open_file(self, file_types: list[str] | None = None) -> str | None:
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=tuple(file_types) if file_types else (),
        )
        return res[0] if res else None

    def pick_save_file(self, default_name: str = "") -> str | None:
        res = self._window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=default_name or ""
        )
        if not res:
            return None
        return res if isinstance(res, str) else res[0]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = generate_token()

    proc, port, lifeline = spawn_worker(token)
    url = f"http://127.0.0.1:{port}"
    logger.info("Worker started on %s", url)

    if not wait_until_ready(port):
        lifeline.close()
        proc.terminate()
        proc.join(timeout=5)
        print("Worker failed to become ready; aborting.", file=sys.stderr)
        raise SystemExit(1)

    api = JsApi(token)
    window = webview.create_window(
        WINDOW_TITLE,
        # ?desktop=1 tells the SPA to pull its token through the js_api bridge
        # (and that native file dialogs are available) instead of the env token.
        f"{url}/?desktop=1",
        js_api=api,
        width=1280,
        height=820,
        min_size=(900, 600),
    )
    api.set_window(window)

    try:
        webview.start()
    finally:
        # Closing the lifeline triggers the worker's graceful shutdown, which
        # runs the FastAPI lifespan finally → releases the .arch edit lock.
        lifeline.close()
        proc.join(timeout=8)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=3)
        if proc.is_alive():
            proc.kill()


if __name__ == "__main__":
    import multiprocessing

    # Required so the spawned worker re-executes correctly inside a frozen
    # (PyInstaller) bundle; a no-op in a normal interpreter.
    multiprocessing.freeze_support()
    main()
