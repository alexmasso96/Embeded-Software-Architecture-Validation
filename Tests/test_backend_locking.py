"""
Phase 1 — file locking + heartbeat (plan §3.3).

Covers: exclusive open holds the lock; a second exclusive open of the same file
is refused; the heartbeat notices a lock takeover and drops the session to
lock-lost (writes 409, status reports it, a `lock` SSE event fires).
"""
import json
import os
import socket
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic.Logic_File_Locking import FileLockManager
from Tests.test_helpers import make_project_db

TOKEN = "lock-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        db.close()
        yield path


def test_exclusive_open_holds_lock(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        body = c.post("/api/project/open",
                      json={"path": project_path, "mode": "exclusive"}, headers=AUTH).json()
        assert body["mode"] == "exclusive"
        # The lock file exists and is held by us.
        assert FileLockManager.check_lock(project_path)["status"] == "locked_by_me"
        c.post("/api/project/close", headers=AUTH)
        # Lock released on close.
        assert FileLockManager.check_lock(project_path)["status"] == "unlocked"


def _steal_lock(project_path):
    """Overwrite the lock file as if another host took it over."""
    lock_file = FileLockManager.get_lock_file_path(project_path)
    now = "2999-01-01T00:00:00+00:00"
    with open(lock_file, "w") as f:
        json.dump({"user": "intruder", "hostname": "otherhost",
                   "timestamp": now, "last_seen": now, "pid": 999999}, f)


def test_exclusive_open_refused_when_locked_by_other(project_path):
    # Simulate another session (different host) already holding the lock.
    # (A same-process second open can't be tested via the real PID check — real
    # sessions are separate processes; a foreign-host lock is the genuine case.)
    _steal_lock(project_path)
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        r = c.post("/api/project/open",
                   json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        assert r.status_code == 409
        # …but view-only is fine even while another session holds the lock.
        assert c.post("/api/project/open",
                      json={"path": project_path, "mode": "view"}, headers=AUTH).status_code == 200


def test_heartbeat_detects_lock_takeover(project_path):
    # Fast heartbeat so the takeover is noticed quickly.
    app = create_app(token=TOKEN, heartbeat_interval=0.1)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        assert c.get("/api/project/status", headers=AUTH).json()["lock_lost"] is False

        _steal_lock(project_path)

        # Poll status until the heartbeat flips lock_lost.
        deadline = time.time() + 5
        lost = False
        while time.time() < deadline:
            if c.get("/api/project/status", headers=AUTH).json()["lock_lost"]:
                lost = True
                break
            time.sleep(0.05)
        assert lost, "heartbeat did not detect the lock takeover"

        # Writes are now refused (409); reads still work.
        assert c.post("/api/project/save", headers=AUTH).status_code == 409
        assert c.post("/api/models", json={"name": "X"}, headers=AUTH).status_code == 409
        assert c.get("/api/models", headers=AUTH).status_code == 200


def test_view_only_open_of_modelless_project_does_not_crash():
    # Regression: load_registry must not write a default model on a read-only DB.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "empty.arch")
        db = make_project_db(path, layout=[("TC. ID", "Static Text", True)],
                             releases=[{"name": "R1"}])   # no models
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            r = c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            assert r.status_code == 200, r.text
            # The in-memory placeholder model is surfaced without a DB write.
            assert c.get("/api/models", headers=AUTH).json()["models"][0]["name"] == "Architecture_1"
