import sys
import os
import shutil
import json
from unittest.mock import MagicMock, patch

# Setup path
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from PyQt6 import QtCore
from main import ApplicationWindow
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Application_Logic.Logic_Column_Types import ReleaseResultColumn

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)

def test_baseline_locking():
    print("=" * 70)
    print("TESTING BASELINE VIEW LOCKING AND UNLOCKING")
    print("=" * 70)

    proj_path = "test_baseline_locking_proj.arch"
    if os.path.exists(proj_path):
        shutil.rmtree(proj_path)
    os.makedirs(proj_path)

    try:
        # Create minimal project files
        layout = {
            "version": "2.0",
            "layout": [
                ["TC. ID", "Static Text", True],
                ["Review Status", "Review Status", True],
                ["Port State", "PortStateColumn", True],
                ["Link", "Link", True],
                ["Release_R12_Result", "ReleaseResultColumn", True]
            ],
            "settings": {"default_cyclicity": "10"}
        }
        with open(os.path.join(proj_path, "layout.json"), 'w') as f:
            json.dump(layout, f, indent=4)

        registry = {
            "models": [{"name": "Architecture_1", "filename": "Architecture_1.json", "status": "In Work", "is_deleted": False}],
            "active_index": 0
        }
        with open(os.path.join(proj_path, "architecture_models_registry.json"), 'w') as f:
            json.dump(registry, f, indent=4)

        model_data = {
            "rows": [
                {
                    "TC. ID": {"text": "TC_001"},
                    "Review Status": {"text": "Not Reviewed"},
                    "Port State": {"text": "In Work"},
                    "Link": {"text": "No"},
                    "Release_R12_Result": {"text": "Not Run"}
                }
            ]
        }
        with open(os.path.join(proj_path, "Architecture_1.json"), 'w') as f:
            json.dump(model_data, f, indent=4)

        release_registry = {
            "releases": [
                {
                    "name": "R12",
                    "file_path": "sw_releases/R12.json",
                    "is_baseline": False,
                    "description": "R12 Release",
                    "timestamp": "",
                    "elf_hash": "hash_12"
                }
            ],
            "active_release_name": "R12"
        }
        os.makedirs(os.path.join(proj_path, "sw_releases"), exist_ok=True)
        with open(os.path.join(proj_path, "releases_registry.json"), 'w') as f:
            json.dump(release_registry, f, indent=4)
        
        with open(os.path.join(proj_path, "sw_releases/R12.json"), 'w') as f:
            json.dump({"elf_path": "", "elf_hash": "hash_12", "symbols": [], "functions": [], "structures": {}, "global_vars": {}}, f, indent=4)

        # Instantiate ApplicationWindow with mocked dialogs
        with patch.object(ApplicationWindow, 'new_project'):
            window = ApplicationWindow()

        # Load project non-interactively
        success, msg = ProjectSaver.load_project(window, proj_path)
        assert success is True, f"Failed to load project: {msg}"

        table = window.arch_controller.table
        controller = window.arch_controller

        # Refresh table to populate row widgets
        controller.load_active_model_to_table()
        
        # Verify initial live view state is editable
        tc_item = table.item(0, 0)
        assert tc_item is not None
        assert (tc_item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) == QtCore.Qt.ItemFlag.ItemIsEditable, "Expected TC ID to be editable in live view"
        
        review_widget = table.cellWidget(0, 1)
        assert review_widget is not None
        assert review_widget.isEnabled() is True, "Expected Review dropdown to be enabled in live view"
        
        state_widget = table.cellWidget(0, 2)
        assert state_widget is not None
        assert state_widget.isEnabled() is True, "Expected Port State dropdown to be enabled in live view"

        link_widget = table.cellWidget(0, 3)
        assert link_widget is not None
        assert link_widget.isEnabled() is True, "Expected Link dropdown to be enabled in live view"

        result_widget = table.cellWidget(0, 4)
        assert result_widget is not None
        assert result_widget.isEnabled() is True, "Expected Release Result dropdown to be enabled in live view"

        print("Verification 1: Live view widgets and items are enabled/editable: PASSED")

        # Create a baseline
        # Switch to R12 and baseline it
        model_cache = controller.model_manager.get_active_model().data_cache
        layout_data = controller.get_current_layout_data()
        baseline = controller.release_manager.create_baseline(0, "R12_Baseline", layout_data, active_model_data=model_cache)
        assert baseline is not None

        # Load the baseline
        # Simulate baseline load
        # In handle_load_baseline, it does load_project_data and sets btn_exit_baseline visible
        controller.btn_exit_baseline.setVisible(True)
        
        # Load the baseline data
        baseline_dir = os.path.dirname(baseline.file_path)
        with open(os.path.join(baseline_dir, "table_data.json"), 'r') as f:
            table_data = json.load(f)
        data_to_load = {
            "config": layout["layout"],
            "settings": layout["settings"],
            "rows": table_data.get("rows", []),
        }
        controller.load_project_data(data_to_load)
        
        # Verify that all widgets are disabled and all items are read-only
        print("Verifying baseline lock status of all cells...")
        for col_idx in range(table.columnCount()):
            widget = table.cellWidget(0, col_idx)
            item = table.item(0, col_idx)
            
            if widget:
                print(f"Col {col_idx} Widget Enabled: {widget.isEnabled()}")
                assert widget.isEnabled() is False, f"Expected cell widget at column {col_idx} to be disabled in baseline view"
            if item:
                print(f"Col {col_idx} Item Flags: {item.flags()}")
                assert (item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) != QtCore.Qt.ItemFlag.ItemIsEditable, f"Expected table item at column {col_idx} to be non-editable in baseline view"
        
        print("Verification 2: All baseline view widgets and items are successfully locked: PASSED")

        # Exit baseline view
        controller.btn_exit_baseline.setVisible(False)
        ProjectSaver.load_project(window, proj_path)
        controller.load_active_model_to_table()

        # Verify editing has been restored
        tc_item_restored = table.item(0, 0)
        assert (tc_item_restored.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) == QtCore.Qt.ItemFlag.ItemIsEditable, "Expected TC ID to be editable after exiting baseline"
        
        review_widget_restored = table.cellWidget(0, 1)
        assert review_widget_restored.isEnabled() is True, "Expected Review dropdown to be enabled after exiting baseline"
        
        state_widget_restored = table.cellWidget(0, 2)
        assert state_widget_restored.isEnabled() is True, "Expected Port State dropdown to be enabled after exiting baseline"

        link_widget_restored = table.cellWidget(0, 3)
        assert link_widget_restored.isEnabled() is True, "Expected Link dropdown to be enabled after exiting baseline"

        result_widget_restored = table.cellWidget(0, 4)
        assert result_widget_restored.isEnabled() is True, "Expected Release Result dropdown to be enabled after exiting baseline"

        print("Verification 3: All widgets and items are successfully unlocked/restored after exiting baseline view: PASSED")
        print("\nALL BASELINE LOCKING UNIT TESTS PASSED!")

    finally:
        if os.path.exists(proj_path):
            shutil.rmtree(proj_path)

if __name__ == "__main__":
    test_baseline_locking()
