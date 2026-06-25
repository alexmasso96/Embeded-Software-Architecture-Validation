"""
Phase 3 — desktop worker bootstrap (plan §3.3 / §5).

Headless coverage for the multiprocessing worker: port handshake, HTTP
readiness, token auth over the real socket, and the lifeline shutdown (closing
the parent's pipe end must stop the worker — the no-zombie-lock guarantee).
No pywebview/GUI is involved here.
"""
import os
import sys
import time
import urllib.request

import pytest

sys.path.insert(0, os.path.abspath("src"))

from desktop.worker import spawn_worker, wait_until_ready


def _get(port, path, token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=3)


@pytest.fixture()
def worker():
    proc, port, lifeline = spawn_worker("desk-token-xyz")
    try:
        assert wait_until_ready(port, timeout=20), "worker never became ready"
        yield proc, port, lifeline
    finally:
        if not lifeline.closed:
            lifeline.close()
        proc.join(timeout=8)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=3)


def test_health_is_open(worker):
    _, port, _ = worker
    r = _get(port, "/api/health")
    assert r.status == 200


def test_api_requires_token(worker):
    _, port, _ = worker
    with pytest.raises(urllib.error.HTTPError) as ei:
        _get(port, "/api/project/status")
    assert ei.value.code == 401


def test_api_accepts_session_token(worker):
    _, port, _ = worker
    r = _get(port, "/api/project/status", token="desk-token-xyz")
    assert r.status == 200


def test_spa_shell_is_served(worker):
    # serve_frontend=True → the built index.html is returned at the root
    _, port, _ = worker
    r = _get(port, "/")
    body = r.read().decode("utf-8", "replace")
    assert r.status == 200
    assert "<html" in body.lower() or "<!doctype" in body.lower()


def test_lifeline_close_shuts_worker_down(worker):
    proc, _, lifeline = worker
    lifeline.close()
    # graceful uvicorn shutdown should land within a few seconds
    deadline = time.monotonic() + 10
    while proc.is_alive() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not proc.is_alive(), "worker did not exit after lifeline closed"
