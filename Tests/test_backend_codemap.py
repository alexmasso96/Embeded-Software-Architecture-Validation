"""
Phase 1 — codemap + source router tests.

Builds a project with a stored CodeMap and a release source file, then exercises
the function list, depth-limited graph, function details, and source extraction.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic.Logic_Database import ProjectDatabase
from Tests.test_helpers import make_project_db

TOKEN = "cm-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

MAIN_C = """\
#include <stdio.h>

void func_c(void) {
    return;
}

int func_a(void) {
    func_c();
    return 1;
}

void func_b(void) {
}

int main(void) {
    func_a();
    func_b();
    return 0;
}
"""

CODE_MAP = {
    "functions": {
        "main": {"address": 0x1000, "size": 64, "file": "src/main.c",
                 "line_start": 17, "calls": ["func_a", "func_b"],
                 "return_type": "int", "signature": "int main(void)"},
        "func_a": {"address": 0x1100, "size": 32, "file": "src/main.c",
                   "line_start": 7, "calls": ["func_c"], "return_type": "int"},
        "func_b": {"address": 0x1200, "size": 8, "file": "src/main.c",
                   "line_start": 13, "calls": []},
        "func_c": {"address": 0x1300, "size": 8, "file": "src/main.c",
                   "line_start": 3, "calls": []},
    },
    "global_variables": {"main_status": "int", "func_a_count": "uint32_t"},
    "defines": {"MAX_LEN": "256"},
    "structures": {},
}


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path,
            layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1", "elf_hash": "h1"}],
        )
        model_id = db.get_all_models()[0]["id"]
        release_id = db.get_all_releases()[0]["id"]
        db.set_active_release(release_id)
        db.save_model_code_map(model_id, json.dumps(CODE_MAP), release_id=release_id)
        db.save_release_source_files(release_id, [("src/main.c", MAIN_C)])
        db.commit()
        db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "view"}, headers=AUTH)
        yield c


def test_codemap_summary(client):
    body = client.get("/api/codemap", headers=AUTH).json()
    assert body["function_count"] == 4
    assert set(body["functions"]) == {"main", "func_a", "func_b", "func_c"}
    assert body["global_count"] == 2
    assert body["define_count"] == 1


def test_graph_default_focus_main_depth_1(client):
    body = client.get("/api/codemap/graph", headers=AUTH).json()
    assert body["focus"] == "main"
    names = {n["name"] for n in body["nodes"]}
    # depth 1 forward from main → main, func_a, func_b (not func_c).
    assert names == {"main", "func_a", "func_b"}
    edges = {(e["source"], e["target"]) for e in body["edges"]}
    assert ("main", "func_a") in edges and ("main", "func_b") in edges
    center = next(n for n in body["nodes"] if n["name"] == "main")
    assert center["type"] == "center"


def test_graph_forward_depth_2_reaches_func_c(client):
    body = client.get("/api/codemap/graph?fn=main&fwd=2&back=1", headers=AUTH).json()
    names = {n["name"] for n in body["nodes"]}
    assert "func_c" in names
    assert ("func_a", "func_c") in {(e["source"], e["target"]) for e in body["edges"]}


def test_graph_backward_callers(client):
    # Focus func_c, look back 2 → func_a (caller) and main (caller of caller).
    body = client.get("/api/codemap/graph?fn=func_c&back=2&fwd=1", headers=AUTH).json()
    names = {n["name"] for n in body["nodes"]}
    assert {"func_c", "func_a", "main"} <= names
    caller = next(n for n in body["nodes"] if n["name"] == "func_a")
    assert caller["type"] == "caller"


def test_function_details(client):
    body = client.get("/api/codemap/function/func_a", headers=AUTH).json()
    assert body["address"] == 0x1100
    assert body["callees"] == ["func_c"]
    assert body["callers"] == ["main"]
    assert {g["name"] for g in body["globals"]} == {"func_a_count"}
    assert "func_a" in body["tooltip_html"]


def test_function_details_unknown_409(client):
    assert client.get("/api/codemap/function/nope", headers=AUTH).status_code == 409


def test_source_function_extraction(client):
    body = client.get("/api/source/function/func_a", headers=AUTH).json()
    assert body["found"] is True
    assert "int func_a(void) {" in body["source"]
    assert "func_c();" in body["source"]
    # Brace matching stops at the function's closing brace.
    assert "void func_b" not in body["source"]


def test_source_function_no_source_for_release():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p2.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        mid = db.get_all_models()[0]["id"]
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        db.save_model_code_map(mid, json.dumps(CODE_MAP), release_id=rid)
        db.commit(); db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            body = c.get("/api/source/function/main", headers=AUTH).json()
            assert body["found"] is False
            assert "not imported" in body["reason"]


def test_codemap_absent_409():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p3.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            assert c.get("/api/codemap", headers=AUTH).status_code == 409
