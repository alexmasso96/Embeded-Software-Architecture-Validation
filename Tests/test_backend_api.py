"""
Phase 1 — FastAPI worker API tests (plan §3.4).

Covers: bearer-token auth, project new/open/save/status/close lifecycle, the
job manager (start/poll/cancel), and that the whole backend imports without
PyQt6. Uses the FastAPI TestClient (httpx) against an in-process app.
"""
import os
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app

TOKEN = "test-token-123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def tmp_arch():
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, "proj.arch")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_health_requires_no_token(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_status_rejects_missing_token(client):
    assert client.get("/api/project/status").status_code == 401


def test_status_rejects_wrong_token(client):
    r = client.get("/api/project/status", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_status_accepts_valid_token(client):
    r = client.get("/api/project/status", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["open"] is False


# ---------------------------------------------------------------------------
# Project lifecycle
# ---------------------------------------------------------------------------
def test_new_open_save_close_cycle(client, tmp_arch):
    # New project → exclusive edit, open.
    r = client.post("/api/project/new", json={"path": tmp_arch}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["open"] is True
    assert body["mode"] == "exclusive"
    assert body["can_edit"] is True
    assert os.path.exists(tmp_arch)

    # Save stamps integrity + commits.
    assert client.post("/api/project/save", headers=AUTH).json()["open"] is True

    # Close.
    assert client.post("/api/project/close", headers=AUTH).json()["open"] is False

    # Reopen view-only → read-only, cannot edit, save refused.
    r = client.post("/api/project/open", json={"path": tmp_arch, "mode": "view"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "view"
    assert r.json()["can_edit"] is False
    assert client.post("/api/project/save", headers=AUTH).status_code == 409


def test_new_project_seeds_default_layout(client, tmp_arch):
    """A fresh project opens with the PyQt6 default columns (issue: new projects
    should give the user basic columns to work with)."""
    client.post("/api/project/new", json={"path": tmp_arch}, headers=AUTH)
    cols = client.get("/api/columns", headers=AUTH).json()["columns"]
    names = [c["name"] for c in cols]
    assert names[0] == "TC. ID"
    for expected in ["Input Port", "Input Port (Match)", "Mapped Func",
                     "Mapped Parameter", "Review Status", "Port State"]:
        assert expected in names, expected
    # search columns carry their proper logic_key types
    by_name = {c["name"]: c["type"] for c in cols}
    assert by_name["Input Port"] == "Port Search"
    assert by_name["Mapped Func"] == "Function Search"
    assert by_name["Review Status"] == "Review Status"


def test_new_project_rejects_existing_path(client, tmp_arch):
    assert client.post("/api/project/new", json={"path": tmp_arch}, headers=AUTH).status_code == 200
    client.post("/api/project/close", headers=AUTH)
    # File now exists → new must refuse.
    assert client.post("/api/project/new", json={"path": tmp_arch}, headers=AUTH).status_code == 409


def test_open_missing_file_409(client, tmp_arch):
    assert client.post("/api/project/open", json={"path": tmp_arch}, headers=AUTH).status_code == 409


def test_open_unknown_mode_422(client, tmp_arch):
    client.post("/api/project/new", json={"path": tmp_arch}, headers=AUTH)
    client.post("/api/project/close", headers=AUTH)
    r = client.post("/api/project/open", json={"path": tmp_arch, "mode": "bogus"}, headers=AUTH)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def _wait_for_job(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if body["status"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish")


def test_job_kinds_listed(client):
    kinds = client.get("/api/jobs", headers=AUTH).json()["kinds"]
    assert "_demo" in kinds
    assert "release_diff" in kinds
    assert "build_code_map" in kinds


def test_demo_job_runs_to_completion(client):
    r = client.post("/api/jobs/_demo", json={"steps": 4, "echo": "hi"}, headers=AUTH)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    body = _wait_for_job(client, job_id)
    assert body["status"] == "done"
    assert body["result"] == {"steps_completed": 4, "echo": "hi"}
    assert body["progress"] == 100.0


def test_unknown_job_kind_404(client):
    assert client.post("/api/jobs/nope", json={}, headers=AUTH).status_code == 404


def test_job_get_unknown_404(client):
    assert client.get("/api/jobs/deadbeef", headers=AUTH).status_code == 404


def test_demo_job_cancellation(client):
    # Long-running demo (10 steps × 50ms) → cancel mid-flight.
    r = client.post("/api/jobs/_demo", json={"steps": 10, "delay": 0.05}, headers=AUTH)
    job_id = r.json()["job_id"]
    time.sleep(0.08)
    assert client.post(f"/api/jobs/{job_id}/cancel", headers=AUTH).json()["cancelling"] is True
    body = _wait_for_job(client, job_id)
    assert body["status"] == "cancelled"
    assert body["result"]["steps_completed"] < 10


def test_release_diff_job_requires_open_project(client):
    r = client.post("/api/jobs/release_diff",
                    json={"current_release_id": 1, "previous_release_id": 2}, headers=AUTH)
    body = _wait_for_job(client, r.json()["job_id"])
    assert body["status"] == "failed"
    assert "No project is open" in body["error"]


# ---------------------------------------------------------------------------
# No PyQt6 under backend/
# ---------------------------------------------------------------------------
def test_backend_imports_without_pyqt6():
    import builtins
    real_import = builtins.__import__

    def guard(name, *a, **kw):
        if name == "PyQt6" or name.startswith("PyQt6."):
            raise ImportError(f"BLOCKED: {name}")
        return real_import(name, *a, **kw)

    import importlib
    for mod in ["backend.app", "backend.state", "backend.jobs",
                "backend.events", "backend.handlers", "backend.security"]:
        sys.modules.pop(mod, None)
    builtins.__import__ = guard
    try:
        for mod in ["backend.events", "backend.jobs", "backend.state",
                    "backend.handlers", "backend.security", "backend.app"]:
            importlib.import_module(mod)
    finally:
        builtins.__import__ = real_import
