import sys
import os
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup path
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import QtWidgets

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)

import UI
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
from Application_Logic.Logic_Column_Types import PortSearchColumn, LinkColumn, ReviewColumn
from main import ApplicationWindow

def test_import_flow():
    print("=" * 70)
    print("TESTING EXCEL ARCHITECTURE IMPORT FLOW")
    print("=" * 70)

    # Setup temp project path
    temp_proj = "test_import_project.arch"
    if os.path.exists(temp_proj):
        shutil.rmtree(temp_proj)
    os.makedirs(temp_proj)

    excel_path = os.path.abspath("Data Set/CHLC_Rhapsody_Export_R12_2_Star_3_5.xlsx")
    assert os.path.exists(excel_path), f"Excel file not found at {excel_path}"

    # Initialize a dummy project registry/manager
    mgr = ArchitectureManager(temp_proj)
    # Default model is created upon initialization: "Architecture_1"
    assert len(mgr.models) == 1
    assert mgr.models[0].name == "Architecture_1"

    # Create a mock ApplicationWindow to avoid triggering timers and interactive dialogs
    window = QMainWindow()
    window.ui = UI.Ui_MainWindow()
    window.ui.setupUi(window)
    window.current_project_file = temp_proj

    # Instantiate Controller
    controller = ArchitectureTabController(window)
    controller.model_manager = mgr

    # Setup the mock dialog inputs/actions
    mock_file_dialog = MagicMock(return_value=(excel_path, "Excel Files (*.xlsx)"))
    
    # 1. Test Automated Import Mode where:
    # - "LeAdapter_Sw" -> FuzzyMatchPromptDialog -> chooses "<Create New Model>"
    # - ConfirmationDialog -> confirms
    # - Info Box -> informs about the count

    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', mock_file_dialog), \
         patch('Application_Logic.Logic_Architecture_Table.ImportModeDialog') as MockModeDialog, \
         patch('Application_Logic.Logic_Architecture_Table.FuzzyMatchPromptDialog') as MockFuzzyDialog, \
         patch('Application_Logic.Logic_Architecture_Table.ImportConfirmationDialog') as MockConfirmDialog, \
         patch('PyQt6.QtWidgets.QMessageBox.information') as MockInfo, \
         patch('PyQt6.QtWidgets.QMessageBox.warning') as MockWarning:

        # Mock Mode Dialog to choose Automated
        mode_instance = MagicMock()
        mode_instance.exec.return_value = True
        mode_instance.selected_mode = "automated"
        MockModeDialog.return_value = mode_instance

        # Mock Fuzzy Dialog to choose "<Create New Model>"
        fuzzy_instance = MagicMock()
        fuzzy_instance.exec.return_value = True
        fuzzy_instance.selected_model = "<Create New Model>"
        MockFuzzyDialog.return_value = fuzzy_instance

        # Mock Confirmation Dialog to choose Confirm
        confirm_instance = MagicMock()
        confirm_instance.exec.return_value = True
        confirm_instance.selected_action = "confirm"
        MockConfirmDialog.return_value = confirm_instance

        print("\n[TEST 1] Triggering Automated Excel Import...")
        controller.import_architecture_excel()

        # Verify a new model is created
        model_names = [m.name for m in mgr.models]
        print(f"Models after import: {model_names}")
        assert "LeAdapter_Sw" in model_names, "LeAdapter_Sw should be created since it was mapped to <Create New Model>"

        # Verify Link Column is added to config
        print(f"Active Columns config: {controller.active_config}")
        assert any(col[1] == "Link" for col in controller.active_config), "Link column must be added to active config"

        # Check imported ports in LeAdapter_Sw model
        imported_model = next(m for m in mgr.models if m.name == "LeAdapter_Sw")
        rows = imported_model.data_cache.get("rows", [])
        print(f"Total imported ports: {len(rows)}")
        assert len(rows) > 0, "Should have imported ports from LeAdapter_Sw sheet"

        # Verify a couple of ports and their Link values
        # Let's inspect some of the rows:
        port_names = []
        for r in rows:
            p_val = r.get("TC. ID", {}).get("text", "") # Wait, port column name is "TC. ID" or "Port"?
            # Let's check which column is PortSearchColumn
            port_col_name = next(c.name for c in controller.active_columns if isinstance(c, PortSearchColumn))
            p_val = r.get(port_col_name, {}).get("text", "")
            l_val = r.get("Link", {}).get("text", "")
            port_names.append((p_val, l_val))

        print(f"Sample of imported ports: {port_names[:5]}")
        # Validate that deduplication works: import again into the same model
        # Setup manual import mock to map LeAdapter_Sw to LeAdapter_Sw
        # and select it.
        # This tests that existing ports in LeAdapter_Sw are not re-added.

    # 2. Test Manual Import Mode and Deduplication
    with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', mock_file_dialog), \
         patch('Application_Logic.Logic_Architecture_Table.ImportModeDialog') as MockModeDialog, \
         patch('Application_Logic.Logic_Architecture_Table.ManualImportDialog') as MockManualDialog, \
         patch('Application_Logic.Logic_Architecture_Table.ImportConfirmationDialog') as MockConfirmDialog, \
         patch('PyQt6.QtWidgets.QMessageBox.information') as MockInfo:

        # Mock Mode Dialog to choose Manual
        mode_instance = MagicMock()
        mode_instance.exec.return_value = True
        mode_instance.selected_mode = "manual"
        MockModeDialog.return_value = mode_instance

        # Mock Manual Dialog to map 'LeAdapter_Sw' sheet to 'LeAdapter_Sw' model
        manual_instance = MagicMock()
        manual_instance.exec.return_value = True
        # mappings: {sheet_name: (import_bool, target_model)}
        manual_instance.mappings = {
            "LeAdapter_Sw": (True, "LeAdapter_Sw")
        }
        MockManualDialog.return_value = manual_instance

        # Mock Confirmation Dialog to choose Confirm
        confirm_instance = MagicMock()
        confirm_instance.exec.return_value = True
        confirm_instance.selected_action = "confirm"
        MockConfirmDialog.return_value = confirm_instance

        # Get count before
        imported_model = next(m for m in mgr.models if m.name == "LeAdapter_Sw")
        count_before = len(imported_model.data_cache.get("rows", []))

        # Update one port's link status to 'Yes' in the cache before import
        test_port_row = imported_model.data_cache["rows"][0]
        port_col_name = next(c.name for c in controller.active_columns if isinstance(c, PortSearchColumn))
        link_col_name = next(c.name for c in controller.active_columns if isinstance(c, LinkColumn))
        test_port_row[link_col_name]["text"] = "Yes"
        test_port_row[link_col_name]["widget_text"] = "Yes"
        port_name_under_test = test_port_row[port_col_name]["text"]
        print(f"Updating link status of existing port '{port_name_under_test}' to 'Yes' in cache before re-import...")

        print("\n[TEST 2] Triggering Manual Excel Import (Testing Deduplication and Link Update)...")
        controller.import_architecture_excel()

        # Check count after
        count_after = len(imported_model.data_cache.get("rows", []))
        print(f"Port count before: {count_before}, after: {count_after}")
        assert count_before == count_after, "Deduplication failed! Ports were re-imported."

        # Verify that the link status was updated back to 'No' (as specified in Excel)
        updated_link_val = test_port_row[link_col_name]["text"]
        print(f"Post-import link status of existing port '{port_name_under_test}': {updated_link_val}")
        assert updated_link_val == "No", "Link status was not updated back to 'No' on re-import!"

        # Verify that Info Box was called with 0 new ports
        MockInfo.assert_called_once()
        args, kwargs = MockInfo.call_args
        msg = args[2]
        print(f"Completion Message: {msg}")
        assert "Total new ports imported: 0" in msg, "Completion message should indicate 0 new ports imported"

    # 3. Test Review Status coloring logic (No effect on Link column)
    print("\n[TEST 3] Verifying Review Status isolation from Link column coloring...")
    # Load model and trigger active widgets loading
    idx = next(i for i, m in enumerate(controller.model_manager.models) if m.name == "LeAdapter_Sw")
    controller.model_manager.set_active_model(idx)
    controller.load_active_model_to_table()
    
    table = controller.table
    assert table.rowCount() > 0, "Table should have rows populated"
    
    review_col_idx = -1
    link_col_idx = -1
    for i, col_obj in enumerate(controller.active_columns):
        if isinstance(col_obj, ReviewColumn):
            review_col_idx = i
        elif isinstance(col_obj, LinkColumn):
            link_col_idx = i
            
    assert review_col_idx != -1, "ReviewColumn not found"
    assert link_col_idx != -1, "LinkColumn not found"
    
    review_widget = table.cellWidget(0, review_col_idx)
    link_widget = table.cellWidget(0, link_col_idx)
    
    assert isinstance(review_widget, QtWidgets.QComboBox), "Review widget should be a QComboBox"
    assert isinstance(link_widget, QtWidgets.QComboBox), "Link widget should be a QComboBox"
    
    initial_link_style = link_widget.styleSheet()
    print(f"Initial Link Widget StyleSheet: {initial_link_style}")
    
    print("Changing Review Status to 'Reviewed'...")
    review_widget.setCurrentText("Reviewed")
    
    post_change_link_style = link_widget.styleSheet()
    print(f"Post-Change Link Widget StyleSheet: {post_change_link_style}")
    
    assert post_change_link_style == initial_link_style, "Link Widget StyleSheet changed after Review Status changed!"
    print("Review Status change does not affect Link Column coloring: PASSED")

    # Clean up
    shutil.rmtree(temp_proj)
    print("\nALL EXCEL IMPORT TESTS PASSED ✓")

if __name__ == "__main__":
    test_import_flow()
