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


# ---------------------------------------------------------------------------
# File read (feeds the column-mapping wizard step)
# ---------------------------------------------------------------------------
def test_read_rows(client_with_project):
    c, d = client_with_project
    csv = os.path.join(d, "export.csv")
    with open(csv, "w") as f:
        f.write("Path,Port,Required Interface\n")
        f.write("Root::P10_SW_Arch_Public::EngineCtl::op1,p_speed,IFace_A\n")
        f.write("Root::P10_SW_Arch_Public::SensorMgr::op1,p_temp,IFace_C\n")
    body = c.post("/api/import/read", json={"file_path": csv}, headers=AUTH).json()
    assert body["columns"] == ["Path", "Port", "Required Interface"]
    assert body["total"] == 2
    assert body["is_rhapsody"] is True
    assert body["path_col"] == "Path"
    assert body["rows"][0]["Port"] == "p_speed"
    assert body["rows"][1]["Required Interface"] == "IFace_C"


def test_read_rows_limit(client_with_project):
    c, d = client_with_project
    csv = os.path.join(d, "plain.csv")
    with open(csv, "w") as f:
        f.write("a,b\n1,2\n3,4\n5,6\n")
    body = c.post("/api/import/read", json={"file_path": csv, "limit": 2}, headers=AUTH).json()
    assert len(body["rows"]) == 2
    assert body["rows"][0]["a"] == "1"


def test_read_missing_file_404(client_with_project):
    c, _ = client_with_project
    assert c.post("/api/import/read",
                  json={"file_path": "/no/such/file.csv"}, headers=AUTH).status_code == 404


# ---------------------------------------------------------------------------
# Rhapsody multi-model split
# ---------------------------------------------------------------------------
def _write_rhapsody_csv(path):
    with open(path, "w") as f:
        f.write("Path,Port,Required Interface,Operations\n")
        f.write("Root::P10_SW_Arch_Public::EngineCtl::p_speed,p_speed,IFace_A,op_a\n")
        f.write("Root::P10_SW_Arch_Public::EngineCtl::p_torque,p_torque,IFace_B,op_b\n")
        f.write("Root::P10_SW_Arch_Public::SensorMgr::p_temp,p_temp,IFace_C,op_c\n")
        # non-P10 row → must be skipped entirely
        f.write("Root::P20_SW_Arch_Intern::Ignored::p_x,p_x,IFace_D,op_d\n")


def test_rhapsody_split_creates_models(client_with_project):
    c, d = client_with_project
    csv = os.path.join(d, "rhap.csv")
    _write_rhapsody_csv(csv)
    body = {
        "file_path": csv,
        "col_mapping": {"Port": "Input Port", "Required Interface": "Notes"},
        "path_col": "Path",
        "required_col": "Required Interface",
    }
    r = c.post("/api/import/rhapsody", json=body, headers=AUTH).json()
    assert r["total_models"] == 2
    names = {m["name"]: m for m in r["models"]}
    assert names["EngineCtl"]["created"] is True and names["EngineCtl"]["added"] == 2
    assert names["SensorMgr"]["added"] == 1
    assert r["total_added"] == 3  # the P20 row was filtered out
    assert len(r["model_ids"]) == 2

    # the rows actually landed in the new models
    models = c.get("/api/models", headers=AUTH).json()["models"]
    eng = next(m for m in models if m["name"] == "EngineCtl")
    rows = c.get(f"/api/models/{eng['id']}/ports", headers=AUTH).json()["rows"]
    ports = sorted(row["cells"]["Input Port"]["text"] for row in rows)
    assert ports == ["p_speed", "p_torque"]


def test_rhapsody_ops_expand_into_rows(client_with_project):
    c, d = client_with_project
    csv = os.path.join(d, "rhap_ops.csv")
    with open(csv, "w") as f:
        f.write("Path,Port,Required Interface,Operations\n")
        # one port with two operations → two rows after expansion
        f.write('Root::P10_SW_Arch_Public::EngineCtl::p,p,IFace,"op1\nop2"\n')
    body = {
        "file_path": csv,
        "col_mapping": {"Port": "Input Port", "Operations": "Notes"},
        "path_col": "Path",
        "ops_col": "Operations",
        "required_col": "Required Interface",
    }
    r = c.post("/api/import/rhapsody", json=body, headers=AUTH).json()
    assert r["total_added"] == 2
    eng = next(m for m in c.get("/api/models", headers=AUTH).json()["models"]
               if m["name"] == "EngineCtl")
    rows = c.get(f"/api/models/{eng['id']}/ports", headers=AUTH).json()["rows"]
    assert sorted(row["cells"]["Notes"]["text"] for row in rows) == ["op1", "op2"]


def test_rhapsody_append_to_existing_model(client_with_project):
    c, d = client_with_project
    # First import creates EngineCtl; second appends to it (created=False).
    csv = os.path.join(d, "rhap.csv")
    _write_rhapsody_csv(csv)
    body = {"file_path": csv, "col_mapping": {"Port": "Input Port"},
            "path_col": "Path", "required_col": "Required Interface"}
    c.post("/api/import/rhapsody", json=body, headers=AUTH)
    r2 = c.post("/api/import/rhapsody", json=body, headers=AUTH).json()
    eng = next(m for m in r2["models"] if m["name"] == "EngineCtl")
    assert eng["created"] is False
    eng_model = next(m for m in c.get("/api/models", headers=AUTH).json()["models"]
                     if m["name"] == "EngineCtl")
    assert eng_model["row_count"] == 4  # 2 + 2


def test_rhapsody_view_only_blocked():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        csv = os.path.join(d, "rhap.csv")
        _write_rhapsody_csv(csv)
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            r = c.post("/api/import/rhapsody",
                       json={"file_path": csv, "col_mapping": {"Port": "Input Port"},
                             "path_col": "Path"}, headers=AUTH)
            assert r.status_code == 409
