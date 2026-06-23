"""
Worker-process bootstrap for the Phase 3 desktop shell (plan §3.3 / §5).

Kept free of any pywebview/GUI import so it can be unit-tested headless. The
desktop shell (``desktop/main.py``) spawns the worker with ``multiprocessing``,
receives the OS-assigned port back over a pipe, and points the native window at
it. The same pipe doubles as a **lifeline**: if the parent (UI) process dies, the
worker's end raises ``EOFError`` and the worker shuts down gracefully — releasing
the ``.arch`` edit lock via the FastAPI lifespan — so no zombie server keeps the
project locked.
"""
from __future__ import annotations

import multiprocessing as mp
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

# All app code now lives under ``src/`` (``src/backend``, ``src/desktop``,
# ``src/Application_Logic``, ...). This file is ``src/desktop/worker.py``, so its
# grandparent is that single source root. The spawned child re-imports this
# module; make sure the source root is importable there for ``backend``,
# ``desktop`` and ``Application_Logic`` alike.
SRC = Path(__file__).resolve().parent.parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def run_worker(conn) -> None:
    """Child entrypoint: bind a port, report it, serve until the parent goes away.

    ``conn`` first carries the chosen port (parent → reads it), then stays open
    as the lifeline. A daemon thread blocks on ``conn.recv()``; when the parent
    closes its end (clean exit or crash) that raises ``EOFError`` and we ask
    uvicorn to stop, which runs the lifespan shutdown and releases the lock.
    """
    import uvicorn

    from backend.app import create_app

    token = conn.recv()  # parent sends the session token first
    app = create_app(token=token, serve_frontend=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    conn.send(port)

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    # uvicorn would normally install signal handlers only in the main thread;
    # we run server.run() in this (main) thread, so SIGTERM still works as a
    # fallback. The lifeline is the primary, cross-platform stop signal.

    def _watch_parent() -> None:
        try:
            conn.recv()  # blocks until the parent sends or closes the pipe
        except EOFError:
            pass
        server.should_exit = True

    threading.Thread(target=_watch_parent, daemon=True).start()
    server.run(sockets=[sock])


def spawn_worker(token: str, timeout: float = 30.0):
    """Spawn the worker process; return ``(proc, port, lifeline_conn)``.

    The caller MUST keep ``lifeline_conn`` open for the app's lifetime and close
    it on shutdown to signal the worker to stop gracefully.
    """
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe()
    proc = ctx.Process(target=run_worker, args=(child_conn,), name="arch-worker")
    proc.start()
    child_conn.close()  # parent keeps only its own end

    parent_conn.send(token)
    if not parent_conn.poll(timeout):
        proc.terminate()
        raise RuntimeError(f"Worker did not report a port within {timeout:.0f}s")
    port = parent_conn.recv()
    return proc, port, parent_conn


def wait_until_ready(port: int, timeout: float = 20.0, interval: float = 0.1) -> bool:
    """Poll ``/api/health`` until the worker accepts connections."""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:  # noqa: S310 (localhost only)
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(interval)
    return False
