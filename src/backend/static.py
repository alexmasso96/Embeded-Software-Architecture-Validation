"""
Serve the built React SPA (``frontend/dist/``) from the worker (plan §5).

In development the frontend is served by Vite and the worker only answers
``/api/*``. In the Phase 3 desktop shell there is no second server: the worker
serves the static build itself, so ``create_app(serve_frontend=True)`` mounts it.

Static files are intentionally unauthenticated (they are just the app shell —
no data). All data flows through ``/api/*``, which requires the session token,
and the token reaches the SPA through pywebview's ``js_api`` (never over HTTP).
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def frontend_dist() -> Path:
    # In a PyInstaller bundle the build is unpacked under sys._MEIPASS; in a
    # source checkout it sits at <repo>/frontend/dist.
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "frontend" / "dist"
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> bool:
    """Mount the SPA if a build exists. Returns True when mounted.

    Registered AFTER the API routers so ``/api/*`` always wins; the catch-all
    only handles client-side routes (it serves ``index.html`` for unknown GETs,
    which is the standard SPA-history fallback).
    """
    dist = frontend_dist()
    index = dist / "index.html"
    if not index.exists():
        return False

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    def _index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{path:path}", include_in_schema=False)
    def _spa(path: str) -> FileResponse:
        if path.startswith("api/") or path == "api":
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if candidate.is_file() and (candidate == dist.resolve() or dist.resolve() in candidate.parents):
            return FileResponse(candidate)
        return FileResponse(index)

    return True
