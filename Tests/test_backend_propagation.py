"""
Phase 1 — port-state propagation (#8.2) tests: the two-step preview → commit
flow when a model leaves "In Work", including selective propagation.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "prop-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

LAYOUT = [
    ("TC. ID", "Static Text", True),
    ("Input Port", "Port Search", True),
    ("Port State", "PortStateColumn", True),
]


def _rows():
    return [
        {"TC. ID": {"text": "TC_001"}, "Input Port": {"text": "p_speed"},
         "Port State": {"text": "In Work", "widget_text": "In Work"}},
        {"TC. ID": {"text": "TC_002"}, "Input Port": {"text": "p_torque"},
         "Port State": {"text": "In Work", "widget_text": "In Work"}},
        {"TC. ID": {"text": "TC_003"}, "Input Port": {"text": "p_locked"},
         "Port State": {"text": "Released", "widget_text": "Released"}},
    ]


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path, layout=LAYOUT,
            models=[{"name": "Arch_A", "status": "In Work", "rows": _rows()}],
            releases=[{"name": "R1"}])
        db.commit(); db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        yield c


def _mid(client):
    return next(m["id"] for m in client.get("/api/models", headers=AUTH).json()["models"])


def _port_states(client, mid):
    rows = client.get(f"/api/models/{mid}/ports", headers=AUTH).json()["rows"]
    return [r["cells"]["Port State"]["text"] for r in rows]


def test_preview_lists_in_work_ports(client):
    mid = _mid(client)
    body = client.post(f"/api/models/{mid}/state/preview",
                       json={"new_status": "Released"}, headers=AUTH).json()
    assert body["propagates"] is True
    assert body["old_status"] == "In Work"
    assert body["port_name_column"] == "Input Port"
    affected = {p["port_name"] for p in body["affected_ports"]}
    assert affected == {"p_speed", "p_torque"}     # p_locked (Released) excluded


def test_preview_no_propagation_when_staying_in_work(client):
    mid = _mid(client)
    body = client.post(f"/api/models/{mid}/state/preview",
                       json={"new_status": "In Work"}, headers=AUTH).json()
    assert body["propagates"] is False
    assert body["affected_ports"] == []


def test_commit_propagates_to_all(client):
    mid = _mid(client)
    r = client.post(f"/api/models/{mid}/state",
                    json={"new_status": "Released"}, headers=AUTH).json()
    assert r["ports_changed"] == 2
    assert _port_states(client, mid) == ["Released", "Released", "Released"]
    # Model status persisted.
    m = next(m for m in client.get("/api/models", headers=AUTH).json()["models"] if m["id"] == mid)
    assert m["status"] == "Released"


def test_commit_propagates_only_selected(client):
    mid = _mid(client)
    r = client.post(f"/api/models/{mid}/state",
                    json={"new_status": "Released", "selected_ports": ["p_speed"]},
                    headers=AUTH).json()
    assert r["ports_changed"] == 1
    # p_speed follows; p_torque stays In Work; p_locked untouched.
    assert _port_states(client, mid) == ["Released", "In Work", "Released"]


def test_commit_staying_in_work_changes_nothing(client):
    mid = _mid(client)
    r = client.post(f"/api/models/{mid}/state",
                    json={"new_status": "In Work"}, headers=AUTH).json()
    assert r["ports_changed"] == 0
    assert _port_states(client, mid) == ["In Work", "In Work", "Released"]


def test_preview_retired_not_eligible_strict_forward(client):
    # Strict forward: leaving In Work for a non-Released state does not cascade.
    mid = _mid(client)
    body = client.post(f"/api/models/{mid}/state/preview",
                       json={"new_status": "Retired"}, headers=AUTH).json()
    assert body["propagates"] is False
    assert body["affected_ports"] == []


def test_commit_in_work_to_retired_does_not_propagate(client):
    # In Work → Retired moves the model but leaves every port untouched.
    mid = _mid(client)
    r = client.post(f"/api/models/{mid}/state",
                    json={"new_status": "Retired"}, headers=AUTH).json()
    assert r["ports_changed"] == 0
    assert _port_states(client, mid) == ["In Work", "In Work", "Released"]
    m = next(m for m in client.get("/api/models", headers=AUTH).json()["models"] if m["id"] == mid)
    assert m["status"] == "Retired"   # model status still changes


def test_view_only_cannot_commit_state(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        mid = _mid(c)
        # Preview is a read → allowed.
        assert c.post(f"/api/models/{mid}/state/preview",
                      json={"new_status": "Released"}, headers=AUTH).status_code == 200
        # Commit is a write → 409.
        assert c.post(f"/api/models/{mid}/state",
                      json={"new_status": "Released"}, headers=AUTH).status_code == 409
