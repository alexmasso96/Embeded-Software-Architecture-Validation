"""
Regression tests for the ASPICE-audit fixes (logic layer only).

Covers:
  * OBS-05  — get_username() prefers getpass over the unreliable os.getlogin()
  * NC-3    — change-history obfuscation at rest + append-only HMAC tamper-chain
  * NC-5    — DB-level write-protection of frozen baselines (with create bypass)
  * NC-4    — baseline freeze/unfreeze is recorded in history (dual-scope)
  * BUG-02  — NewProjectController close is idempotent / guarded
"""
import os
import sys
import tempfile

sys.path.append(os.path.abspath("src"))

import pytest


# ---------------------------------------------------------------------------
# OBS-05 — username resolution
# ---------------------------------------------------------------------------
def test_get_username_prefers_getpass_over_getlogin(monkeypatch):
    from Application_Logic.Logic_File_Locking import FileLockManager
    import getpass as _gp
    import os as _os
    monkeypatch.setattr(_gp, "getuser", lambda: "alice")
    monkeypatch.setattr(_os, "getlogin", lambda: "root")
    assert FileLockManager.get_username() == "alice"


def test_get_username_falls_back_when_getpass_fails(monkeypatch):
    from Application_Logic.Logic_File_Locking import FileLockManager
    import getpass as _gp
    import os as _os
    def boom():
        raise OSError("no user")
    monkeypatch.setattr(_gp, "getuser", boom)
    monkeypatch.setattr(_os, "getlogin", lambda: "fallback")
    assert FileLockManager.get_username() == "fallback"


# ---------------------------------------------------------------------------
# NC-3 — history obfuscation + tamper-evident hash-chain
# ---------------------------------------------------------------------------
@pytest.fixture
def db(tmp_path):
    from Application_Logic.Logic_Database import ProjectDatabase
    d = ProjectDatabase()
    d.open(str(tmp_path / "t.arch"))
    yield d
    d.close()


def test_history_roundtrip_and_obfuscated_at_rest(db):
    db.add_history_entry("Edited cell A1", model_name="M", username="alice")
    db.add_history_entry("Reviewed row 2", model_name="M", username="bob")
    # Public read returns plaintext
    hist = db.get_history(None)
    descs = [h["description"] for h in hist]
    assert "Edited cell A1" in descs and "Reviewed row 2" in descs
    # Raw column is obfuscated (not the plaintext)
    raw = [r[0] for r in db._conn.execute("SELECT description FROM history ORDER BY id")]
    assert all(r.startswith("enc:") for r in raw)
    assert "Edited cell A1" not in raw


def test_history_chain_valid_then_detects_tamper(db):
    for i in range(4):
        db.add_history_entry(f"change {i}", username="u")
    assert db.verify_history_chain() is True
    # Tamper with a description directly in the DB -> chain breaks
    rid = db._conn.execute("SELECT id FROM history ORDER BY id LIMIT 1").fetchone()[0]
    with db._conn:
        db._conn.execute("UPDATE history SET description='enc:forged' WHERE id=?", (rid,))
    assert db.verify_history_chain() is False


def test_history_chain_detects_deletion(db):
    for i in range(4):
        db.add_history_entry(f"row {i}", username="u")
    assert db.verify_history_chain() is True
    mid = db._conn.execute("SELECT id FROM history ORDER BY id LIMIT 1 OFFSET 1").fetchone()[0]
    with db._conn:
        db._conn.execute("DELETE FROM history WHERE id=?", (mid,))
    assert db.verify_history_chain() is False


def test_copy_release_history_keeps_chain_valid(db):
    a = db.create_release("A")
    b = db.create_release("B")
    db.add_history_entry("a1", username="u", release_id=a)
    db.add_history_entry("a2", username="u", release_id=a)
    db.copy_release_history(a, b)
    # cloned rows are readable and the global chain stays valid
    assert {h["description"] for h in db.get_history(b)} == {"a1", "a2"}
    assert db.verify_history_chain() is True


def test_history_excluded_from_digest(db):
    d0 = db.compute_content_digest()
    db.add_history_entry("noise", username="u")
    assert db.compute_content_digest() == d0   # history must not perturb the digest


# ---------------------------------------------------------------------------
# NC-5 — frozen-baseline DB write protection
# ---------------------------------------------------------------------------
def test_frozen_baseline_blocks_row_writes(db):
    from Application_Logic.Logic_Database import BaselineLockedError
    rid = db.create_release("BL", is_baseline=1)
    assert db.is_release_frozen(rid) is True
    with pytest.raises(BaselineLockedError):
        db.save_release_rows(rid, [{"x": 1}])
    with pytest.raises(BaselineLockedError):
        db.save_release_results(rid, {"c": []})
    with pytest.raises(BaselineLockedError):
        db.save_release_column_metadata(rid, {"c": {}})


def test_frozen_baseline_allows_creation_bypass_then_blocks(db):
    rid = db.create_release("BL", is_baseline=1)
    db.save_release_rows(rid, [{"x": 1}], _allow_frozen=True)   # creation path
    assert db.get_release_rows(rid) == [{"x": 1}]
    from Application_Logic.Logic_Database import BaselineLockedError
    with pytest.raises(BaselineLockedError):
        db.save_release_rows(rid, [{"x": 2}])                   # normal edit blocked


