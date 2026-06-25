"""Column-layout logic + customizer API (rename cell-migration, delete cleanup,
locked-column computation, validation)."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic.Logic_Column_Layout import (
    compute_locked_columns, validate_layout, migrate_rows, diff_layout,
    is_dependent, leader_of, ADDABLE_TYPES,
)
from Tests.test_helpers import make_project_db

TOKEN = "col-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

LAYOUT = [
    ("TC. ID", "Static Text", True),
    ("Input Port", "Port Search", True),
    ("Input Port (Match)", "Static Text", True),
    ("Review Status", "Review Status", True),
    ("Port State", "PortStateColumn", True),
    ("Notes", "Static Text", True),
]


# ---------------------------------------------------------------------------
# Logic layer
# ---------------------------------------------------------------------------
def test_is_dependent_and_leader():
    assert is_dependent("Input Port (Match)")
    assert is_dependent("Port State")
    assert not is_dependent("Input Port")
    assert leader_of("Input Port (Cyclic)") == "Input Port"
    assert leader_of("TC. ID") is None


def test_validate_layout_rules():
    validate_layout(LAYOUT)  # ok
    with pytest.raises(ValueError):
        validate_layout([("Input Port", "Port Search", True)])  # TC. ID not first
    with pytest.raises(ValueError):
        validate_layout([("TC. ID", "Static Text", True), ("X", "Static Text", True),
                         ("X", "Static Text", True)])  # duplicate
    with pytest.raises(ValueError):
        validate_layout([("TC. ID", "Static Text", True), ("A | B", "Static Text", True)])  # pipe


def test_compute_locked_columns():
    rows = [
        {"Review Status": {"text": "Reviewed"}, "Input Port": {"text": "p_a"}, "Notes": {"text": ""}},
        {"Review Status": {"text": "Not Reviewed"}, "Input Port": {"text": "p_b"}, "Notes": {"text": "x"}},
    ]
    locked = compute_locked_columns(LAYOUT, rows)
    assert {"TC. ID", "Port State", "Review Status"} <= locked
    assert "Input Port" in locked          # has data in the reviewed row
    assert "Notes" not in locked           # only had data in the non-reviewed row


def test_migrate_rows_rename_and_remove():
    rows = [{"Input Port": {"text": "p"}, "Notes": {"text": "n"}, "Gone": {"text": "g"}}]
    migrate_rows(rows, {"Input Port": "In"}, {"Gone"})
    assert rows[0]["In"]["text"] == "p"
    assert "Input Port" not in rows[0]
    assert "Gone" not in rows[0]
    assert rows[0]["Notes"]["text"] == "n"


def test_diff_layout_removed_excludes_renames():
    removed = diff_layout(["TC. ID", "A", "B"], ["TC. ID", "Anew"], {"A": "Anew"})
    assert removed == {"B"}  # A was renamed (not removed), B is gone


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(
            path, layout=LAYOUT,
            models=[
                {"name": "M1", "status": "In Work", "rows": [
                    {"Input Port": {"text": "p_a"}, "Notes": {"text": "n1"},
                     "Review Status": {"text": "Reviewed"}},
                ]},
                {"name": "M2", "status": "In Work", "rows": [
                    {"Input Port": {"text": "p_b"}, "Notes": {"text": "n2"}},
                ]},
            ],
            releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            yield c


def test_editor_endpoint(client):
    r = client.get("/api/columns/editor", headers=AUTH).json()
    assert [c["name"] for c in r["columns"]][0] == "TC. ID"
    assert "Port State" in r["locked"] and "TC. ID" in r["locked"]
    assert "Input Port" in r["locked"]      # M1 row is Reviewed with data
    assert r["addable_types"] == ADDABLE_TYPES


def test_put_rename_migrates_cells_in_all_models(client):
    cols = [
        {"name": "TC. ID", "type": "Static Text", "visible": True, "width": 80},
        {"name": "InPort", "type": "Port Search", "visible": True, "width": 120},
        {"name": "InPort (Match)", "type": "Static Text", "visible": True, "width": 120},
        {"name": "Review Status", "type": "Review Status", "visible": True, "width": 100},
        {"name": "Port State", "type": "PortStateColumn", "visible": True, "width": 100},
        {"name": "Notes", "type": "Static Text", "visible": True, "width": 100},
    ]
    body = {"columns": cols, "renames": {"Input Port": "InPort", "Input Port (Match)": "InPort (Match)"}}
    assert client.put("/api/columns", json=body, headers=AUTH).status_code == 200

    # both models' rows now carry the cell under the NEW key
    for mid_name, port in [("M1", "p_a"), ("M2", "p_b")]:
        models = client.get("/api/models", headers=AUTH).json()["models"]
        mid = next(m["id"] for m in models if m["name"] == mid_name)
        rows = client.get(f"/api/models/{mid}/ports", headers=AUTH).json()["rows"]
        assert rows[0]["cells"]["InPort"]["text"] == port
        assert "Input Port" not in rows[0]["cells"]


def test_put_delete_strips_cells(client):
    cols = [
        {"name": "TC. ID", "type": "Static Text", "visible": True, "width": 80},
        {"name": "Input Port", "type": "Port Search", "visible": True, "width": 120},
        {"name": "Input Port (Match)", "type": "Static Text", "visible": True, "width": 120},
        {"name": "Review Status", "type": "Review Status", "visible": True, "width": 100},
        {"name": "Port State", "type": "PortStateColumn", "visible": True, "width": 100},
        # "Notes" removed
    ]
    assert client.put("/api/columns", json={"columns": cols}, headers=AUTH).status_code == 200
    models = client.get("/api/models", headers=AUTH).json()["models"]
    mid = next(m["id"] for m in models if m["name"] == "M1")
    rows = client.get(f"/api/models/{mid}/ports", headers=AUTH).json()["rows"]
    assert "Notes" not in rows[0]["cells"]


def test_visibility_tristate_roundtrip(client):
    """Init/Cyclic columns persist a 3-state visibility: True/False/None(Auto)."""
    cols = [
        {"name": "TC. ID", "type": "Static Text", "visible": True, "width": 80},
        {"name": "Input Port", "type": "Port Search", "visible": False, "width": 120},
        {"name": "Input Port (Match)", "type": "Static Text", "visible": None, "width": 120},
        {"name": "Review Status", "type": "Review Status", "visible": True, "width": 100},
        {"name": "Port State", "type": "PortStateColumn", "visible": True, "width": 100},
    ]
    assert client.put("/api/columns", json={"columns": cols}, headers=AUTH).status_code == 200
    out = client.get("/api/columns", headers=AUTH).json()["columns"]
    by = {c["name"]: c["visible"] for c in out}
    assert by["TC. ID"] is True
    assert by["Input Port"] is False
    assert by["Input Port (Match)"] is None  # Auto survives the round-trip


def test_put_rejects_bad_layout(client):
    # TC. ID not first → 409
    cols = [{"name": "Input Port", "type": "Port Search", "visible": True, "width": 120}]
    assert client.put("/api/columns", json={"columns": cols}, headers=AUTH).status_code == 409


def test_put_view_only_blocked():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=LAYOUT,
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            cols = [{"name": "TC. ID", "type": "Static Text", "visible": True, "width": 80}]
            assert client_put_blocked(c, cols)


def client_put_blocked(c, cols):
    return c.put("/api/columns", json={"columns": cols}, headers=AUTH).status_code == 409
