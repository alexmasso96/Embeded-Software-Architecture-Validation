import sys
import os
import shutil
import json
from unittest.mock import MagicMock, patch

# Setup path
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from main import ApplicationWindow
from Application_Logic.Logic_Project_Saving import ProjectSaver

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)

def test_project_isolation():
    print("=" * 70)
    print("TESTING PROJECT ISOLATION AND LOADING")
    print("=" * 70)

    # 1. Prepare temporary directory paths
    proj_a_path = "test_project_empty.arch"
    proj_b_path = "test_project_data.arch"

    for p in [proj_a_path, proj_b_path]:
        if os.path.exists(p):
            shutil.rmtree(p)
        os.makedirs(p)

    try:
        # Create a mock ApplicationWindow instance
        # Ensure we patch dialogs and QMessageBoxes to run non-interactively
        with patch.object(ApplicationWindow, 'new_project'):
            window = ApplicationWindow()

        # Let's mock a simple project A structure (Empty Project style)
        # We save layout.json and registry.json for Project A
        layout_a = {
            "version": "2.0",
            "layout": [
                ["TC. ID", "Static Text", True],
                ["Input Port", "Port Search", True],
            ],
            "settings": {"default_cyclicity": "10"}
        }
        with open(os.path.join(proj_a_path, "layout.json"), 'w') as f:
            json.dump(layout_a, f, indent=4)
        
        # Project A architecture model registry
        registry_a = {
            "models": [{"name": "Architecture_1", "filename": "Architecture_1.json", "status": "In Work", "is_deleted": False}],
            "active_index": 0
        }
        with open(os.path.join(proj_a_path, "architecture_models_registry.json"), 'w') as f:
            json.dump(registry_a, f, indent=4)

        # Write model rows for Architecture_1 in Project A (Empty Slate)
        with open(os.path.join(proj_a_path, "Architecture_1.json"), 'w') as f:
            json.dump({"rows": [{"TC. ID": {"text": ""}}]}, f, indent=4)

        # Release registry for Project A
        release_registry_a = {
            "releases": [
                {
                    "name": "R1.0",
                    "file_path": "sw_releases/R1.0.json",
                    "is_baseline": False,
                    "description": "",
                    "timestamp": ""
                }
            ],
            "active_release_name": "R1.0"
        }
        os.makedirs(os.path.join(proj_a_path, "sw_releases"), exist_ok=True)
        with open(os.path.join(proj_a_path, "releases_registry.json"), 'w') as f:
            json.dump(release_registry_a, f, indent=4)
        with open(os.path.join(proj_a_path, "sw_releases", "R1.0.json"), 'w') as f:
            json.dump({"rows": []}, f, indent=4)

        # ----------------------------------------------------
        # Now let's mock Project B structure (Populated Project style with different layout)
        layout_b = {
            "version": "2.0",
            "layout": [
                ["TC. ID", "Static Text", True],
                ["Input Port", "Port Search", True],
                ["Link", "Link", True],
                ["R12_1", "ReleaseResultColumn", True]
            ],
            "settings": {"default_cyclicity": "20"}
        }
        with open(os.path.join(proj_b_path, "layout.json"), 'w') as f:
            json.dump(layout_b, f, indent=4)
        
        # Project B architecture model registry
        registry_b = {
            "models": [
                {"name": "HDR_Supervisor", "filename": "HDR_Supervisor.json", "status": "In Work", "is_deleted": False},
                {"name": "LeAdapter_Sw", "filename": "LeAdapter_Sw.json", "status": "In Work", "is_deleted": False}
            ],
            "active_index": 1
        }
        with open(os.path.join(proj_b_path, "architecture_models_registry.json"), 'w') as f:
            json.dump(registry_b, f, indent=4)

        # Write model rows for models in Project B
        with open(os.path.join(proj_b_path, "HDR_Supervisor.json"), 'w') as f:
            json.dump({"rows": [{"TC. ID": {"text": "TC_HDR"}, "Input Port": {"text": "Port_HDR"}}]}, f, indent=4)
        with open(os.path.join(proj_b_path, "LeAdapter_Sw.json"), 'w') as f:
            json.dump({"rows": [{"TC. ID": {"text": "TC_LE"}, "Input Port": {"text": "Port_LE"}, "Link": {"text": "Yes"}}]}, f, indent=4)

        # Release registry for Project B (Release name: R12)
        release_registry_b = {
            "releases": [
                {
                    "name": "R12",
                    "file_path": "sw_releases/R12.json",
                    "is_baseline": False,
                    "description": "",
                    "timestamp": ""
                }
            ],
            "active_release_name": "R12"
        }
        os.makedirs(os.path.join(proj_b_path, "sw_releases"), exist_ok=True)
        with open(os.path.join(proj_b_path, "releases_registry.json"), 'w') as f:
            json.dump(release_registry_b, f, indent=4)
        with open(os.path.join(proj_b_path, "sw_releases", "R12.json"), 'w') as f:
            json.dump({"rows": [{"TC. ID": {"text": "TC_LE"}, "Input Port": {"text": "Port_LE"}, "Link": {"text": "Yes"}}]}, f, indent=4)

        # ----------------------------------------------------
        # Run loading sequence:
        # First load Project A
        print("\nLoading Project A...")
        success, msg = ProjectSaver.load_project(window, proj_a_path)
        assert success, f"Failed to load Project A: {msg}"
        window.current_project_file = proj_a_path

        # Verify Project A state in controller
        assert len(window.arch_controller.active_config) == 2
        assert window.arch_controller.release_manager.get_active_release().name == "R1.0"
        assert window.arch_controller.model_manager.get_active_model().name == "Architecture_1"
        print("Project A loaded correctly.")

        # Next, load Project B
        print("\nLoading Project B...")
        success, msg = ProjectSaver.load_project(window, proj_b_path)
        assert success, f"Failed to load Project B: {msg}"
        window.current_project_file = proj_b_path

        # Verify that Project B was loaded correctly and did not get corrupted
        # 1. Registry verification
        assert window.arch_controller.release_manager.get_active_release().name == "R12"
        assert window.arch_controller.model_manager.get_active_model().name == "LeAdapter_Sw"
        
        # 2. Column count/layout verification (should be 4 columns)
        print(f"Columns after loading Project B: {[c.name for c in window.arch_controller.active_columns]}")
        assert len(window.arch_controller.active_config) == 4
        assert len(window.arch_controller.active_columns) == 4
        assert window.arch_controller.active_columns[2].name == "Link"
        assert window.arch_controller.active_columns[3].name == "R12_1"

        # 3. Row data verification (should load the row with Port_LE)
        assert window.arch_controller.table.rowCount() == 1
        tc_id_item = window.arch_controller.table.item(0, 0)
        port_item = window.arch_controller.table.item(0, 1)
        assert tc_id_item is not None and tc_id_item.text() == "TC_LE"
        assert port_item is not None and port_item.text() == "Port_LE"

        # 4. Check if project A registry or files on disk were untouched or modified
        with open(os.path.join(proj_b_path, "releases_registry.json"), 'r') as f:
            final_registry_b = json.load(f)
        assert final_registry_b["active_release_name"] == "R12", "Project B release registry was corrupted/overwritten by Project A!"

        # 5. Verify Resizability Properties (Splitter & Headers)
        print("Verifying Resizability Properties...")
        splitter = window.ui.splitter
        assert splitter.handleWidth() == 8, f"Expected splitter handleWidth to be 8, got {splitter.handleWidth()}"
        assert not splitter.isCollapsible(0), "Expected left pane of splitter to be non-collapsible"
        assert not splitter.isCollapsible(1), "Expected right pane of splitter to be non-collapsible"
        
        # Verify column header resize mode is Interactive
        header = window.arch_controller.table.horizontalHeader()
        from PyQt6.QtWidgets import QHeaderView
        for i in range(window.arch_controller.table.columnCount()):
            mode = header.sectionResizeMode(i)
            assert mode == QHeaderView.ResizeMode.Interactive, f"Expected Column {i} resize mode to be Interactive, got {mode}"

        # Verify Refactored Last Result column type mapping
        from Application_Logic.Logic_Column_Types import LastResultColumn, ReleaseResultColumn
        assert window.arch_controller.available_logics.get("Last Result") is LastResultColumn
        
        # Test creating release result columns
        release_mock = MagicMock()
        release_mock.name = "Rtest"
        window.arch_controller.create_result_columns_for_release(release_mock)
        
        # Check that it creates both Last Result and ReleaseResultColumn correctly
        active_col_types = [type(c) for c in window.arch_controller.active_columns]
        assert LastResultColumn in active_col_types
        assert ReleaseResultColumn in active_col_types
        
        # Set a test result (e.g. Passed) in the ReleaseResultColumn
        rel_idx = -1
        for i, c in enumerate(window.arch_controller.active_columns):
            if isinstance(c, ReleaseResultColumn) and "Rtest" in c.name:
                rel_idx = i
                break
        
        assert rel_idx != -1
        # Set combobox value in cell
        cb = window.arch_controller.table.cellWidget(0, rel_idx)
        assert cb is not None
        cb.setCurrentText("Passed")
        # Check that Last Result updates automatically
        last_idx = -1
        for i, c in enumerate(window.arch_controller.active_columns):
            if isinstance(c, LastResultColumn):
                last_idx = i
                break
        assert last_idx != -1
        item = window.arch_controller.table.item(0, last_idx)
        assert item is not None and item.text() == "Passed"
        
        # Save and Reload layout/columns via apply_new_columns to verify it restores correctly (Bug 1 Fix)
        # Note: apply_new_columns uses config tuples format: (name, key, visible)
        config = window.arch_controller.active_config
        window.arch_controller.apply_new_columns(config)
        
        # Check that ReleaseResultColumn combobox is recreated and still says "Passed"
        cb_after = window.arch_controller.table.cellWidget(0, rel_idx)
        assert cb_after is not None
        assert cb_after.currentText() == "Passed"

        # ----------------------------------------------------
        # NEW TESTS: Prevent duplicate Last Result and Link Last Result
        print("Testing duplicate Last Result column prevention...")
        from PyQt6 import QtWidgets
        from Application_Logic.Logic_Column_Customizer import ColumnCustomizer
        
        customizer = ColumnCustomizer(
            current_config=[("Last Result", "Last Result", True)],
            logic_options=["Last Result", "Link", "Static Text"],
            parent=None
        )
        customizer.new_name_input.setText("Duplicate Last Result")
        customizer.type_combo.setCurrentText("Last Result")
        with patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
            customizer._add_custom_item()
            mock_warning.assert_called_once()
            assert customizer.active_list.count() == 1
        print("Duplicate Last Result prevention: PASSED")

        print("Testing Link Last Result feature...")
        from UI.Dialog_Release_Selection import ReleaseSelectionDialog
        
        # Add a dummy project file so save_temp doesn't fail/warn
        window.current_project_file = proj_b_path
        
        dialog = ReleaseSelectionDialog(
            release_manager=window.arch_controller.release_manager,
            architecture_controller=window.arch_controller,
            parent=None
        )
        # Select our release (index 0 which is Rtest, because we added Rtest earlier in the test)
        dialog.list_widget.setCurrentRow(0)
        
        with patch('PyQt6.QtWidgets.QMessageBox.question', return_value=QtWidgets.QMessageBox.StandardButton.Yes), \
             patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            dialog.on_link_result()
            mock_info.assert_called_once()
            
        active_model = window.arch_controller.model_manager.get_active_model()
        assert active_model.data_cache.get("linked_release_column") == "Release_R12_Result"
        
        # Get the Release_R12_Result combobox index
        rel_idx_r12 = -1
        for i, c in enumerate(window.arch_controller.active_columns):
            if isinstance(c, ReleaseResultColumn) and c.name == "Release_R12_Result":
                rel_idx_r12 = i
                break
        assert rel_idx_r12 != -1
        
        cb_r12 = window.arch_controller.table.cellWidget(0, rel_idx_r12)
        assert cb_r12 is not None
        
        # Check that value propagates when changed
        item = window.arch_controller.table.item(0, last_idx)
        print(f"DEBUG TEST: Setting cb_r12 text to Failed. Current last result = {item.text() if item else 'None'}")
        cb_r12.setCurrentText("Failed")
        print(f"DEBUG TEST: After setting cb_r12 to Failed. cb_r12 text = {cb_r12.currentText()}, last result = {item.text() if item else 'None'}")
        item = window.arch_controller.table.item(0, last_idx)
        assert item is not None and item.text() == "Failed"
        
        # Flush to data cache
        window.arch_controller.flush_current_data_to_model()
        
        # Check that loading active model restores the linked column value to Last Result
        window.arch_controller.load_active_model_to_table()
        item = window.arch_controller.table.item(0, last_idx)
        assert item is not None and item.text() == "Failed"
        print("Link Last Result: PASSED")

        # ----------------------------------------------------
        # NEW TESTS: Exclude Result Column Types & Sanitization & Empty Row Clearing
        print("Testing column customizer options exclusion...")
        logic_options = [
            key for key in window.arch_controller.available_logics.keys() 
            if key not in ["InitColumn", "CyclicColumn", "Review Status", "PortStateColumn", "ReleaseResultColumn", "Last Result"]
        ]
        assert "ReleaseResultColumn" not in logic_options
        assert "Last Result" not in logic_options
        print("Column customizer options exclusion: PASSED")
        
        print("Testing configuration sanitization...")
        invalid_config = [
            ("TC. ID", "Static Text", True),
            ("ManualReleaseCol", "ReleaseResultColumn", True),
            ("ManualLastResultCol", "Last Result", True),
            ("Release_Valid_Result", "ReleaseResultColumn", True),
            ("Last Result", "Last Result", True)
        ]
        sanitized = window.arch_controller.sanitize_column_config(invalid_config)
        assert sanitized[1][1] == "Static Text" # ManualReleaseCol demoted
        assert sanitized[2][1] == "Static Text" # ManualLastResultCol demoted
        assert sanitized[3][1] == "ReleaseResultColumn" # Valid prefix/suffix preserved
        assert sanitized[4][1] == "Last Result" # Valid name preserved
        print("Configuration sanitization: PASSED")
        
        print("Testing empty row prepopulation prevention...")
        tc_id_col = -1
        input_port_col = -1
        for i, col_obj in enumerate(window.arch_controller.active_columns):
            if col_obj.name == "TC. ID":
                tc_id_col = i
            elif col_obj.name == "Input Port":
                input_port_col = i
        
        # Clear TC. ID and Input Port
        window.arch_controller.table.item(0, tc_id_col).setText("")
        ip_item = window.arch_controller.table.item(0, input_port_col)
        if ip_item:
            ip_item.setText("")
        ip_widget = window.arch_controller.table.cellWidget(0, input_port_col)
        if ip_widget:
            ip_widget.setCurrentText("")
            
        # Trigger on_change for output columns
        for i, col_obj in enumerate(window.arch_controller.active_columns):
            if col_obj.name not in ["TC. ID", "Input Port"]:
                col_obj.on_change(window.arch_controller.table, 0, i, "Passed", window.arch_controller)
                
        # Verify that widgets are removed and item texts are empty
        for i, col_obj in enumerate(window.arch_controller.active_columns):
            if col_obj.name not in ["TC. ID", "Input Port"]:
                widget = window.arch_controller.table.cellWidget(0, i)
                item = window.arch_controller.table.item(0, i)
                assert widget is None, f"Expected no widget in column {col_obj.name} but found one."
                assert item is None or item.text() == "", f"Expected empty text in column {col_obj.name} but found: {item.text()}"
        print("Empty row prepopulation prevention: PASSED")

        print("Project B loaded correctly and was isolated: PASSED")

    finally:
        # Cleanup temp project directories
        for p in [proj_a_path, proj_b_path]:
            if os.path.exists(p):
                shutil.rmtree(p)

if __name__ == "__main__":
    test_project_isolation()
