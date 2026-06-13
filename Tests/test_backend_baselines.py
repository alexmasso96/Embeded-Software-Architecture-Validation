"""
Phase 1 — baselines router tests: create a frozen snapshot of the active
release + active model, list baselines, and read a baseline's snapshot back.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "bl-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

LAYOUT = [("TC. ID", "Static Text", True), ("Port State", "PortStateColumn", True)]
ROWS = [
    {"TC. ID": {"text": "TC_001"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
    {"TC. ID": {"text": "TC_002"}, "Port State": {"text": "Released", "widget_text": "Released"}},
]


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path, layout=LAYOUT,
            models=[{"name": "Arch_A", "status": "In Work", "rows": ROWS}],
            releases=[{"name": "R1"}])
        db.set_active_release(db.get_all_releases()[0]["id"])
        db.commit(); db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        yield c


def test_create_and_list_baseline(client):
    r = client.post("/api/baselines", json={"name": "BL_1"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["parent_release_name"] == "R1"
    assert r.json()["row_count"] == 2

    bls = client.get("/api/baselines", headers=AUTH).json()["baselines"]
    assert [b["name"] for b in bls] == ["BL_1"]
    # The baseline also shows up as a (non-selectable) release.
    rels = client.get("/api/releases", headers=AUTH).json()["releases"]
    bl = next(r for r in rels if r["name"] == "BL_1")
    assert bl["is_baseline"] is True and bl["selectable"] is False


def test_get_baseline_snapshot(client):
    bid = client.post("/api/baselines", json={"name": "BL_1"}, headers=AUTH).json()["id"]
    snap = client.get(f"/api/baselines/{bid}", headers=AUTH).json()
    assert snap["row_count"] == 2
    assert snap["rows"][0]["cells"]["TC. ID"]["text"] == "TC_001"
    # Layout snapshot captured the columns at creation time.
    assert [c[0] for c in snap["layout"]["layout"]] == ["TC. ID", "Port State"]
    assert snap["layout"]["version"] == "2.0"


def test_baseline_is_frozen_snapshot(client):
    """Editing the live model after baselining must not change the baseline."""
    bid = client.post("/api/baselines", json={"name": "BL_1"}, headers=AUTH).json()["id"]
    mid = next(m["id"] for m in client.get("/api/models", headers=AUTH).json()["models"])
    client.patch(f"/api/models/{mid}/ports/0",
                 json={"updates": {"TC. ID": "CHANGED"}}, headers=AUTH)
    snap = client.get(f"/api/baselines/{bid}", headers=AUTH).json()
    assert snap["rows"][0]["cells"]["TC. ID"]["text"] == "TC_001"  # unchanged


def test_create_baseline_duplicate_name_409(client):
    client.post("/api/baselines", json={"name": "BL_1"}, headers=AUTH)
    assert client.post("/api/baselines", json={"name": "BL_1"}, headers=AUTH).status_code == 409


def test_get_unknown_baseline_409(client):
    assert client.get("/api/baselines/9999", headers=AUTH).status_code == 409


def test_view_only_cannot_create_baseline(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        assert c.post("/api/baselines", json={"name": "BL_x"}, headers=AUTH).status_code == 409
