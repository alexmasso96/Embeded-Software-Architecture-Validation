"""
Source-Level Test Code Injection — backend integration tests.

Exercises the full router surface against a real .arch via TestClient: test
project CRUD, helper-file import, injection hooks, fuzzy resolve/shift, export
(modified + reconstruct), and the build runner / settings. The active release is
seeded with production source so the injection paths have something to anchor to.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic.Logic_Database import ProjectDatabase
from Tests.test_helpers import make_project_db

TOKEN = "inject-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

MAIN_C = "\n".join([
    "int main(void)",
    "{",
    "    int x = 1;",
    "    int y = 2;",
    "    foo();",
    "    return 0;",
    "}",
    "",
])


@pytest.fixture()
def project_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path,
            layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1", "description": "first",
                       "rows": [{"TC. ID": {"text": "1"}}]}],
        )
        # Seed the active release with production source to inject into.
        rid = db.get_all_releases()[0]["id"] if hasattr(db, "get_all_releases") else None
        if rid is None:
            # Fall back: query the releases table directly.
            rid = db.execute("SELECT id FROM releases ORDER BY id LIMIT 1").fetchone()[0]
        db.save_release_source_files(rid, [("src/main.c", MAIN_C)])
        db.commit()
        db.close()
        yield path


@pytest.fixture()
def client(project_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": project_path, "mode": "exclusive"},
               headers=AUTH)
        yield c


def _new_project(client, name="MyTests"):
    r = client.post("/api/injection/projects", json={"name": name}, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# -- test projects ------------------------------------------------------
def test_create_list_delete_project(client):
    pid = _new_project(client)
    listing = client.get("/api/injection/projects", headers=AUTH).json()
    assert any(p["id"] == pid and p["name"] == "MyTests"
               for p in listing["projects"])
    r = client.delete(f"/api/injection/projects/{pid}", headers=AUTH)
    assert r.status_code == 200
    listing = client.get("/api/injection/projects", headers=AUTH).json()
    assert all(p["id"] != pid for p in listing["projects"])


def test_create_empty_name_rejected(client):
    r = client.post("/api/injection/projects", json={"name": "  "}, headers=AUTH)
    assert r.status_code == 409


# -- helper-file import -------------------------------------------------
def test_import_and_read_helper_files(client):
    pid = _new_project(client)
    r = client.post(
        f"/api/injection/projects/{pid}/import",
        json={"files": [
            {"rel_path": "helpers/stub.c", "content": "int stub(void){return 0;}"},
            {"rel_path": "helpers/stub.h", "content": "int stub(void);"},
            {"rel_path": "README.md", "content": "ignored"},  # non-source skipped
        ]},
        headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2
    files = client.get(f"/api/injection/projects/{pid}/files", headers=AUTH).json()
    names = {f["rel_path"] for f in files["files"]}
    assert names == {"helpers/stub.c", "helpers/stub.h"}
    content = client.get(
        f"/api/injection/projects/{pid}/files/content",
        params={"rel_path": "helpers/stub.h"}, headers=AUTH).json()
    assert content["content"] == "int stub(void);"


# -- production source tree --------------------------------------------
def test_source_files_and_content(client):
    files = client.get("/api/injection/source/files", headers=AUTH).json()
    assert any(f["rel_path"] == "src/main.c" for f in files["files"])
    content = client.get("/api/injection/source/content",
                         params={"rel_path": "src/main.c"}, headers=AUTH).json()
    assert "int main(void)" in content["content"]


# -- injection hooks + resolution --------------------------------------
def _add_hook(client, pid, **kw):
    body = {"src_file_path": "src/main.c", "function_name": "main",
            "line_above_code": "int x = 1;", "line_below_code": "int y = 2;",
            "injected_code": "CHECK(x);"}
    body.update(kw)
    r = client.post(f"/api/injection/projects/{pid}/injections", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()["injection_id"]


def test_add_update_list_injection(client):
    pid = _new_project(client)
    iid = _add_hook(client, pid)
    rows = client.get(f"/api/injection/projects/{pid}/injections", headers=AUTH).json()
    hook = next(h for h in rows["injections"] if h["id"] == iid)
    assert hook["confidence"] == 4           # both anchors found, in order
    assert hook["resolved_index"] == 3

    # Update the snippet via the same endpoint (injection_id present).
    r = client.post(f"/api/injection/projects/{pid}/injections",
                    json={"injection_id": iid, "src_file_path": "src/main.c",
                          "function_name": "main", "line_above_code": "int x = 1;",
                          "line_below_code": "int y = 2;",
                          "injected_code": "LOG();"}, headers=AUTH)
    assert r.status_code == 200
    rows = client.get(f"/api/injection/projects/{pid}/injections", headers=AUTH).json()
    assert next(h for h in rows["injections"] if h["id"] == iid)["injected_code"] == "LOG();"


def test_resolve_conflict(client):
    r = client.post("/api/injection/resolve",
                    json={"src_file_path": "src/main.c",
                          "line_above_code": "GONE;", "line_below_code": "MISSING;"},
                    headers=AUTH)
    assert r.status_code == 200
    assert r.json()["index"] is None and r.json()["confidence"] == 0


def test_shift_within_and_out_of_function(client):
    pid = _new_project(client)
    iid = _add_hook(client, pid)  # index 3 (between x and y)
    # First shift up stays inside the function body (index 2).
    r = client.post(f"/api/injection/injections/{iid}/shift",
                    json={"direction": "up"}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] and r.json()["index"] == 2
    # Keep shifting up; the block must eventually be refused at the opening brace
    # rather than escaping the function. Bound the loop so a logic bug can't hang.
    refused = False
    for _ in range(6):
        r = client.post(f"/api/injection/injections/{iid}/shift",
                        json={"direction": "up"}, headers=AUTH)
        if r.status_code == 409:
            refused = True
            break
        assert r.json()["index"] >= 1   # never lands on/above the signature line
    assert refused, "shift never hit the function boundary"


def test_delete_injection(client):
    pid = _new_project(client)
    iid = _add_hook(client, pid)
    r = client.delete(f"/api/injection/injections/{iid}", headers=AUTH)
    assert r.status_code == 200
    rows = client.get(f"/api/injection/projects/{pid}/injections", headers=AUTH).json()
    assert all(h["id"] != iid for h in rows["injections"])


# -- export -------------------------------------------------------------
def test_export_modified_only(client):
    pid = _new_project(client)
    _add_hook(client, pid, injected_code="ASSERT(x>0);")
    client.post(f"/api/injection/projects/{pid}/import",
                json={"files": [{"rel_path": "helpers/t.c", "content": "void t(){}"}]},
                headers=AUTH)
    with tempfile.TemporaryDirectory() as out:
        r = client.post(f"/api/injection/projects/{pid}/export",
                        json={"mode": "modified", "out_dir": out, "overwrite": True},
                        headers=AUTH)
        assert r.status_code == 200, r.text
        injected = open(os.path.join(out, "src", "main.c")).read()
        assert "ASSERT(x>0);" in injected
        assert os.path.exists(os.path.join(out, "helpers", "t.c"))


def test_export_reconstruct(client):
    pid = _new_project(client)
    _add_hook(client, pid, injected_code="ASSERT(1);")
    with tempfile.TemporaryDirectory() as out:
        r = client.post(f"/api/injection/projects/{pid}/export",
                        json={"mode": "reconstruct", "out_dir": out, "overwrite": True},
                        headers=AUTH)
        assert r.status_code == 200, r.text
        assert os.path.exists(os.path.join(out, "src", "main.c"))


# -- build settings + runner -------------------------------------------
def test_settings_roundtrip(client):
    r = client.post("/api/injection/settings",
                    json={"terminal": "bash", "build_command": "echo hi",
                          "build_cwd": "/tmp"}, headers=AUTH)
    assert r.status_code == 200
    s = client.get("/api/injection/settings", headers=AUTH).json()
    assert s["terminal"] == "bash" and s["build_command"] == "echo hi"


def test_settings_unknown_terminal_rejected(client):
    r = client.post("/api/injection/settings", json={"terminal": "fish"}, headers=AUTH)
    assert r.status_code == 409


def test_build_argv_per_terminal():
    from backend.routers.injection import _build_argv
    assert _build_argv("cmd", "make", "C:\\proj", "") == ["cmd.exe", "/c", "make"]
    assert _build_argv("powershell", "make", "", "") == \
        ["powershell.exe", "-NoProfile", "-Command", "make"]
    assert _build_argv("bash", "make", "/proj", "") == ["bash", "-lc", "make"]
    wsl = _build_argv("wsl", "make all", "/home/u/proj", "Ubuntu")
    assert wsl[:4] == ["wsl.exe", "-d", "Ubuntu", "--"]
    assert wsl[-3:] == ["sh", "-c", "cd /home/u/proj && make all"]


@pytest.mark.skipif(sys.platform == "win32", reason="bash terminal")
def test_build_runner_streams_output():
    """The build runner fans subprocess output over the ``build`` event and ends
    with a ``done`` payload carrying the return code."""
    from backend.routers import injection as inj

    captured = []

    class FakeBus:
        def publish(self, event_type, data):
            captured.append((event_type, data))

    argv = inj._build_argv("bash", "echo BUILD_OK", "", "")
    inj._stream_build("b1", argv, "", "bash", FakeBus())

    assert captured[0][1]["event"] == "start"
    logs = [d["line"] for t, d in captured if d.get("event") == "log"]
    assert any("BUILD_OK" in line for line in logs)
    assert captured[-1][1]["event"] == "done"
    assert captured[-1][1]["returncode"] == 0


def test_build_endpoint_starts(client):
    pid = _new_project(client)
    client.post("/api/injection/settings",
                json={"terminal": "bash"}, headers=AUTH)
    r = client.post(f"/api/injection/projects/{pid}/build",
                    json={"command": "echo hi", "cwd": ""}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert "build_id" in r.json()


def test_build_no_command_rejected(client):
    pid = _new_project(client)
    r = client.post(f"/api/injection/projects/{pid}/build",
                    json={"command": "  "}, headers=AUTH)
    assert r.status_code == 409