def test_unfrozen_release_is_writable(db):
    rid = db.create_release("R", is_baseline=0)
    db.save_release_rows(rid, [{"x": 1}])      # not frozen -> allowed
    db.update_release(rid, is_baseline=1)
    from Application_Logic.Logic_Database import BaselineLockedError
    with pytest.raises(BaselineLockedError):
        db.save_release_rows(rid, [{"x": 2}])
    db.update_release(rid, is_baseline=0)       # unfreeze
    db.save_release_rows(rid, [{"x": 3}])       # editable again
    assert db.get_release_rows(rid) == [{"x": 3}]


# ---------------------------------------------------------------------------
# NC-4 — baseline freeze/unfreeze logged to history (dual-scope)
# ---------------------------------------------------------------------------
def test_baseline_event_logged_to_both_scopes(tmp_path):
    from Application_Logic.Logic_Database import ProjectDatabase
    from Application_Logic.Logic_Release_Manager import ReleaseManager
    path = str(tmp_path / "rel.arch")
    db = ProjectDatabase()
    db.open(path)
    manager = ReleaseManager(path)
    manager.set_db(db)
    main = manager.create_release("Main")    # active
    r2 = manager.create_release("R2")        # now active; Main is previous
    manager.log_baseline_event(main, frozen=True)
    active = manager.get_active_release()
    main_hist = [h["description"] for h in db.get_history(main.id)]
    active_hist = [h["description"] for h in db.get_history(active.id)]
    assert any("Froze baseline 'Main'" in d for d in main_hist)
    assert any("Froze baseline 'Main'" in d for d in active_hist)
    db.close()


# ---------------------------------------------------------------------------
# BUG-02 — NewProjectController close guard is idempotent
# ---------------------------------------------------------------------------
def test_new_project_controller_close_is_idempotent(tmp_path):
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow
        app = QApplication.instance() or QApplication(sys.argv)
        from UI.new_project_window import NewProjectController
    except Exception as e:  # pragma: no cover - environment without Qt
        pytest.skip(f"Qt unavailable: {e}")
    ctrl = NewProjectController(main_window=None, project_db=None)
    assert ctrl._closing is False
    ctrl._safe_close()
    assert ctrl._closing is True
    # second close (and a late handler call) must not raise
    ctrl._safe_close()
    ctrl.start_empty_handler()   # guarded: returns immediately when _closing


# ---------------------------------------------------------------------------
# Finding F — journal-mode selection (WAL local / DELETE on network)
# ---------------------------------------------------------------------------
def test_journal_mode_env_override(tmp_path, monkeypatch):
    from Application_Logic.Logic_Database import ProjectDatabase
    monkeypatch.setenv("ARCH_SQLITE_JOURNAL_MODE", "DELETE")
    d = ProjectDatabase()
    d.open(str(tmp_path / "ov.arch"))
    assert d.journal_mode == "DELETE"
    d.close()


def test_journal_mode_local_is_wal(tmp_path, monkeypatch):
    from Application_Logic.Logic_Database import ProjectDatabase
    monkeypatch.delenv("ARCH_SQLITE_JOURNAL_MODE", raising=False)
    d = ProjectDatabase()
    d.open(str(tmp_path / "loc.arch"))
    # a local temp dir supports WAL on every CI platform
    assert d.journal_mode == "WAL"
    d.close()


def test_is_network_fs_posix_false_for_local(tmp_path):
    import sys as _sys
    from Application_Logic import Logic_Database as L
    if _sys.platform == "win32":
        import pytest as _pt
        _pt.skip("posix-only helper")
    assert L._is_network_fs_posix(str(tmp_path / "x.arch")) is False


# ---------------------------------------------------------------------------
# Finding D — integrity digest: deterministic + cheap surrogate ordering
# ---------------------------------------------------------------------------
def test_digest_deterministic_and_content_sensitive(db):
    rid = db.create_release("R")
    db.save_release_rows(rid, [{"port": "A"}, {"port": "B"}])
    d1 = db.compute_content_digest()
    d2 = db.compute_content_digest()
    assert d1 == d2                       # stable
    db.save_release_rows(rid, [{"port": "A"}, {"port": "CHANGED"}])
    assert db.compute_content_digest() != d1   # content-sensitive


def test_digest_stable_across_recompute_with_big_rows(db):
    # The surrogate-key ordering (Finding D) must still produce a stable digest
    # when release_rows carry large JSON blobs (the case it speeds up). Real
    # save->close->reopen stability is covered by Tests/test_integrity.py.
    rid = db.create_release("R")
    big = [{"port": f"P{i}", "blob": "x" * 500} for i in range(50)]
    db.save_release_rows(rid, big)
    assert db.compute_content_digest() == db.compute_content_digest()


# ---------------------------------------------------------------------------
# Finding M — flushing the active release before a switch preserves edits
# ---------------------------------------------------------------------------
def test_flush_active_release_preserves_unsaved_edits(tmp_path):
    from Application_Logic.Logic_Database import ProjectDatabase
    from Application_Logic.Logic_Release_Manager import ReleaseManager
    path = str(tmp_path / "rel.arch")
    d = ProjectDatabase(); d.open(path)
    mgr = ReleaseManager(path); mgr.set_db(d)
    a = mgr.create_release("A")
    b = mgr.create_release("B")           # B active; A at index 1
    mgr.set_active_release(1)             # make A active
    mgr.get_active_release().data_cache = {"rows": [{"port": "P1"}]}
    mgr.flush_active_release_data()       # the M fix: persist before switching
    mgr.set_active_release(0)             # switch to B (nulls A's cache)
    mgr.set_active_release(1)             # back to A -> reloads from DB
    assert mgr.get_active_release().data_cache.get("rows") == [{"port": "P1"}]
    d.close()
