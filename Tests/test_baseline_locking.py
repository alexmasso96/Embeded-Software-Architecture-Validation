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
from Application_Logic.Logic_Column_Types import ReleaseResultColumn

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)


def _create_minimal_project(db_path: str):
    """Create a minimal .arch project for baseline locking tests."""
    from Tests.test_helpers import make_project_db
    db = make_project_db(
        db_path,
        layout=[
            ("TC. ID", "Static Text", True),
            ("Review Status", "Review Status", True),
            ("Port State", "PortStateColumn", True),
            ("Link", "Link", True),
            ("Release_R12_Result", "ReleaseResultColumn", True),
        ],
        models=[{
            "name": "Architecture_1",
            "status": "In Work",
            "rows": [{
                "TC. ID": {"text": "TC_001"},
                "Review Status": {"text": "Not Reviewed"},
                "Port State": {"text": "In Work"},
                "Link": {"text": "No"},
                "Release_R12_Result": {"text": "Not Run"},
            }]
        }],
        releases=[{
            "name": "R12",
            "elf_hash": "hash_12",
            "description": "R12 Release",
        }],
        settings={"default_cyclicity": "10"},
    )
    # Set R12 as active
    releases = db.get_all_releases()
    db.set_active_release(releases[0]["id"])
    db.commit()
    db.close()


def test_baseline_locking():
    print("=" * 70)
    print("TESTING BASELINE VIEW LOCKING AND UNLOCKING")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        proj_path = os.path.join(tmp, "test_baseline_locking.arch")
        _create_minimal_project(proj_path)

        with patch.object(ApplicationWindow, 'new_project'):
            window = ApplicationWindow()

        success, msg = ProjectSaver.load_project(window, proj_path)
        assert success is True, f"Failed to load project: {msg}"

        table = window.arch_controller.table
        controller = window.arch_controller

        controller.load_active_model_to_table()

        # Verify initial live view state is editable
        tc_item = table.item(0, 0)
        assert tc_item is not None
        assert (tc_item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) == QtCore.Qt.ItemFlag.ItemIsEditable, \
            "Expected TC ID to be editable in live view"

        review_widget = table.cellWidget(0, 1)
        assert review_widget is not None
        assert review_widget.isEnabled() is True

        state_widget = table.cellWidget(0, 2)
        assert state_widget is not None
        assert state_widget.isEnabled() is True

        link_widget = table.cellWidget(0, 3)
        assert link_widget is not None
        assert link_widget.isEnabled() is True

        result_widget = table.cellWidget(0, 4)
        assert result_widget is not None
        assert result_widget.isEnabled() is True

        print("Verification 1: Live view widgets and items are enabled/editable: PASSED")

        # Create a baseline
        layout_data = controller.get_current_layout_data()
        model_cache = controller.model_manager.get_active_model().data_cache
        baseline = controller.release_manager.create_baseline(0, "R12_Baseline", layout_data, active_model_data=model_cache)
        assert baseline is not None

        # Load the baseline using load_baseline_by_model
        controller.btn_exit_baseline.setVisible(True)

        # Load rows from DB
        db = window.project_db
        rows = db.get_release_rows(baseline.id)
        layout_config = db.load_column_layout()
        data_to_load = {
            "config": layout_config,
            "settings": {"default_cyclicity": "10"},
            "rows": rows,
        }
        controller.load_project_data(data_to_load)

        # Verify that all widgets are disabled and all items are read-only
        print("Verifying baseline lock status of all cells...")
        for col_idx in range(table.columnCount()):
            widget = table.cellWidget(0, col_idx)
            item = table.item(0, col_idx)

            if widget:
                assert widget.isEnabled() is False, \
                    f"Expected cell widget at column {col_idx} to be disabled in baseline view"
            if item:
                assert (item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) != QtCore.Qt.ItemFlag.ItemIsEditable, \
                    f"Expected table item at column {col_idx} to be non-editable in baseline view"

        print("Verification 2: All baseline view widgets and items are successfully locked: PASSED")

        # Exit baseline view
        controller.btn_exit_baseline.setVisible(False)
        ProjectSaver.load_project(window, proj_path)
        controller.load_active_model_to_table()

        tc_item_restored = table.item(0, 0)
        assert (tc_item_restored.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) == QtCore.Qt.ItemFlag.ItemIsEditable

        review_widget_restored = table.cellWidget(0, 1)
        assert review_widget_restored.isEnabled() is True

        state_widget_restored = table.cellWidget(0, 2)
        assert state_widget_restored.isEnabled() is True

        link_widget_restored = table.cellWidget(0, 3)
        assert link_widget_restored.isEnabled() is True

        result_widget_restored = table.cellWidget(0, 4)
        assert result_widget_restored.isEnabled() is True

        print("Verification 3: All widgets and items are successfully unlocked/restored after exiting baseline view: PASSED")
        print("\nALL BASELINE LOCKING UNIT TESTS PASSED!")


if __name__ == "__main__":
    test_baseline_locking()
