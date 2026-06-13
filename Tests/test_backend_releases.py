"""
Phase 1 — releases router tests: list / create / activate / rename / delete,
the selectable vs baseline distinction, and the view-only write guard.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "rel-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path,
            layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1", "description": "first"}],
        )
        db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        yield c


def _releases(client):
    return client.get("/api/releases", headers=AUTH).json()


def _id_of(client, name):
    return next(r["id"] for r in _releases(client)["releases"] if r["name"] == name)


def test_list_releases(client):
    body = _releases(client)
    names = {r["name"] for r in body["releases"]}
    assert "R1" in names
    r1 = next(r for r in body["releases"] if r["name"] == "R1")
    assert r1["selectable"] is True
    assert r1["is_baseline"] is False
    assert r1["has_source"] is False


def test_create_release(client):
    r = client.post("/api/releases", json={"name": "R2", "copy_from_active": False}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert "R2" in {x["name"] for x in _releases(client)["releases"]}


def test_create_duplicate_release_409(client):
    assert client.post("/api/releases", json={"name": "R1"}, headers=AUTH).status_code == 409


def test_create_release_baselines_previous(client):
    # Creating R2 with baseline_previous freezes R1 into a baseline.
    client.post("/api/releases", json={"name": "R2", "baseline_previous": True}, headers=AUTH)
    rels = _releases(client)["releases"]
    r1 = next(r for r in rels if r["name"] == "R1")
    assert r1["is_baseline"] is True
    assert r1["selectable"] is False


def test_activate_release(client):
    client.post("/api/releases", json={"name": "R2"}, headers=AUTH)
    rid = _id_of(client, "R1")
    r = client.post(f"/api/releases/{rid}/activate", headers=AUTH)
    assert r.json()["active_release"] == "R1"
    assert _releases(client)["active_release_id"] == rid


def test_rename_release(client):
    rid = _id_of(client, "R1")
    assert client.patch(f"/api/releases/{rid}", json={"name": "R1b"}, headers=AUTH).status_code == 200
    assert "R1b" in {r["name"] for r in _releases(client)["releases"]}


def test_delete_release(client):
    client.post("/api/releases", json={"name": "R2"}, headers=AUTH)
    rid = _id_of(client, "R2")
    assert client.delete(f"/api/releases/{rid}", headers=AUTH).status_code == 200
    assert "R2" not in {r["name"] for r in _releases(client)["releases"]}


def test_rename_unknown_release_409(client):
    assert client.patch("/api/releases/9999", json={"name": "x"}, headers=AUTH).status_code == 409


def test_view_only_blocks_release_writes(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        assert c.get("/api/releases", headers=AUTH).status_code == 200
        assert c.post("/api/releases", json={"name": "R9"}, headers=AUTH).status_code == 409
