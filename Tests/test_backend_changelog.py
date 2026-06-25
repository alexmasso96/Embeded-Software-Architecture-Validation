"""
Phase 1 — changelog router tests.

Two angles:
  * read endpoints over seeded diff rows (file list, aligned per-file diff, AI summary);
  * end-to-end: run the release_diff job over two releases with DB source and
    confirm the changelog reflects the persisted result.
"""
import os
import sys
import time
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Tests.test_helpers import make_project_db

TOKEN = "cl-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

UNIFIED = (
    "--- a/src/a.c\n+++ b/src/a.c\n@@ -1,2 +1,2 @@\n"
    " int x;\n-int old_v;\n+int new_v;\n"
)


@pytest.fixture()
def seeded_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        mid = db.get_all_models()[0]["id"]
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        db.save_code_diffs(mid, "hash123", [
            {"file_path": "src/a.c", "status": "modified", "unified_diff": UNIFIED},
            {"file_path": "src/new.c", "status": "added", "unified_diff": "+brand new\n"},
        ])
        db.set_model_diff_hash(mid, "hash123", release_id=rid)
        db.save_model_metadata(mid, {"ai_change_log": "# Summary\n- changed a.c"})
        db.commit(); db.close()
        yield path


@pytest.fixture()
def client(seeded_path):
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        c.post("/api/project/open", json={"path": seeded_path, "mode": "view"}, headers=AUTH)
        yield c


def test_changelog_summary(client):
    body = client.get("/api/changelog", headers=AUTH).json()
    assert body["diff_hash"] == "hash123"
    files = {f["file_path"]: f["status"] for f in body["files"]}
    assert files == {"src/a.c": "modified", "src/new.c": "added"}
    assert "Summary" in body["ai_change_log"]


def test_file_diff_aligned(client):
    body = client.get("/api/changelog/diff?file=src/a.c", headers=AUTH).json()
    assert body["status"] == "modified"
    # The changed line aligns deleted(old) ↔ added(new).
    old_types = [k for _, k in body["old"]]
    new_types = [k for _, k in body["new"]]
    assert "deleted" in old_types
    assert "added" in new_types
    old_text = [t for t, _ in body["old"]]
    new_text = [t for t, _ in body["new"]]
    assert "int old_v;" in old_text
    assert "int new_v;" in new_text


def test_file_diff_unknown_file_409(client):
    assert client.get("/api/changelog/diff?file=nope.c", headers=AUTH).status_code == 409


def test_changelog_empty_when_no_diffs():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p2.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        db.close()
        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
            body = c.get("/api/changelog", headers=AUTH).json()
            assert body["diff_hash"] is None
            assert body["files"] == []


# ---------------------------------------------------------------------------
# End-to-end: release_diff job → persisted diffs → changelog
# ---------------------------------------------------------------------------
def _wait(client, job_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        b = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if b["status"] in ("done", "failed", "cancelled"):
            return b
        time.sleep(0.03)
    raise AssertionError("job timed out")


def test_release_diff_job_feeds_changelog():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}, {"name": "R2"}])
        mid = db.get_all_models()[0]["id"]
        rels = {r["name"]: r["id"] for r in db.get_all_releases()}
        # Same file, different content between releases.
        db.save_release_source_files(rels["R1"], [("src/main.c", "int main(){return 0;}\n")])
        db.save_release_source_files(rels["R2"], [("src/main.c", "int main(){return 1;}\n")])
        db.set_active_release(rels["R2"])
        db.commit(); db.close()

        app = create_app(token=TOKEN)
        with TestClient(app) as c:
            c.post("/api/project/open", json={"path": path, "mode": "exclusive"}, headers=AUTH)
            r = c.post("/api/jobs/release_diff",
                       json={"model_id": mid,
                             "current_release_id": rels["R2"],
                             "previous_release_id": rels["R1"]}, headers=AUTH)
            body = _wait(c, r.json()["job_id"])
            assert body["status"] == "done", body
            assert body["result"]["file_count"] >= 1

            cl = c.get("/api/changelog", headers=AUTH).json()
            assert cl["diff_hash"]
            assert any(f["file_path"].endswith("main.c") for f in cl["files"])
            diff = c.get("/api/changelog/diff?file=" + cl["files"][0]["file_path"],
                         headers=AUTH).json()
            assert diff["old"] and diff["new"]
