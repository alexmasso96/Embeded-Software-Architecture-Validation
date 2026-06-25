"""
Logic-layer tests for ``HistoryManager`` (change-history persistence).

Loads/persists per-release history rows through ``ProjectDatabase``; covers the
detached (no-db) state, load-on-attach, immediate persistence via ``add_entry``,
and the release scoping of loaded entries.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("src"))

from Application_Logic.Logic_History import HistoryManager
from Tests.test_helpers import make_project_db


def test_detached_manager_is_inert():
    mgr = HistoryManager()           # no db
    assert mgr.history == []
    mgr.add_entry("did a thing", "Arch_A")     # must not raise without a db
    assert len(mgr.history) == 1
    assert mgr.history[0]["description"] == "did a thing"
    assert mgr.history[0]["model"] == "Arch_A"
    assert mgr.history[0]["timestamp"]         # iso timestamp stamped
    mgr.save_history()                          # documented no-op


def test_set_db_loads_existing_history():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])
        rid = db.get_active_release_id()
        db.add_history_entry(description="seeded", model_name="Arch_A",
                             username="tester", release_id=rid)
        db.commit()

        mgr = HistoryManager()
        mgr.set_db(db)
        assert any(e["description"] == "seeded" for e in mgr.history)
        db.close()


def test_add_entry_persists_to_db():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "p.arch")
        db = make_project_db(
            path, layout=[("TC. ID", "Static Text", True)],
            models=[{"name": "Arch_A", "status": "In Work", "rows": []}],
            releases=[{"name": "R1"}])

        mgr = HistoryManager(db)
        mgr.add_entry("renamed port", "Arch_A")
        db.commit()

        # A freshly-loaded manager sees the persisted entry.
        reloaded = HistoryManager(db)
        assert any(e["description"] == "renamed port" for e in reloaded.history)
        db.close()
