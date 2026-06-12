"""
#2E Phase 2 — per-(model, release) mind maps & code maps (ai_release_maps).

Verifies release isolation (release A's map ≠ release B's), the active-release
default resolution, the legacy ai_model_mindmaps → ai_release_maps migration, and
that release deletion drops only that release's maps.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from Application_Logic.Logic_Database import ProjectDatabase
from Tests.test_helpers import make_project_db


def _proj(tmp):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("Port", "PortSearchColumn", True)],
        models=[{"name": "M", "status": "In Work", "rows": []}],
        releases=[{"name": "R2.0"}, {"name": "R1.0"}],
    )
    mid = db.get_all_models()[0]["id"]
    rels = {r["name"]: r["id"] for r in db.get_all_releases()}
    return db, mid, rels


def test_maps_are_isolated_per_release():
    with tempfile.TemporaryDirectory() as tmp:
        db, mid, rels = _proj(tmp)
        db.save_model_code_map(mid, json.dumps({"functions": {"a": {}}}), release_id=rels["R1.0"])
        db.save_model_code_map(mid, json.dumps({"functions": {"b": {}}}), release_id=rels["R2.0"])

        assert db.get_model_code_map(mid, release_id=rels["R1.0"]) == {"functions": {"a": {}}}
        assert db.get_model_code_map(mid, release_id=rels["R2.0"]) == {"functions": {"b": {}}}
        db.close()


def test_release_id_none_resolves_to_active():
    with tempfile.TemporaryDirectory() as tmp:
        db, mid, rels = _proj(tmp)
        db.set_active_release(rels["R1.0"])
        db.save_model_mindmap(mid, json.dumps({"v": "for-r1"}))  # no release_id → active
        assert db.get_model_mindmap(mid) == {"v": "for-r1"}                       # active
        assert db.get_model_mindmap(mid, release_id=rels["R1.0"]) == {"v": "for-r1"}
        assert db.get_model_mindmap(mid, release_id=rels["R2.0"]) is None

        # Switch active release → the same default call now sees R2.0 (empty).
        db.set_active_release(rels["R2.0"])
        assert db.get_model_mindmap(mid) is None
        db.close()


def test_save_mindmap_preserves_code_map_same_release():
    with tempfile.TemporaryDirectory() as tmp:
        db, mid, rels = _proj(tmp)
        rid = rels["R1.0"]
        db.save_model_code_map(mid, json.dumps({"functions": {}}), release_id=rid)
        db.save_model_mindmap(mid, json.dumps({"mm": 1}), release_id=rid)  # no code_map arg
        # mind map saved, code map preserved
        assert db.get_model_mindmap(mid, release_id=rid) == {"mm": 1}
        assert db.get_model_code_map(mid, release_id=rid) == {"functions": {}}
        db.close()


def test_delete_release_drops_only_its_maps():
    with tempfile.TemporaryDirectory() as tmp:
        db, mid, rels = _proj(tmp)
        db.save_model_code_map(mid, json.dumps({"functions": {"a": {}}}), release_id=rels["R1.0"])
        db.save_model_code_map(mid, json.dumps({"functions": {"b": {}}}), release_id=rels["R2.0"])
        db.delete_release_record(rels["R1.0"])
        assert db.get_model_code_map(mid, release_id=rels["R1.0"]) is None
        assert db.get_model_code_map(mid, release_id=rels["R2.0"]) == {"functions": {"b": {}}}
        db.close()


def test_ids_with_mindmap_is_per_release():
    with tempfile.TemporaryDirectory() as tmp:
        db, mid, rels = _proj(tmp)
        db.save_model_mindmap(mid, json.dumps({"mm": 1}), release_id=rels["R1.0"])
        assert db.get_model_ids_with_mindmap(release_id=rels["R1.0"]) == {mid}
        assert db.get_model_ids_with_mindmap(release_id=rels["R2.0"]) == set()
        db.close()


def test_legacy_mindmap_migration():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "legacy.arch")
        db = make_project_db(
            path,
            layout=[("Port", "PortSearchColumn", True)],
            models=[{"name": "M", "status": "In Work", "rows": []}],
            releases=[{"name": "R1.0"}],
        )
        mid = db.get_all_models()[0]["id"]
        rid = db.get_all_releases()[0]["id"]
        db.set_active_release(rid)
        # Simulate a pre-#2E project: a row only in the legacy table, new table empty.
        db._conn.execute("DELETE FROM ai_release_maps")
        db._conn.execute(
            "INSERT OR REPLACE INTO ai_model_mindmaps "
            "(model_id, mindmap_json, code_map_json, updated_at) VALUES (?,?,?,?)",
            (mid, json.dumps({"legacy": True}), json.dumps({"functions": {}}), "t"))
        db.commit()
        db.close()

        # Reopen → migration runs, keying the legacy row to the active release.
        db2 = ProjectDatabase()
        db2.open(path)
        assert db2.get_model_mindmap(mid, release_id=rid) == {"legacy": True}
        assert db2.get_model_code_map(mid, release_id=rid) == {"functions": {}}
        db2.close()
