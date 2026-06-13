"""
Phase 1 — the long-running job kinds: fuzzy_rematch, build_mind_map,
parse_elf, generate_tests. Each runs through the JobManager (start → poll) and
its persisted effect is verified through the API / DB.
"""
import json
import os
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic import Logic_AI_Providers as providers
from Tests.test_helpers import make_project_db

TOKEN = "jobs-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SAMPLE_ELF = os.path.abspath("Tests/Resources/sample.elf")


def _wait(client, job_id, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        b = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if b["status"] in ("done", "failed", "cancelled"):
            return b
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} timed out")


def _run(client, kind, params):
    r = client.post(f"/api/jobs/{kind}", json=params, headers=AUTH)
    assert r.status_code == 202, r.text
    return _wait(client, r.json()["job_id"])


# ---------------------------------------------------------------------------
# fuzzy_rematch
# ---------------------------------------------------------------------------
def test_fuzzy_rematch_fills_match_cells():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(
            path,
            layout=[("Input Port", "Port Search", True), ("Input Port (Match)", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": [
                {"Input Port": {"text": "sensor_read"}, "Input Port (Match)": {"text": ""}},
                {"Input Port": {"text": "engine_update"}, "Input Port (Match)": {"text": ""}},
            ]}],
            releases=[{"name": "R1", "elf_hash": "h1", "elf_path": "/tmp/x.elf"}])
        db.register_elf("h1", "/tmp/x.elf", "test")
        db.bulk_insert_functions("h1", [
            {"name": n, "address": 0, "size": 0, "parameters": [], "return_type": None}
            for n in ["Sensor_Read", "Engine_Update", "Unrelated_Fn"]])
        db.set_active_release(db.get_all_releases()[0]["id"])
        db.commit(); db.close()

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "fuzzy_rematch", {})
            assert body["status"] == "done", body
            assert body["result"]["cells_changed"] == 2
            mid = c.get("/api/models", headers=AUTH).json()["models"][0]["id"]
            rows = c.get(f"/api/models/{mid}/ports", headers=AUTH).json()["rows"]
            assert rows[0]["cells"]["Input Port (Match)"]["widget_text"].startswith("Sensor_Read")
            assert rows[1]["cells"]["Input Port (Match)"]["widget_text"].startswith("Engine_Update")


def test_fuzzy_rematch_no_elf_fails():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "fuzzy_rematch", {})
            assert body["status"] == "failed"
            assert "No ELF" in body["error"]


# ---------------------------------------------------------------------------
# build_mind_map
# ---------------------------------------------------------------------------
def test_build_mind_map():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(
            path,
            layout=[("Input Port", "Port Search", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": [
                {"Input Port": {"text": "Sensor_Read"}},
            ]}],
            releases=[{"name": "R1"}])
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        db.save_release_source_files(rid, [
            ("src/sensor.c", "int Sensor_Read(void){ return 42; }\n")])
        db.commit(); db.close()

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "build_mind_map", {})
            assert body["status"] == "done", body
            assert body["result"]["maps_built"] == 1


def test_build_mind_map_no_source_fails():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.set_active_release(db.get_all_releases()[0]["id"])
        db.commit(); db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "build_mind_map", {})
            assert body["status"] == "failed"
            assert "source" in body["error"].lower()


# ---------------------------------------------------------------------------
# parse_elf
# ---------------------------------------------------------------------------
def test_parse_elf_imports_symbols():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        db.commit(); db.close()

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "parse_elf", {"file_path": SAMPLE_ELF, "release_id": rid})
            assert body["status"] == "done", body
            assert body["result"]["functions"] > 0
            ehash = body["result"]["elf_hash"]
            assert ehash
            # The symbols endpoint now resolves the active release's ELF.
            sym = c.get("/api/symbols?q=main&kind=function", headers=AUTH).json()
            assert sym["elf_hash"] == ehash


def test_parse_elf_missing_args_fails():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "parse_elf", {"file_path": SAMPLE_ELF})  # no release_id
            assert body["status"] == "failed"


def test_import_symbols_autodetects_elf():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        db.commit(); db.close()

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "import_symbols", {"file_path": SAMPLE_ELF, "release_id": rid})
            assert body["status"] == "done", body
            assert body["result"]["kind"] == "elf"
            assert body["result"]["functions"] > 0


def test_import_symbols_rejects_unknown_type():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        junk = os.path.join(d, "thing.bin")
        with open(junk, "wb") as f:
            f.write(b"not elf not json")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        db.commit(); db.close()

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "import_symbols", {"file_path": junk, "release_id": rid})
            assert body["status"] == "failed", body


# ---------------------------------------------------------------------------
# generate_tests (faked provider, no network)
# ---------------------------------------------------------------------------
HLT_MD = """\
# Test Case Design - Arch_A

## Test Case: TC_001
Given the sensor is active when read then it returns a value.

## Test Case: TC_002
Given the engine is off when updated then nothing happens.
"""


def test_generate_tests_writes_output(monkeypatch):
    def fake_generate(provider_id, model, messages, system_prompt=None,
                      stream_cb=None, stop_check=None):
        return "## Low-Level Steps\n1. do a thing\n"
    monkeypatch.setattr(providers, "generate", fake_generate)

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.set_active_release(db.get_all_releases()[0]["id"])
        db.commit(); db.close()

        hlt_path = os.path.join(d, "Arch_A_HLT.md")
        with open(hlt_path, "w") as f:
            f.write(HLT_MD)

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "generate_tests", {
                "provider_id": "anthropic", "model": "claude-3-5-haiku-latest",
                "hlt_path": hlt_path})
            assert body["status"] == "done", body
            assert body["result"]["cases"] == 2
            assert os.path.exists(body["result"]["output_path"])


def test_generate_tests_requires_args():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(path, layout=[("Input Port", "Port Search", True)],
                             models=[{"name": "A", "status": "In Work", "rows": []}],
                             releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            body = _run(c, "generate_tests", {"provider_id": "anthropic"})
            assert body["status"] == "failed"


def test_new_job_kinds_registered():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        kinds = c.get("/api/jobs", headers=AUTH).json()["kinds"]
        for k in ("fuzzy_rematch", "build_mind_map", "generate_tests", "parse_elf"):
            assert k in kinds
