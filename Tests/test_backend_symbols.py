"""
Phase 1 — symbols router tests: fuzzy candidate lookup for the match-picker,
backed by ELF symbols stored in the DB and keyed to the active release's ELF.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "sym-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ELF_HASH = "deadbeef"

FUNCTIONS = ["compute_crc", "Engine_Update", "Sensor_Read", "Sensor_Calibrate"]
GLOBALS = {"g_engine_state": "int", "g_sensor_value": "uint32_t"}


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path,
            layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1", "elf_hash": ELF_HASH, "elf_path": "/tmp/x.elf"}],
        )
        db.register_elf(ELF_HASH, "/tmp/x.elf", "test")
        db.bulk_insert_functions(ELF_HASH, [
            {"name": n, "address": 0, "size": 0, "parameters": [], "return_type": None}
            for n in FUNCTIONS
        ])
        db.bulk_insert_global_vars(ELF_HASH, GLOBALS)
        db.commit()
        db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"}, headers=AUTH)
        yield c


def test_function_candidates(client):
    body = client.get("/api/symbols?q=sensor&kind=function&limit=5", headers=AUTH).json()
    assert body["elf_hash"] == ELF_HASH
    names = [c["name"] for c in body["candidates"]]
    assert "Sensor_Read" in names and "Sensor_Calibrate" in names
    # Scores are present and ordered descending.
    scores = [c["score"] for c in body["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > 50


def test_variable_candidates(client):
    body = client.get("/api/symbols?q=engine_state&kind=variable", headers=AUTH).json()
    names = [c["name"] for c in body["candidates"]]
    assert "g_engine_state" in names


def test_any_kind_searches_both_pools(client):
    body = client.get("/api/symbols?q=engine", headers=AUTH).json()
    names = [c["name"] for c in body["candidates"]]
    assert "Engine_Update" in names
    assert "g_engine_state" in names


def test_explicit_elf_hash(client):
    body = client.get(f"/api/symbols?q=crc&kind=function&elf_hash={ELF_HASH}", headers=AUTH).json()
    assert "compute_crc" in [c["name"] for c in body["candidates"]]


def test_no_elf_returns_empty_not_error():
    # A project whose active release has no ELF → empty candidates, 200.
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p2.arch")
        db = make_project_db(path, layout=[("TC. ID", "Static Text", True)],
                             models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            body = c.get("/api/symbols?q=anything", headers=AUTH).json()
            assert body["elf_hash"] is None
            assert body["candidates"] == []


def test_symbols_available_in_view_only(client, project_path):
    # Fuzzy lookup is a read — must work in view-only too.
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        body = c.get("/api/symbols?q=crc&kind=function", headers=AUTH).json()
        assert "compute_crc" in [x["name"] for x in body["candidates"]]


def test_query_required(client):
    assert client.get("/api/symbols", headers=AUTH).status_code == 422
