"""
FastAPI app factory + standalone entrypoint (plan §3).

``create_app()`` wires the singletons (EventBus, AppState, JobManager) onto
app.state, binds the running event loop to the bus at startup so worker-thread
publishers can reach it, and mounts the routers.

Run standalone:
    uvicorn backend.app:app --port 8765          # fixed port, dev
    python -m backend.app                         # 127.0.0.1:0, prints the URL+token
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI

from .events import EventBus
from .handlers import register_handlers
from .jobs import JobManager
from .security import generate_token
from .state import AppState
from .routers import ai as ai_router
from .routers import architecture as architecture_router
from .routers import changelog as changelog_router
from .routers import codemap as codemap_router
from .routers import jobs as jobs_router
from .routers import project as project_router
from .routers import releases as releases_router
from .routers import symbols as symbols_router

logger = logging.getLogger(__name__)


def create_app(token: str | None = None) -> FastAPI:
    bus = EventBus()
    state = AppState(bus)
    jobs = JobManager(bus)
    register_handlers(jobs, state)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        bus.bind_loop(asyncio.get_running_loop())
        logger.info("Worker ready. Session token: %s", app.state.token)
        try:
            yield
        finally:
            jobs.shutdown()
            state.close_project()

    app = FastAPI(title="Architecture Validator — Worker", lifespan=lifespan)
    app.state.bus = bus
    app.state.appstate = state
    app.state.jobs = jobs
    app.state.token = token or os.environ.get("ARCH_API_TOKEN") or generate_token()

    app.include_router(project_router.router)
    app.include_router(jobs_router.router)
    app.include_router(architecture_router.router)
    app.include_router(releases_router.router)
    app.include_router(symbols_router.router)
    app.include_router(codemap_router.router)
    app.include_router(changelog_router.router)
    app.include_router(ai_router.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app


# Module-level app for `uvicorn backend.app:app`.
app = create_app()


def main() -> None:
    """Bind 127.0.0.1:0 (OS-assigned port), print the URL + token, serve.

    The desktop shell (Phase 3) reads the port off a pipe instead; this path is
    for running the worker by hand during development.
    """
    import socket
    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    print(f"Worker URL: http://127.0.0.1:{port}")
    print(f"Session token: {app.state.token}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
