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

def test_column_locking():
    print("=" * 70)
    print("TESTING COLUMN LOCKING AND BASELINE LOCKING")
    print("=" * 70)

    proj_path = "test_locking_proj.arch"
    if os.path.exists(proj_path):
        shutil.rmtree(proj_path)
    os.makedirs(proj_path)

    try:
        # Create minimal project files
        layout = {
            "version": "2.0",
            "layout": [
                ["TC. ID", "Static Text", True],
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
                {"TC. ID": {"text": "TC_001"}}
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
                },
                {
                    "name": "R13",
                    "file_path": "sw_releases/R13.json",
                    "is_baseline": False,
                    "description": "R13 Release",
                    "timestamp": "",
                    "elf_hash": "hash_13"
                }
            ],
            "active_release_name": "R12"
        }
        os.makedirs(os.path.join(proj_path, "sw_releases"), exist_ok=True)
        with open(os.path.join(proj_path, "releases_registry.json"), 'w') as f:
            json.dump(release_registry, f, indent=4)
        
        # Write flat ELF cache format to releases
        with open(os.path.join(proj_path, "sw_releases/R12.json"), 'w') as f:
            json.dump({"elf_path": "", "elf_hash": "hash_12", "symbols": [], "functions": [], "structures": {}, "global_vars": {}}, f, indent=4)
        with open(os.path.join(proj_path, "sw_releases/R13.json"), 'w') as f:
            json.dump({"elf_path": "", "elf_hash": "hash_13", "symbols": [], "functions": [], "structures": {}, "global_vars": {}}, f, indent=4)

        # Instantiate ApplicationWindow with mocked dialogs
        with patch.object(ApplicationWindow, 'new_project'):
            window = ApplicationWindow()

        # Load project non-interactively
        success, msg = ProjectSaver.load_project(window, proj_path)
        assert success is True, f"Failed to load project: {msg}"

        # Verify R12 is active
        active_rel = window.arch_controller.release_manager.get_active_release()
        assert active_rel is not None
        assert active_rel.name == "R12"

        # Table & Column details
        table = window.arch_controller.table
        active_cols = window.arch_controller.active_columns

        # Verify Release_R12_Result is at column index 1
        r12_col_idx = -1
        for i, col in enumerate(active_cols):
            if col.name == "Release_R12_Result":
                r12_col_idx = i
                break
        assert r12_col_idx != -1, "Could not find Release_R12_Result column"

        # 1. Test active, non-baselined state (R12 is active)
        # Force reload to ensure cell widgets are rendered
        window.arch_controller.load_active_model_to_table()
        
        cb = table.cellWidget(0, r12_col_idx)
        assert cb is not None, "Expected combobox widget for active release result"
        assert cb.isEnabled() is True, "Expected widget to be enabled for active release"
        
        cb.setCurrentText("Passed")

        item = table.item(0, r12_col_idx)
        if item:
            assert (item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) == QtCore.Qt.ItemFlag.ItemIsEditable, "Expected item to be editable"

        print("Test 1: Release Result column is editable when release is active and not baselined: PASSED")

        # 2. Test inactive state (Switch active release to R13)
        window.arch_controller.release_manager.set_active_release(1) # R13 is at index 1
        assert window.arch_controller.release_manager.get_active_release().name == "R13"

        # Refresh table to update lock state
        window.arch_controller.load_active_model_to_table()
        
        # Check that Release_R12_Result is now locked
        cb2 = table.cellWidget(0, r12_col_idx)
        if cb2:
            assert cb2.isEnabled() is False, "Expected widget to be disabled for inactive release"

        item2 = table.item(0, r12_col_idx)
        if item2:
            assert (item2.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) != QtCore.Qt.ItemFlag.ItemIsEditable, "Expected item to be non-editable"

        print("Test 2: Release Result column is locked when release is inactive: PASSED")

        # 3. Switch back to R12, then create a baseline to verify locking
        window.arch_controller.release_manager.set_active_release(0) # R12 active again
        assert window.arch_controller.release_manager.get_active_release().name == "R12"
        window.arch_controller.load_active_model_to_table()

        cb3 = table.cellWidget(0, r12_col_idx)
        if cb3:
            assert cb3.isEnabled() is True, "Expected widget to re-enable when release is active again"

        # Create baseline of active release (R12 is at index 0)
        # Release_R12_Result should get locked permanently in the live view
        model_cache = window.arch_controller.model_manager.get_active_model().data_cache
        window.arch_controller.release_manager.create_baseline(0, "R12_Baseline", layout, active_model_data=model_cache)
        
        # Trigger reload to apply baseline locking visuals
        window.arch_controller.load_active_model_to_table()

        # R12 is still active in memory, but R12 has now been baselined!
        # Thus, Release_R12_Result MUST be locked.
        cb4 = table.cellWidget(0, r12_col_idx)
        if cb4:
            assert cb4.isEnabled() is False, "Expected widget to be disabled for baselined release"

        item4 = table.item(0, r12_col_idx)
        if item4:
            assert (item4.flags() & QtCore.Qt.ItemFlag.ItemIsEditable) != QtCore.Qt.ItemFlag.ItemIsEditable, "Expected item to be non-editable"

        print("Test 3: Release Result column is locked once the release has been baselined: PASSED")

        print("\nALL COLUMN LOCKING UNIT TESTS PASSED!")

    finally:
        if os.path.exists(proj_path):
            shutil.rmtree(proj_path)

if __name__ == "__main__":
    test_column_locking()
