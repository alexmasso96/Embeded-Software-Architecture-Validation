"""
Integrity HMAC tests
====================
Covers the hotfix that replaced the fragile whole-file SHA-256 with an
HMAC over canonical *logical* content (ProjectDatabase.compute_content_digest
+ ProjectSaver.compute_integrity_hmac).

The headline regression: a save -> close -> reopen cycle (and benign writes
to volatile tables like ui_state/history that the app performs outside an
explicit save) must NOT change the integrity value, so the user is not
spuriously prompted for the master password.
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

import pytest

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Project_Saving import ProjectSaver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed(db: ProjectDatabase):
    """Populate a project with some meaningful content."""
    db.set_meta("default_cyclicity", "10")
    db.save_column_layout([("Signal", "text", True, 120), ("Value", "text", True, 80)])
    mid = db.create_model("Model_A")
    db.save_model_rows(mid, [{"Signal": f"S{i}", "Value": str(i)} for i in range(5)])
    db.commit()
    return mid


def _stamp(db: ProjectDatabase, master_hash=None):
    """Mirror what ProjectSaver.save_project does for the integrity stamp."""
    integrity = ProjectSaver.compute_integrity_hmac(db, master_hash)
    db.set_meta("integrity_hmac", integrity)
    db.commit()
    return integrity


def _reopen(path: str) -> ProjectDatabase:
    db = ProjectDatabase()
    db.open(path)
    return db


# ===========================================================================
# Content digest stability
# ===========================================================================

class TestContentDigestStability:
    def test_digest_is_deterministic_same_connection(self, tmp_path):
        db = ProjectDatabase()
        db.open(str(tmp_path / "p.arch"))
        _seed(db)
        assert db.compute_content_digest() == db.compute_content_digest()

    def test_digest_survives_close_reopen(self, tmp_path):
        path = str(tmp_path / "p.arch")
        db = ProjectDatabase()
        db.open(path)
        _seed(db)
        before = db.compute_content_digest()
        db.close()

        db2 = _reopen(path)
        after = db2.compute_content_digest()
        assert after == before, "digest must be stable across close/reopen"

    def test_digest_changes_on_real_content_change(self, tmp_path):
        db = ProjectDatabase()
        db.open(str(tmp_path / "p.arch"))
        mid = _seed(db)
        before = db.compute_content_digest()
        db.upsert_model_row(mid, 0, {"Signal": "S0", "Value": "CHANGED"})
        db.commit()
        assert db.compute_content_digest() != before


# ===========================================================================
# Volatile tables must NOT affect the digest (the actual bug)
# ===========================================================================

class TestVolatileWritesIgnored:
    def test_ui_state_write_does_not_change_digest(self, tmp_path):
        db = ProjectDatabase()
        db.open(str(tmp_path / "p.arch"))
        _seed(db)
        before = db.compute_content_digest()
        db.set_ui_state("active_model_id", "1")
        db.set_ui_state("window_geometry", "0,0,800,600")
        db.commit()
        assert db.compute_content_digest() == before

    def test_history_append_does_not_change_digest(self, tmp_path):
        db = ProjectDatabase()
        db.open(str(tmp_path / "p.arch"))
        _seed(db)
        before = db.compute_content_digest()
        db.add_history_entry("edited something", model_name="Model_A", username="alex")
        db.commit()
        assert db.compute_content_digest() == before

    def test_integrity_meta_excluded_from_digest(self, tmp_path):
        db = ProjectDatabase()
        db.open(str(tmp_path / "p.arch"))
        _seed(db)
        before = db.compute_content_digest()
        db.set_meta("integrity_hmac", "deadbeef")
        db.commit()
        assert db.compute_content_digest() == before


# ===========================================================================
# HMAC stamp / verify round-trip — the spurious-prompt regression
# ===========================================================================

class TestIntegrityRoundTrip:
    def test_no_mismatch_on_clean_reopen(self, tmp_path):
        path = str(tmp_path / "p.arch")
        db = ProjectDatabase()
        db.open(path)
        _seed(db)
        stamped = _stamp(db, master_hash="$2b$bcryptfakehash")
        db.close()

        db2 = _reopen(path)
        stored = db2.get_meta("integrity_hmac")
        # Recompute with the same key that produced the stamp.
        expected_keyed = ProjectSaver.compute_integrity_hmac(db2, "$2b$bcryptfakehash")
        assert stored == stamped
        assert stored == expected_keyed

    def test_no_mismatch_after_volatile_writes_then_reopen(self, tmp_path):
        """Reproduces the reported bug: open, touch ui_state/history, reopen.

        Under the old whole-file hash this changed the bytes and triggered a
        master-password prompt. The logical digest must stay matched.
        """
        path = str(tmp_path / "p.arch")
        db = ProjectDatabase()
        db.open(path)
        _seed(db)
        master = "$2b$somebcrypthash"
        db.set_meta("master_password_hash", master)
        _stamp(db, master_hash=master)
        db.close()

        # Simulate a view/edit session that writes volatile state but never saves
        db2 = _reopen(path)
        db2.set_ui_state("active_model_id", "1")
        db2.add_history_entry("opened project")
        db2.commit()
        db2.close()

        # Next open: verify integrity the way load_project does
        db3 = _reopen(path)
        stored = db3.get_meta("integrity_hmac")
        expected = ProjectSaver.compute_integrity_hmac(db3, db3.get_meta("master_password_hash"))
        assert stored == expected, "volatile writes must not break integrity"

    def test_tamper_is_detected(self, tmp_path):
        path = str(tmp_path / "p.arch")
        db = ProjectDatabase()
        db.open(path)
        mid = _seed(db)
        master = "$2b$somebcrypthash"
        db.set_meta("master_password_hash", master)
        _stamp(db, master_hash=master)
        db.close()

        # Tamper with content directly, WITHOUT re-stamping
        db2 = _reopen(path)
        db2.upsert_model_row(mid, 0, {"Signal": "EVIL", "Value": "INJECTED"})
        db2.commit()
        db2.close()

        db3 = _reopen(path)
        stored = db3.get_meta("integrity_hmac")
        expected = ProjectSaver.compute_integrity_hmac(db3, db3.get_meta("master_password_hash"))
        assert stored != expected, "tampering must be detected as a mismatch"

    def test_legacy_project_has_no_stored_integrity(self, tmp_path):
        """A project saved before this feature has no integrity_hmac and must
        not be treated as tampered (load_project opens it silently)."""
        path = str(tmp_path / "legacy.arch")
        db = ProjectDatabase()
        db.open(path)
        _seed(db)  # no _stamp()
        db.close()

        db2 = _reopen(path)
        assert db2.get_meta("integrity_hmac") is None

    def test_wrong_key_does_not_verify(self, tmp_path):
        """The HMAC is keyed by the master-password hash: a different key must
        not validate the same content."""
        db = ProjectDatabase()
        db.open(str(tmp_path / "p.arch"))
        _seed(db)
        a = ProjectSaver.compute_integrity_hmac(db, "hashA")
        b = ProjectSaver.compute_integrity_hmac(db, "hashB")
        assert a != b
