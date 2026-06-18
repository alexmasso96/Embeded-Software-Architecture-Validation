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
            releases=[{"name": "R1", "description": "first",
                       "rows": [{"TC. ID": {"text": "1"}},
                                {"TC. ID": {"text": "2"}}]}],
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


def _lineage(client):
    return client.get("/api/releases/lineage", headers=AUTH).json()


def test_branch_release(client):
    rid = _id_of(client, "R1")
    r = client.post(f"/api/releases/{rid}/branch",
                    json={"name": "R1_fork", "description": "forked"}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "R1_fork"
    assert body["parent_release_name"] == "R1"
    # The new branch becomes the active release.
    assert _releases(client)["active_release_id"] == body["id"]


def test_branch_clones_rows(client):
    rid = _id_of(client, "R1")
    fork = client.post(f"/api/releases/{rid}/branch", json={"name": "R1_fork"},
                       headers=AUTH).json()
    node = next(n for n in _lineage(client)["nodes"] if n["id"] == fork["id"])
    # R1 has two snapshot rows; the fork inherits them.
    assert node["row_count"] == 2


def test_branch_duplicate_name_409(client):
    rid = _id_of(client, "R1")
    assert client.post(f"/api/releases/{rid}/branch", json={"name": "R1"},
                       headers=AUTH).status_code == 409


def test_branch_unknown_release_409(client):
    assert client.post("/api/releases/9999/branch", json={"name": "x"},
                       headers=AUTH).status_code == 409


def test_lineage_grid_and_parent(client):
    rid = _id_of(client, "R1")
    client.post(f"/api/releases/{rid}/branch", json={"name": "R1_fork"}, headers=AUTH)
    body = _lineage(client)
    assert body["active_release_id"] is not None
    nodes = {n["name"]: n for n in body["nodes"]}
    assert "R1" in nodes and "R1_fork" in nodes
    # Every node has integer grid coordinates normalised to a non-negative origin.
    for n in body["nodes"]:
        assert isinstance(n["grid_x"], int) and n["grid_x"] >= 0
        assert isinstance(n["grid_y"], int) and n["grid_y"] >= 0
    # The fork is a mainline child: same column, one row up from its parent.
    assert nodes["R1_fork"]["grid_x"] == nodes["R1"]["grid_x"]
    assert nodes["R1_fork"]["grid_y"] == nodes["R1"]["grid_y"] - 1


def test_lineage_includes_deleted_with_stable_coords(client):
    # Freeze R1 into a baseline, then soft-delete the baseline, and confirm the
    # deleted node still appears in the lineage at its original grid cell (so the
    # UI can leave it as a gap). Baselines soft-delete; plain releases hard-delete.
    rid = _id_of(client, "R1")
    client.post(f"/api/releases/{rid}/branch", json={"name": "keep"}, headers=AUTH)
    snap = client.post("/api/baselines", json={"name": "snap", "release_id": rid},
                       headers=AUTH).json()
    before = {n["name"]: (n["grid_x"], n["grid_y"]) for n in _lineage(client)["nodes"]}
    assert "snap" in before
    assert client.delete(f"/api/releases/{snap['id']}", headers=AUTH).status_code == 200
    after = {n["name"]: n for n in _lineage(client)["nodes"]}
    # Soft-deleted baseline is still present, flagged, and at its original cell.
    assert "snap" in after and after["snap"]["is_deleted"] is True
    assert (after["snap"]["grid_x"], after["snap"]["grid_y"]) == before["snap"]
    # The surviving branch did not shift.
    assert (after["keep"]["grid_x"], after["keep"]["grid_y"]) == before["keep"]


def test_restore_soft_deleted_baseline(client):
    rid = _id_of(client, "R1")
    snap = client.post("/api/baselines", json={"name": "snap", "release_id": rid},
                       headers=AUTH).json()
    client.delete(f"/api/releases/{snap['id']}", headers=AUTH)
    # Default list hides it; lineage still shows it flagged deleted.
    assert "snap" not in {r["name"] for r in _releases(client)["releases"]}
    assert client.post(f"/api/releases/{snap['id']}/restore", headers=AUTH).status_code == 200
    assert "snap" in {r["name"] for r in _releases(client)["releases"]}


def test_lineage_matches_design_example(tmp_path):
    # Reproduce the design doc's worked example: a root with a mainline successor
    # (up) and a baseline child (left). Coordinates must match exactly.
    path = os.path.join(tmp_path, "lin.arch")
    db = make_project_db(
        path,
        layout=[("TC. ID", "Static Text", True)],
        models=[{"name": "A", "status": "In Work", "rows": []}],
        releases=[
            {"name": "mainline_v1.0", "description": "root"},
            {"name": "snapshot1", "is_baseline": True,
             "parent_release_name": "mainline_v1.0"},
            {"name": "mainline_v2.0", "parent_release_name": "mainline_v1.0"},
        ],
    )
    db.close()
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
        nodes = {n["name"]: n for n in c.get("/api/releases/lineage", headers=AUTH).json()["nodes"]}
    assert (nodes["mainline_v1.0"]["grid_x"], nodes["mainline_v1.0"]["grid_y"]) == (1, 1)
    assert (nodes["mainline_v2.0"]["grid_x"], nodes["mainline_v2.0"]["grid_y"]) == (1, 0)
    assert (nodes["snapshot1"]["grid_x"], nodes["snapshot1"]["grid_y"]) == (0, 1)


def test_branch_blocked_in_view_only(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        rid = next(r["id"] for r in c.get("/api/releases", headers=AUTH).json()["releases"]
                   if r["name"] == "R1")
        assert c.get("/api/releases/lineage", headers=AUTH).status_code == 200
        assert c.post(f"/api/releases/{rid}/branch", json={"name": "nope"},
                      headers=AUTH).status_code == 409


def test_view_only_blocks_release_writes(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        assert c.get("/api/releases", headers=AUTH).status_code == 200
        assert c.post("/api/releases", json={"name": "R9"}, headers=AUTH).status_code == 409
