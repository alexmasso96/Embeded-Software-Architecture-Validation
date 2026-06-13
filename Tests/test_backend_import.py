"""
Phase 1 — import primitives: bulk row append + stateless file analysis.

The interactive import is a Phase-2 wizard composed from these primitives plus
the fuzzy_rematch job; there is no monolithic server-side import.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "imp-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client_with_project():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(
            path,
            layout=[("Input Port", "Port Search", True), ("Notes", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            yield c, d


# ---------------------------------------------------------------------------
# Bulk row append
# ---------------------------------------------------------------------------
def test_bulk_append(client_with_project):
    c, _ = client_with_project
    mid = c.get("/api/models", headers=AUTH).json()["models"][0]["id"]
    body = {"rows": [
        {"Input Port": "p_a", "Notes": "first"},
        {"Input Port": "p_b"},
        {"Input Port": {"text": "p_c", "user_changed": True}},
    ]}
    r = c.post(f"/api/models/{mid}/ports/bulk", json=body, headers=AUTH).json()
    assert r["added"] == 3
    assert r["first_row_index"] == 0
    rows = c.get(f"/api/models/{mid}/ports", headers=AUTH).json()["rows"]
    assert [row["cells"]["Input Port"]["text"] for row in rows] == ["p_a", "p_b", "p_c"]
    assert rows[0]["cells"]["Notes"]["text"] == "first"
    assert rows[2]["cells"]["Input Port"]["user_changed"] is True


def test_bulk_append_view_only_blocked():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            mid = c.get("/api/models", headers=AUTH).json()["models"][0]["id"]
            assert c.post(f"/api/models/{mid}/ports/bulk",
                          json={"rows": [{"Input Port": "x"}]}, headers=AUTH).status_code == 409


# ---------------------------------------------------------------------------
# File analysis
# ---------------------------------------------------------------------------
def test_analyze_excel(client_with_project):
    c, d = client_with_project
    import pandas as pd
    xlsx = os.path.join(d, "book.xlsx")
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame({"A": [1]}).to_excel(w, sheet_name="Engine", index=False)
        pd.DataFrame({"A": [2]}).to_excel(w, sheet_name="Sensor", index=False)
    body = c.post("/api/import/analyze", json={"file_path": xlsx}, headers=AUTH).json()
    assert body["format"] == "excel"
    assert set(body["sheets"]) == {"Engine", "Sensor"}


def test_analyze_rhapsody_csv(client_with_project):
    c, d = client_with_project
    csv = os.path.join(d, "export.csv")
    # Rhapsody export: a '::'-delimited path column (>=3 segments) + a port column.
    with open(csv, "w") as f:
        # Rhapsody path: model name is the 3rd segment; needs >=4 segments.
        f.write("Path,Port,Required Interface\n")
        f.write("Root::P10_SW_Arch_Public::EngineCtl::op1,p_speed,IFace_A\n")
        f.write("Root::P10_SW_Arch_Public::EngineCtl::op2,p_torque,IFace_B\n")
        f.write("Root::P10_SW_Arch_Public::SensorMgr::op1,p_temp,IFace_C\n")
    body = c.post("/api/import/analyze", json={"file_path": csv}, headers=AUTH).json()
    assert body["format"] == "rhapsody"
    assert body["path_col"] == "Path"
    names = {m["name"] for m in body["models"]}
    assert "EngineCtl" in names and "SensorMgr" in names


def test_analyze_plain_csv(client_with_project):
    c, d = client_with_project
    csv = os.path.join(d, "plain.csv")
    with open(csv, "w") as f:
        f.write("a,b\n1,2\n")
    body = c.post("/api/import/analyze", json={"file_path": csv}, headers=AUTH).json()
    assert body["format"] == "csv"


def test_analyze_missing_file_404(client_with_project):
    c, _ = client_with_project
    assert c.post("/api/import/analyze",
                  json={"file_path": "/no/such/file.xlsx"}, headers=AUTH).status_code == 404
