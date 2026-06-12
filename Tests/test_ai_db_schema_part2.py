"""
Phase 7 — DB schema for AI Part 2 (mind map, separate prompt/rules, per-file diffs).

Logic-layer only: exercises the new tables, accessors, version upgrade, and the
integrity-digest exclusions on a real ProjectDatabase against temp .arch files.
"""
import os
import sys
import json

sys.path.append(os.path.abspath("src"))

import pytest
from Application_Logic.Logic_Database import ProjectDatabase, DB_SCHEMA_VERSION


@pytest.fixture()
def db(tmp_path):
    d = ProjectDatabase()
    d.open(str(tmp_path / "p.arch"))
    yield d
    d.close()


def _tables(d):
    cur = d._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# Schema presence + version
# ---------------------------------------------------------------------------

def test_new_db_has_v2_tables_and_version(db):
    assert DB_SCHEMA_VERSION == 3
    assert db.get_meta("schema_version") == "3"
    t = _tables(db)
    assert "ai_model_mindmaps" in t
    assert "ai_code_diffs" in t


def test_v1_project_upgrades_on_reopen(tmp_path):
    p = str(tmp_path / "old.arch")
    d = ProjectDatabase(); d.open(p)
    # Simulate a v1 project.
    d.set_meta("schema_version", "1")
    d.set_meta("ai_prompt", "keep me")     # pre-existing data must survive
    d.close()
    # Reopen → _create_schema runs the in-block upgrade (no set_meta re-entrancy).
    d2 = ProjectDatabase(); d2.open(p)
    assert d2.get_meta("schema_version") == "3"
    assert d2.get_meta("ai_prompt") == "keep me"
    assert "ai_model_mindmaps" in _tables(d2)
    d2.close()


# ---------------------------------------------------------------------------
# Mind map accessors
# ---------------------------------------------------------------------------

def test_mindmap_roundtrip_and_replace(db):
    mid = db.create_model("DoorControl", "In Work")
    mm = {"model_name": "DoorControl", "functions": {"DoorControl_Init": {}}}
    db.save_model_mindmap(mid, json.dumps(mm), source_hash="h1",
                          builder_version="1.0", char_count=123, updated_at="t1")
    assert db.get_model_mindmap(mid) == mm
    meta = db.get_model_mindmap_meta(mid)
    assert meta["source_hash"] == "h1" and meta["builder_version"] == "1.0"
    assert meta["char_count"] == 123
    assert db.has_model_mindmap(mid) is True

    # INSERT OR REPLACE overwrites, never duplicates (#2E: per-(model, release) map).
    db.save_model_mindmap(mid, json.dumps({"v": 2}), source_hash="h2")
    assert db.get_model_mindmap(mid) == {"v": 2}
    cur = db._conn.execute("SELECT COUNT(*) FROM ai_release_maps WHERE model_id=?", (mid,))
    assert cur.fetchone()[0] == 1


def test_get_mindmap_missing(db):
    assert db.get_model_mindmap(999) is None
    assert db.get_model_mindmap_meta(999) is None
    assert db.has_model_mindmap(999) is False


# ---------------------------------------------------------------------------
# Diffs
# ---------------------------------------------------------------------------

def test_diffs_dedup_on_repeat(db):
    mid = db.create_model("M", "In Work")
    diffs = [
        {"file_path": "a.c", "status": "modified", "unified_diff": "@@ ..."},
        {"file_path": "b.c", "status": "added", "unified_diff": "@@ ..."},
    ]
    db.save_code_diffs(mid, "dh1", diffs)
    db.save_code_diffs(mid, "dh1", diffs)   # repeat with same set
    got = db.get_code_diffs(mid, "dh1")
    assert len(got) == 2                      # no duplicates (sentinel + clear path)
    assert {g["file_path"] for g in got} == {"a.c", "b.c"}
    assert db.has_code_diff(mid, "dh1") is True
    assert db.list_diff_files(mid, "dh1") == ["a.c", "b.c"]


def test_diffs_project_wide_sentinel(db):
    # model_id = -1 (inception/project-wide) must store and dedup too.
    db.save_code_diffs(-1, "dh", [{"file_path": "x.c", "status": "modified", "unified_diff": "d"}])
    db.save_code_diffs(-1, "dh", [{"file_path": "x.c", "status": "modified", "unified_diff": "d"}])
    assert len(db.get_code_diffs(-1, "dh")) == 1


# ---------------------------------------------------------------------------
# Cascade / cleanup
# ---------------------------------------------------------------------------

def test_model_delete_cascades_mindmap(db):
    mid = db.create_model("M", "In Work")
    db.save_model_mindmap(mid, json.dumps({"a": 1}))
    with db._conn:
        db._conn.execute("DELETE FROM architecture_models WHERE id=?", (mid,))
    assert db.has_model_mindmap(mid) is False   # FK ON DELETE CASCADE


def test_delete_model_mindmap_purges_diffs(db):
    mid = db.create_model("M", "In Work")
    db.save_model_mindmap(mid, json.dumps({"a": 1}))
    db.save_code_diffs(mid, "dh", [{"file_path": "a.c", "status": "modified", "unified_diff": "d"}])
    db.delete_model_mindmap(mid)
    assert db.has_model_mindmap(mid) is False
    assert db.has_code_diff(mid, "dh") is False  # explicit sibling cleanup


# ---------------------------------------------------------------------------
# Integrity digest exclusions
# ---------------------------------------------------------------------------

def test_digest_excludes_ai_caches_and_paths(db):
    mid = db.create_model("M", "In Work")
    base = db.compute_content_digest()
    # Writing derived caches / volatile paths must NOT change the digest.
    db.save_model_mindmap(mid, json.dumps({"a": 1}), source_hash="h")
    db.save_code_diffs(mid, "dh", [{"file_path": "a.c", "status": "modified", "unified_diff": "d"}])
    db.set_meta("ai_source_path", "/Users/somebody/src")
    db.set_meta("ai_previous_source_path", "/Users/somebody/old")
    db.set_meta("ai_requirements_context", json.dumps([{"id": "R1", "text": "x"}]))
    assert db.compute_content_digest() == base


def test_digest_includes_protected_prompt_rules(db):
    base = db.compute_content_digest()
    db.set_meta("chat_rules", "new chat rules")
    assert db.compute_content_digest() != base   # user-authored content IS protected


# ---------------------------------------------------------------------------
# Separate prompt/rules keys
# ---------------------------------------------------------------------------

def test_prompt_rules_keys_independent(db):
    db.set_meta("ai_prompt", "tab3 prompt")
    db.set_meta("ai_rules_md", "tab3 rules")
    db.set_meta("mind_map_prompt", "mm prompt")
    db.set_meta("mind_map_rules", "mm rules")
    db.set_meta("chat_rules", "chat rules")
    # Writing one must not perturb the others.
    db.set_meta("chat_rules", "chat rules v2")
    assert db.get_meta("ai_prompt") == "tab3 prompt"
    assert db.get_meta("ai_rules_md") == "tab3 rules"
    assert db.get_meta("mind_map_prompt") == "mm prompt"
    assert db.get_meta("mind_map_rules") == "mm rules"
    assert db.get_meta("chat_rules") == "chat rules v2"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
