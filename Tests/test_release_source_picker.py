"""
#2E Phase 3 — release-driven source selection helpers.

Covers ReleaseManager.selectable_releases() (real releases only), the
release_source_provider() resolver, set_model_diff_hash, and the ToolExecutor
DB-provider mode (read_file / list_files / search_code over release source).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Source_Store import (
    DbReleaseSourceProvider, release_source_provider,
)
import Application_Logic.Logic_AI_Tools as aitools
from Tests.test_helpers import make_project_db


def _proj(tmp):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("Port", "PortSearchColumn", True)],
        models=[{"name": "M", "status": "In Work", "rows": []}],
        releases=[{"name": "R2.0"}, {"name": "R1.0"}],
    )
    return db


def test_selectable_releases_excludes_baselines_and_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        db = _proj(tmp)
        rels = db.get_all_releases()
        # Mark one a baseline, one deleted, directly.
        db._conn.execute("UPDATE releases SET is_baseline=1 WHERE name='R1.0'")
        db._conn.execute("UPDATE releases SET is_deleted=1 WHERE name='R2.0'")
        db.commit()
        rm = ReleaseManager()
        rm.set_db(db)
        names = [r.name for r in rm.selectable_releases()]
        assert "R1.0" not in names   # baseline excluded
        assert "R2.0" not in names   # deleted excluded
        db.close()


def test_release_source_provider_none_without_source():
    with tempfile.TemporaryDirectory() as tmp:
        db = _proj(tmp)
        rid = db.get_all_releases()[0]["id"]
        assert release_source_provider(db, rid) is None       # no source imported
        assert release_source_provider(db, None) is None
        db.save_release_source_files(rid, [("a.c", "int a;\n")])
        prov = release_source_provider(db, rid)
        assert isinstance(prov, DbReleaseSourceProvider)
        db.close()


def test_set_model_diff_hash_preserves_existing_map():
    with tempfile.TemporaryDirectory() as tmp:
        db = _proj(tmp)
        import json
        mid = db.get_all_models()[0]["id"]
        rid = db.get_all_releases()[0]["id"]
        # Existing maps must survive a diff-hash update.
        db.save_model_code_map(mid, json.dumps({"functions": {"f": {}}}), release_id=rid)
        db.save_model_mindmap(mid, json.dumps({"mm": 1}), release_id=rid)
        db.set_model_diff_hash(mid, "deadbeef", release_id=rid)
        assert db.get_model_mindmap_meta(mid, release_id=rid)["diff_hash"] == "deadbeef"
        assert db.get_model_code_map(mid, release_id=rid) == {"functions": {"f": {}}}
        assert db.get_model_mindmap(mid, release_id=rid) == {"mm": 1}
        db.close()


def test_tool_executor_provider_mode():
    with tempfile.TemporaryDirectory() as tmp:
        db = _proj(tmp)
        rid = db.get_all_releases()[0]["id"]
        db.save_release_source_files(rid, [
            ("src/door.c", "void Door_Init(void){ /* SETUP */ }\n"),
            ("inc/door.h", "void Door_Init(void);\n"),
        ])
        prov = DbReleaseSourceProvider(db, rid)
        ex = aitools.ToolExecutor(None, db=db, model_id=1, provider=prov, release_id=rid)

        assert "Door_Init" in ex.read_file("src/door.c")
        listed = ex.list_files("*.c")
        assert "src/door.c" in listed and "inc/door.h" not in listed
        hits = ex.search_code("SETUP")
        assert "src/door.c:1:" in hits
        # Missing file → ToolError-style message via exception
        try:
            ex.read_file("nope.c")
            assert False, "expected error"
        except Exception:
            pass
        db.close()
