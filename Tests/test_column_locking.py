import sys
import os
import tempfile
from unittest.mock import MagicMock, patch

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from PyQt6 import QtCore
from main import ApplicationWindow
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Application_Logic.Logic_Database import ProjectDatabase
from UI.column_types import ReleaseResultColumn

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)


def _create_project(db_path: str):
    from Tests.test_helpers import make_project_db
    db = make_project_db(
        db_path,
        layout=[
            ("TC. ID", "Static Text", True),
            ("Release_R12_Result", "ReleaseResultColumn", True),
        ],
        models=[{
            "name": "Architecture_1",
            "status": "In Work",
            "rows": [{"TC. ID": {"text": "TC_001"}}],
        }],
        releases=[
            {"name": "R12", "elf_hash": "hash_12", "description": "R12 Release"},
            {"name": "R13", "elf_hash": "hash_13", "description": "R13 Release"},
        ],
        settings={"default_cyclicity": "10"},
    )
    # Set R12 as active
    releases = db.get_all_releases()
    r12 = next(r for r in releases if r["name"] == "R12")
    db.set_active_release(r12["id"])
    db.commit()
    db.close()


def test_column_locking():
    print("=" * 70)
    print("TESTING COLUMN LOCKING AND BASELINE LOCKING")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        proj_path = os.path.join(tmp, "test_locking.arch")
        _create_project(proj_path)

        with patch.object(ApplicationWindow, 'new_project'):
            window = ApplicationWindow()

        success, msg = ProjectSaver.load_project(window, proj_path)
        assert success is True, f"Failed to load project: {msg}"

        active_rel = window.arch_controller.release_manager.get_active_release()
        assert active_rel is not None
        assert active_rel.name == "R12"

        table = window.arch_controller.table
        active_cols = window.arch_controller.active_columns

        r12_col_idx = -1
        for i, col in enumerate(active_cols):
            if col.name == "Release_R12_Result":
                r12_col_idx = i
                break
        assert r12_col_idx != -1, "Could not find Release_R12_Result column"

        # 1. Active, non-baselined state — should be editable
        window.arch_controller.load_active_model_to_table()

        cb = table.cellWidget(0, r12_col_idx)
        assert cb is not None, "Expected combobox widget for active release result"
        assert cb.isEnabled() is True, "Expected widget to be enabled for active release"
        cb.setCurrentText("Passed")

        print("Test 1: Release Result column is editable when release is active and not baselined: PASSED")

        # 2. Switch active release to R13 — R12 result should be locked
        r13_idx = next(i for i, r in enumerate(window.arch_controller.release_manager.releases)
                       if r.name == "R13")
        window.arch_controller.release_manager.set_active_release(r13_idx)
        assert window.arch_controller.release_manager.get_active_release().name == "R13"

        window.arch_controller.load_active_model_to_table()

        cb2 = table.cellWidget(0, r12_col_idx)
        if cb2:
            assert cb2.isEnabled() is False, "Expected widget to be disabled for inactive release"

        print("Test 2: Release Result column is locked when release is inactive: PASSED")

        # 3. Switch back to R12, baseline it, then verify locking
        r12_idx = next(i for i, r in enumerate(window.arch_controller.release_manager.releases)
                       if r.name == "R12")
        window.arch_controller.release_manager.set_active_release(r12_idx)
        assert window.arch_controller.release_manager.get_active_release().name == "R12"
        window.arch_controller.load_active_model_to_table()

        cb3 = table.cellWidget(0, r12_col_idx)
        if cb3:
            assert cb3.isEnabled() is True, "Expected widget to re-enable when release is active again"

        layout_data = window.arch_controller.get_current_layout_data()
        model_cache = window.arch_controller.model_manager.get_active_model().data_cache
        window.arch_controller.release_manager.create_baseline(r12_idx, "R12_Baseline", layout_data, active_model_data=model_cache)

        window.arch_controller.load_active_model_to_table()

        cb4 = table.cellWidget(0, r12_col_idx)
        if cb4:
            assert cb4.isEnabled() is False, "Expected widget to be disabled for baselined release"

        print("Test 3: Release Result column is locked once the release has been baselined: PASSED")
        print("\nALL COLUMN LOCKING UNIT TESTS PASSED!")


if __name__ == "__main__":
    test_column_locking()
    os._exit(0)
