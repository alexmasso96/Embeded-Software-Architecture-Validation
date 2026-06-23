"""
Phase 3 — durable UI-preferences store tests (issue 6).

The desktop shell's per-launch port wipes origin-scoped localStorage between
sessions, so prefs are mirrored to a JSON file in the OS app-data dir. The store
path is overridable via ARCH_PREFS_FILE; these tests point it at a temp file.
"""
import json
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
def store(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "nested", "prefs.json")  # parent created on write
        monkeypatch.setenv("ARCH_PREFS_FILE", path)
        yield path


@pytest.fixture()
def client(store):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        yield c


def test_requires_token(client):
    assert client.get("/api/prefs").status_code == 401
    assert client.put("/api/prefs", json={"key": "k", "value": "v"}).status_code == 401


def test_empty_store_returns_empty(client):
    r = client.get("/api/prefs", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"prefs": {}}


def test_put_persists_and_reads_back(client, store):
    r = client.put("/api/prefs", json={"key": "arch.recents", "value": "[1,2]"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["prefs"]["arch.recents"] == "[1,2]"
    # Round-trips through the file (separate GET) and the file actually exists.
    assert client.get("/api/prefs", headers=AUTH).json()["prefs"]["arch.recents"] == "[1,2]"
    assert json.load(open(store))["arch.recents"] == "[1,2]"


def test_put_updates_existing_key(client):
    client.put("/api/prefs", json={"key": "k", "value": "1"}, headers=AUTH)
    client.put("/api/prefs", json={"key": "k", "value": "2"}, headers=AUTH)
    assert client.get("/api/prefs", headers=AUTH).json()["prefs"]["k"] == "2"


def test_null_value_deletes_key(client):
    client.put("/api/prefs", json={"key": "k", "value": "1"}, headers=AUTH)
    r = client.put("/api/prefs", json={"key": "k", "value": None}, headers=AUTH)
    assert "k" not in r.json()["prefs"]
    assert client.get("/api/prefs", headers=AUTH).json()["prefs"] == {}


def test_persists_across_app_instances(store):
    # A fresh app (simulating a new session / new random port) reads the same file.
    app1 = create_app(token=TOKEN)
    with TestClient(app1) as c1:
        c1.put("/api/prefs", json={"key": "arch.theme.mode", "value": "dark"}, headers=AUTH)
    app2 = create_app(token=TOKEN)
    with TestClient(app2) as c2:
        assert c2.get("/api/prefs", headers=AUTH).json()["prefs"]["arch.theme.mode"] == "dark"
