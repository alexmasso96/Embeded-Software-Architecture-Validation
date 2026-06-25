"""
Backend Test-Case-Design router tests (``/api/testdesign``).

The pure template/grouping helpers in ``Logic_TestCase_Design`` are covered by the
``test_test_case_design_*`` suites; this file exercises the HTTP layer that wraps
them — settings get/put (+ grouping normalisation), live preview (empty / renderable
/ retired rows), condition autocomplete, and the Markdown export to disk — the way
the React Test Design view drives it.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "td-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

LAYOUT = [
    ("TC. ID", "Static Text", True, 100),
    ("Port Name", "Static Text", True, 100),
    ("Port State", "Static Text", True, 100),
]


def _seed(path):
    """One model: a renderable port, a retired port, and an empty placeholder row."""
    db = make_project_db(
        path,
        layout=LAYOUT,
        models=[{"name": "Arch_A", "status": "In Work", "rows": [
            {"TC. ID": {"text": "TC1"}, "Port Name": {"text": "PortA"},
             "Port State": {"text": "In Work"}},
            {"TC. ID": {"text": "TC2"}, "Port Name": {"text": "PortB"},
             "Port State": {"text": "Retired"}},
            {"TC. ID": {"text": ""}, "Port Name": {"text": ""},
             "Port State": {"text": ""}},
        ]}],
        releases=[{"name": "R1"}],
    )
    mid = db.get_all_models()[0]["id"]
    db.commit()
    db.close()
    return mid


@pytest.fixture()
def proj():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        mid = _seed(path)
        yield path, mid


def _client(path, mode="view"):
    app = create_app(token=TOKEN)
    c = TestClient(app)
    c.__enter__()
    c.post("/api/project/open", json={"path": path, "mode": mode}, headers=AUTH)
    return c


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_get_settings_defaults(proj):
    path, _ = proj
    c = _client(path)
    body = c.get("/api/testdesign", headers=AUTH).json()
    assert body["project_title"] == ""
    assert body["design_template"] == ""
    assert body["operation_grouping"] == "grouped"   # DEFAULT_GROUPING
    c.__exit__(None, None, None)


def test_put_settings_persists_and_normalises_grouping(proj):
    path, _ = proj
    c = _client(path, mode="exclusive")
    resp = c.put("/api/testdesign", headers=AUTH, json={
        "project_title": "My Title",
        "design_template": "Test [Port Name]",
        "operation_grouping": "bogus",      # invalid → coerced to default
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["operation_grouping"] == "grouped"

    # round-trips through the DB
    got = c.get("/api/testdesign", headers=AUTH).json()
    assert got["project_title"] == "My Title"
    assert got["design_template"] == "Test [Port Name]"
    assert got["operation_grouping"] == "grouped"
    c.__exit__(None, None, None)


def test_put_settings_keeps_independent(proj):
    path, _ = proj
    c = _client(path, mode="exclusive")
    resp = c.put("/api/testdesign", headers=AUTH, json={"operation_grouping": "independent"})
    assert resp.json()["operation_grouping"] == "independent"
    c.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------
def test_preview_renderable_row(proj):
    path, mid = proj
    c = _client(path)
    body = c.post("/api/testdesign/preview", headers=AUTH, json={
        "project_title": "[Model]",
        "design_template": "Test [Port Name]",
        "operation_grouping": "independent",
        "model_id": mid,
        "row_index": 0,
    }).json()
    assert body["status"] == "ok"
    assert body["row_count"] == 3
    assert body["title"] == "Arch_A"          # [Model] bound to the model name
    assert body["body"] == "Test PortA"
    assert body["unit_label"] == "Row"        # independent grouping
    c.__exit__(None, None, None)


def test_preview_retired_row_not_generated(proj):
    path, mid = proj
    c = _client(path)
    body = c.post("/api/testdesign/preview", headers=AUTH, json={
        "design_template": "Test [Port Name]",
        "operation_grouping": "independent",
        "model_id": mid,
        "row_index": 1,                        # PortB is Retired
    }).json()
    assert body["status"] == "retired"
    assert body["body"] == ""
    assert "Retired" in body["message"]
    c.__exit__(None, None, None)


def test_preview_empty_row(proj):
    path, mid = proj
    c = _client(path)
    body = c.post("/api/testdesign/preview", headers=AUTH, json={
        "design_template": "x",
        "operation_grouping": "independent",
        "model_id": mid,
        "row_index": 2,                        # the empty placeholder row
    }).json()
    assert body["status"] == "empty"
    c.__exit__(None, None, None)


def test_preview_index_clamped(proj):
    path, mid = proj
    c = _client(path)
    body = c.post("/api/testdesign/preview", headers=AUTH, json={
        "design_template": "Test [Port Name]",
        "operation_grouping": "independent",
        "model_id": mid,
        "row_index": 999,                      # clamped to last row
    }).json()
    assert body["index"] == 2
    c.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Autocomplete suggestions
# ---------------------------------------------------------------------------
def test_suggestions_open_bracket_lists_columns(proj):
    path, mid = proj
    c = _client(path)
    body = c.get("/api/testdesign/suggestions",
                 params={"line_text": "Hello [", "model_id": mid}, headers=AUTH).json()
    # Unclosed-bracket fallback surfaces the active columns plus synthetic [Model].
    assert "[Port Name]" in body["completions"]
    assert "[Model]" in body["completions"]
    assert body["prefix"] == "["
    c.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def test_export_writes_markdown_file(proj):
    path, mid = proj
    c = _client(path)
    body = c.post("/api/testdesign/export", headers=AUTH, json={
        "project_title": "Proj",
        "design_template": "Test [Port Name]",
        "operation_grouping": "independent",
        "scope": "current",
        "model_id": mid,
    }).json()
    assert body["file_count"] == 1
    assert body["files"] == ["Arch_A_Test_Case_Design.md"]
    out = os.path.join(body["output_dir"], body["files"][0])
    assert os.path.exists(out)
    content = open(out, encoding="utf-8").read()
    assert "PortA" in content          # renderable row exported
    assert "PortB" not in content      # retired row excluded
    c.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Guard: no project open → 409
# ---------------------------------------------------------------------------
def test_settings_without_project_409():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        assert c.get("/api/testdesign", headers=AUTH).status_code == 409
