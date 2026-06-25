"""
Phase 2 — filesystem browse router tests (dev folder picker support).

The launcher needs a read-only directory listing (browsers can't return real
paths; native dialogs only arrive in Phase 3). Surfaces dirs + .arch only.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app

TOKEN = "arch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def tree():
    with tempfile.TemporaryDirectory() as d:
        os.mkdir(os.path.join(d, "subdir"))
        os.mkdir(os.path.join(d, ".hidden"))
        open(os.path.join(d, "Project.arch"), "w").close()
        open(os.path.join(d, "notes.txt"), "w").close()
        yield d


def test_requires_token(client, tree):
    assert client.get("/api/fs/list", params={"path": tree}).status_code == 401


def test_home(client):
    r = client.get("/api/fs/home", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["home"]


def test_list_surfaces_dirs_and_arch_only(client, tree):
    r = client.get("/api/fs/list", params={"path": tree}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    names = {e["name"]: e for e in body["entries"]}
    assert "subdir" in names and names["subdir"]["is_dir"]
    assert "Project.arch" in names and names["Project.arch"]["is_arch"]
    assert "notes.txt" not in names   # non-.arch file hidden
    assert ".hidden" not in names     # dotfiles hidden
    assert body["parent"] == os.path.dirname(os.path.realpath(tree))


def test_list_defaults_to_home(client):
    r = client.get("/api/fs/list", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["path"]


def test_missing_path_404(client):
    r = client.get("/api/fs/list", params={"path": "/no/such/dir/xyz"}, headers=AUTH)
    assert r.status_code == 404


def test_file_path_400(client, tree):
    r = client.get("/api/fs/list",
                   params={"path": os.path.join(tree, "Project.arch")}, headers=AUTH)
    assert r.status_code == 400


def test_mkdir_creates_folder(client, tree):
    r = client.post("/api/fs/mkdir", json={"parent": tree, "name": "Fresh"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["is_dir"] is True
    assert os.path.isdir(os.path.join(tree, "Fresh"))


def test_mkdir_rejects_existing(client, tree):
    r = client.post("/api/fs/mkdir", json={"parent": tree, "name": "subdir"}, headers=AUTH)
    assert r.status_code == 409


def test_mkdir_rejects_separators(client, tree):
    r = client.post("/api/fs/mkdir", json={"parent": tree, "name": "a/b"}, headers=AUTH)
    assert r.status_code == 400


def test_list_exts_filter_surfaces_elf_and_json(client):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "fw.elf"), "w").close()
        open(os.path.join(d, "cache.json"), "w").close()
        open(os.path.join(d, "Project.arch"), "w").close()
        r = client.get("/api/fs/list", params={"path": d, "exts": ".elf,.json"}, headers=AUTH)
        names = {e["name"] for e in r.json()["entries"]}
        assert "fw.elf" in names and "cache.json" in names
        assert "Project.arch" not in names   # not in the allow-list
