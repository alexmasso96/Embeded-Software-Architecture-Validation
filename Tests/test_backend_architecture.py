"""
Phase 1 — architecture / Workspace router tests.

Exercises models (list/create/patch/activate), the column schema, and paged
port rows with single-cell edits, plus the view-only write guard. Builds the
project with make_project_db, then opens it through the API.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "arch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

LAYOUT = [
    ("TC. ID", "Static Text", True, 120),
    ("Input Port", "Port Search Column", True, 200),
    ("Review Status", "Review Status", True, 120),
]


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path,
            layout=[(c[0], c[1], c[2]) for c in LAYOUT],
            models=[
                {"name": "Arch_A", "status": "In Work", "rows": [
                    {"TC. ID": {"text": "TC_001"},
                     "Input Port": {"text": "p_speed"},
                     "Review Status": {"text": "Not Reviewed", "widget_text": "Not Reviewed"}},
                    {"TC. ID": {"text": "TC_002"},
                     "Input Port": {"text": "p_torque"},
                     "Review Status": {"text": "Reviewed", "widget_text": "Reviewed"}},
                ]},
                {"name": "Arch_B", "status": "Released", "rows": []},
            ],
        )
        db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    c = TestClient(app)
    with c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        c.project_path = project_path
        yield c


@pytest.fixture()
def view_client(project_path):
    app = create_app(token=TOKEN)
    c = TestClient(app)
    with c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        yield c


def _models(client):
    return client.get("/api/models", headers=AUTH).json()


def _id_of(client, name):
    return next(m["id"] for m in _models(client)["models"] if m["name"] == name)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def test_list_models(client):
    body = _models(client)
    names = {m["name"]: m for m in body["models"]}
    assert set(names) == {"Arch_A", "Arch_B"}
    assert names["Arch_A"]["row_count"] == 2
    assert names["Arch_B"]["row_count"] == 0
    assert body["active_model_id"] is not None


def test_create_model(client):
    r = client.post("/api/models", json={"name": "Arch_C", "status": "In Work"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert "Arch_C" in {m["name"] for m in _models(client)["models"]}


def test_create_model_copy_from(client):
    src = _id_of(client, "Arch_A")
    r = client.post("/api/models", json={"name": "Arch_A_copy", "copy_from_id": src}, headers=AUTH)
    assert r.status_code == 200
    new_id = r.json()["id"]
    # Copied rows carried over.
    assert client.get(f"/api/models/{new_id}/ports", headers=AUTH).json()["total"] == 2


def test_patch_model_rename_and_status(client):
    mid = _id_of(client, "Arch_B")
    r = client.patch(f"/api/models/{mid}", json={"name": "Arch_B2", "status": "Retired"}, headers=AUTH)
    assert r.json()["name"] == "Arch_B2"
    assert r.json()["status"] == "Retired"


def test_soft_delete_and_restore(client):
    mid = _id_of(client, "Arch_B")
    client.patch(f"/api/models/{mid}", json={"is_deleted": True}, headers=AUTH)
    assert "Arch_B" not in {m["name"] for m in _models(client)["models"]}
    # include_deleted surfaces it again.
    allm = client.get("/api/models?include_deleted=true", headers=AUTH).json()["models"]
    assert any(m["name"] == "Arch_B" and m["is_deleted"] for m in allm)
    client.patch(f"/api/models/{mid}", json={"is_deleted": False}, headers=AUTH)
    assert "Arch_B" in {m["name"] for m in _models(client)["models"]}


def test_activate_model(client):
    mid = _id_of(client, "Arch_B")
    r = client.post(f"/api/models/{mid}/activate", headers=AUTH)
    assert r.json()["active_model"] == "Arch_B"
    assert _models(client)["active_model_id"] == mid


def test_patch_unknown_model_409(client):
    assert client.patch("/api/models/9999", json={"name": "x"}, headers=AUTH).status_code == 409


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------
def test_get_columns(client):
    cols = client.get("/api/columns", headers=AUTH).json()["columns"]
    assert [c["name"] for c in cols] == ["TC. ID", "Input Port", "Review Status"]
    assert cols[1]["type"] == "Port Search Column"


def test_put_columns(client):
    new_cols = {"columns": [
        {"name": "TC. ID", "type": "Static Text", "visible": True, "width": 150},
        {"name": "Notes", "type": "Static Text", "visible": True, "width": 300},
    ]}
    r = client.put("/api/columns", json=new_cols, headers=AUTH)
    assert [c["name"] for c in r.json()["columns"]] == ["TC. ID", "Notes"]
    assert r.json()["columns"][0]["width"] == 150


# ---------------------------------------------------------------------------
# Ports (rows)
# ---------------------------------------------------------------------------
def test_get_ports_paged(client):
    mid = _id_of(client, "Arch_A")
    body = client.get(f"/api/models/{mid}/ports?offset=1&limit=1", headers=AUTH).json()
    assert body["total"] == 2
    assert len(body["rows"]) == 1
    assert body["rows"][0]["row_index"] == 1
    assert body["rows"][0]["cells"]["Input Port"]["text"] == "p_torque"


def test_patch_port_cell(client):
    mid = _id_of(client, "Arch_A")
    r = client.patch(f"/api/models/{mid}/ports/0",
                     json={"updates": {"Review Status": "Reviewed", "Input Port": "p_renamed"}},
                     headers=AUTH)
    cells = r.json()["cells"]
    assert cells["Input Port"]["text"] == "p_renamed"
    # widget_text mirrored for the dropdown-style cell that had it.
    assert cells["Review Status"]["text"] == "Reviewed"
    assert cells["Review Status"]["widget_text"] == "Reviewed"
    # Persisted.
    again = client.get(f"/api/models/{mid}/ports?offset=0&limit=1", headers=AUTH).json()
    assert again["rows"][0]["cells"]["Input Port"]["text"] == "p_renamed"


def test_patch_port_full_cell_dict(client):
    mid = _id_of(client, "Arch_A")
    r = client.patch(f"/api/models/{mid}/ports/0",
                     json={"updates": {"Input Port": {"text": "p_x", "user_changed": True}}},
                     headers=AUTH)
    cell = r.json()["cells"]["Input Port"]
    assert cell == {"text": "p_x", "user_changed": True}


def test_add_and_delete_port(client):
    mid = _id_of(client, "Arch_A")
    r = client.post(f"/api/models/{mid}/ports",
                    json={"updates": {"TC. ID": "TC_999"}}, headers=AUTH)
    assert r.json()["total"] == 3
    assert r.json()["row_index"] == 2
    # Delete row 0 → re-indexes to 2 rows.
    d = client.delete(f"/api/models/{mid}/ports/0", headers=AUTH)
    assert d.json()["total"] == 2
    rows = client.get(f"/api/models/{mid}/ports", headers=AUTH).json()["rows"]
    assert [r["row_index"] for r in rows] == [0, 1]


def test_patch_unknown_row_409(client):
    mid = _id_of(client, "Arch_A")
    assert client.patch(f"/api/models/{mid}/ports/99",
                        json={"updates": {"TC. ID": "x"}}, headers=AUTH).status_code == 409


# ---------------------------------------------------------------------------
# View-only write guard
# ---------------------------------------------------------------------------
def test_view_only_blocks_writes(view_client):
    mid = next(m["id"] for m in view_client.get("/api/models", headers=AUTH).json()["models"])
    # Reads work.
    assert view_client.get(f"/api/models/{mid}/ports", headers=AUTH).status_code == 200
    # Writes refused with 409.
    assert view_client.post("/api/models", json={"name": "X"}, headers=AUTH).status_code == 409
    assert view_client.patch(f"/api/models/{mid}/ports/0",
                             json={"updates": {"TC. ID": "y"}}, headers=AUTH).status_code == 409
