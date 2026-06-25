"""
Phase 3 — SPA static serving (plan §5).

The desktop shell serves the built React app from the worker itself
(``create_app(serve_frontend=True)``) so there is no second server. These tests
use a synthetic ``dist/`` so they don't depend on a real ``npm run build``.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

import backend.static as static
from backend.app import create_app

TOKEN = "test-token-123"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def fake_dist(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>")
    (dist / "assets" / "app.js").write_text("console.log('hi')")
    (dist / "favicon.ico").write_text("ico")
    monkeypatch.setattr(static, "frontend_dist", lambda: dist)
    return dist


@pytest.fixture()
def client(fake_dist):
    app = create_app(token=TOKEN, serve_frontend=True)
    with TestClient(app) as c:
        yield c


def test_root_serves_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "SPA" in r.text


def test_unknown_route_falls_back_to_index(client):
    # client-side route → SPA history fallback
    r = client.get("/workspace/some/deep/view")
    assert r.status_code == 200
    assert "SPA" in r.text


def test_real_static_file_is_served(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.text == "ico"


def test_assets_are_mounted(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_api_still_wins_over_catch_all(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_unknown_api_path_is_404_not_index(client):
    # an unmatched /api/* must not silently return the SPA shell
    r = client.get("/api/does-not-exist", headers=AUTH)
    assert r.status_code == 404


def test_frontend_not_served_by_default():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        # no SPA mount → root is not a 200 HTML shell
        assert c.get("/").status_code == 404
