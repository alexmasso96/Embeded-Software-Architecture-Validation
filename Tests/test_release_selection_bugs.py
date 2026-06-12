import sys
import os
import tempfile
import json
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import QtWidgets

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase
from UI.architecture_table import ArchitectureTabController
from UI.Dialog_Release_Selection import ReleaseSelectionDialog
from Tests.test_helpers import make_project_db

app = QApplication.instance() or QApplication(sys.argv)

def _make_controller(window, db_path):
    import UI
    window.ui = UI.Ui_MainWindow()
    window.ui.setupUi(window)
    window.current_project_file = db_path
    window.edit_mode = True
    
    # Open DB and link to controller
    db = ProjectDatabase()
    db.open(db_path)
    window.project_db = db
    
    controller = ArchitectureTabController(window)
    controller.model_manager.set_db(db)
    controller.release_manager.set_db(db)
    
    layout = db.load_column_layout()
    if layout:
        controller.active_config = [(r[0], r[1], r[2]) for r in layout]
        
    controller._rebuild_column_objects()
    controller._setup_table_style()
    controller.load_active_model_to_table()
    window.arch_controller = controller
    return controller

def test_release_selection_dialog_bugs():
    print("Running Release Selection Dialog Bug Tests...")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_bugs.arch")
        json_cache_path = os.path.join(tmp, "project_b_symbols.json")
        
        # 1. Create a mock JSON cache representing Project B symbols
        json_symbols = {
            "elf_path": json_cache_path,
            "elf_hash": "project_b_hash_123",
            "symbols": [
                {
                    "name": "ProjectB_Func",
                    "address": 2000,
                    "size": 100,
                    "symbol_type": "STT_FUNC",
                    "binding": "STB_GLOBAL",
                    "section": ".text"
                }
            ],
            "functions": [
                {
                    "name": "ProjectB_Func",
                    "address": 2000,
                    "size": 100,
                    "parameters": [],
                    "return_type": "void"
                }
            ],
            "structures": {},
            "global_vars": {}
        }
        with open(json_cache_path, "w") as f:
            json.dump(json_symbols, f)

        # 2. Setup the project DB
        # Layout has a Function search column and its (Match) column
        layout = [
            ("TC. ID", "Static Text", True),
            ("Function Input", "Function Search", True),
            ("Function Input (Match)", "Static Text", True)
        ]
        
        # Active Model has a row with "Function Input" = "ProjectB_Func"
        models = [
            {
                "name": "ActiveModel",
                "status": "In Work",
                "rows": [
                    {
                        "TC. ID": {"text": "TC_01"},
                        "Function Input": {"text": "ProjectB_Func"}
                    }
                ]
            }
        ]
        
        # Create DB
        db = make_project_db(db_path, layout=layout, models=models, settings={})
        db.close()
        
        # Initialize MainWindow & Controller
        window = QMainWindow()
        controller = _make_controller(window, db_path)
        
        # 3. Create the release (Project B) pointing to the JSON cache file.
        # This release initially has no rows.
        release = controller.release_manager.create_release(
            name="Project_B_Release",
            copy_from_active=False,
            elf_path=json_cache_path,
            elf_hash="project_b_hash_123"
        )
        
        # Create the .elf_caches folder and copy the json cache file there
        cache_dir = db_path + ".elf_caches"
        os.makedirs(cache_dir, exist_ok=True)
        import shutil
        shutil.copy2(json_cache_path, os.path.join(cache_dir, "elf_project_b_hash_123.json"))

        # Let's verify that the release initially has no rows in DB
        loaded_data_before = controller.release_manager._load_data(release)
        assert len(loaded_data_before.get("rows", [])) == 0
        
        # 4. Open the Release Selection Dialog
        dialog = ReleaseSelectionDialog(
            release_manager=controller.release_manager,
            architecture_controller=controller,
            parent=None
        )
        
        # Set selection to Project_B_Release in the list widget
        for i in range(dialog.list_widget.count()):
            item = dialog.list_widget.item(i)
            if "Project_B_Release" in item.text():
                dialog.list_widget.setCurrentRow(i)
                break
                
        # Simulate loading the release
        with patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warn:
            dialog.on_load_release()
            # Assert no warnings were shown
            mock_warn.assert_not_called()
            
        # Verify that:
        # A. The release data has cloned the active model's rows
        loaded_data_after = controller.release_manager._load_data(release)
        assert len(loaded_data_after.get("rows", [])) == 1
        assert loaded_data_after["rows"][0]["TC. ID"]["text"] == "TC_01"
        assert loaded_data_after["rows"][0]["Function Input"]["text"] == "ProjectB_Func"
        
        # B. The controller's parser/matcher was updated with Project B's JSON symbols
        assert controller.parser.md5_hash == "project_b_hash_123"
        assert "ProjectB_Func" in controller.matcher.all_function_names
        
        # C. The matching column contains the correct Project B function match
        # Let's check that the table widgets / items are loaded and matched
        match_col_idx = -1
        for idx, col in enumerate(controller.active_columns):
            if col.name == "Function Input (Match)":
                match_col_idx = idx
                break
        assert match_col_idx != -1
        
        # Check that the (Match) column text contains "ProjectB_Func"
        # Since it was loaded, the fuzzy matches should have run
        match_item = controller.table.item(0, match_col_idx)
        widget = controller.table.cellWidget(0, match_col_idx)
        if widget and isinstance(widget, QtWidgets.QComboBox):
            match_text = widget.currentText()
        else:
            match_text = match_item.text() if match_item else ""
            
        assert "ProjectB_Func" in match_text
        print("MATCH TEXT:", match_text)
        
        # Clean up DB
        controller.release_manager._db.close()
        
    print("ALL RELEASE SELECTION BUG TESTS PASSED!")

def test_empty_project_excel_import_json_import_edgecase():
    print("Running Empty Project + Excel Import + JSON Import Edgecase Test...")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_edgecase.arch")
        json_cache_path = os.path.join(tmp, "project_b_symbols.json")
        
        # 1. Create Project B JSON symbols
        json_symbols = {
            "elf_path": json_cache_path,
            "elf_hash": "project_b_hash_456",
            "symbols": [
                {
                    "name": "TargetFunc",
                    "address": 3000,
                    "size": 80,
                    "symbol_type": "STT_FUNC",
                    "binding": "STB_GLOBAL",
                    "section": ".text"
                }
            ],
            "functions": [
                {
                    "name": "TargetFunc",
                    "address": 3000,
                    "size": 80,
                    "parameters": [],
                    "return_type": "void"
                }
            ],
            "structures": {},
            "global_vars": {}
        }
        with open(json_cache_path, "w") as f:
            json.dump(json_symbols, f)

        # 2. Setup the empty project DB
        layout = [
            ("TC. ID", "Static Text", True),
            ("Function Input", "Function Search", True),
            ("Function Input (Match)", "Static Text", True)
        ]
        
        # 0 releases initially
        db = make_project_db(db_path, layout=layout, models=[
            {
                "name": "ActiveModel",
                "status": "In Work",
                "rows": [
                    {
                        "TC. ID": {"text": "TC_01"},
                        "Function Input": {"text": "TargetFunc"}
                    }
                ]
            }
        ], settings={})
        db.close()
        
        # Initialize MainWindow & Controller
        window = QMainWindow()
        controller = _make_controller(window, db_path)
        
        # At this point, there is NO release. controller.matcher is None.
        # Let's verify that the match column has a LazyComboBox prefilled with TargetFunc
        match_col_idx = -1
        for idx, col in enumerate(controller.active_columns):
            if col.name == "Function Input (Match)":
                match_col_idx = idx
                break
        assert match_col_idx != -1
        
        widget = controller.table.cellWidget(0, match_col_idx)
        from UI.column_types import LazyComboBox
        assert isinstance(widget, LazyComboBox)
        assert widget.currentText() == "TargetFunc"
        
        # Simulate user clicking/loading dropdown when matcher is None
        # Should not lock loaded=True because matcher is None!
        widget.load_items()
        assert widget._loaded is False
        
        # Simulate changing the search column: TargetFunc -> NewTargetFunc
        # The match column should update to reflect the new search text "NewTargetFunc"
        controller.table.item(0, 1).setText("NewTargetFunc")
        # Ensure it updated the widget
        widget_after_edit = controller.table.cellWidget(0, match_col_idx)
        assert widget_after_edit.currentText() == "NewTargetFunc"
        
        # 3. Simulate "Import JSON" (which calls on_add_release in ReleaseSelectionDialog)
        dialog = ReleaseSelectionDialog(
            release_manager=controller.release_manager,
            architecture_controller=controller,
            parent=None
        )
        
        # Mock run_task to parse and load JSON file successfully
        # Mock file selection return value
        with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName', return_value=(json_cache_path, "JSON")), \
             patch('PyQt6.QtWidgets.QInputDialog.getText', return_value=("Project_B_Release", True)), \
             patch('PyQt6.QtWidgets.QMessageBox.information'), \
             patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warn:
            dialog.on_add_release()
            mock_warn.assert_not_called()
            
        # Verify that:
        # A. The release selection dialog successfully selected and loaded the release
        # B. controller.matcher is now initialized with Project B symbols
        assert controller.parser.md5_hash == "project_b_hash_456"
        assert "TargetFunc" in controller.matcher.all_function_names
        
        # C. The table fuzzy matches have run and updated!
        # Check that the (Match) column text contains "TargetFunc"
        widget_final = controller.table.cellWidget(0, match_col_idx)
        # Note: since the release was loaded and refresh_fuzzy_matches ran, it is now a standard QComboBox with matches
        assert widget_final is not None
        assert "TargetFunc" in widget_final.currentText()
        assert widget_final.count() > 0
        
        # D. Test empty matches case: change search text to "NonExistentFunc" which matches nothing
        controller.table.item(0, 1).setText("NonExistentFunc")
        widget_empty_matches = controller.table.cellWidget(0, match_col_idx)
        # It should still be a QComboBox even though matches is empty!
        assert isinstance(widget_empty_matches, QtWidgets.QComboBox)
        assert widget_empty_matches.currentText() == "NonExistentFunc"
        
        # E. Test switching to a release with no ELF/JSON path
        release_no_elf = controller.release_manager.create_release(
            name="No_Elf_Release",
            copy_from_active=False,
            elf_path=None,
            elf_hash=None
        )
        
        # Select No_Elf_Release in the list widget
        dialog_no_elf = ReleaseSelectionDialog(
            release_manager=controller.release_manager,
            architecture_controller=controller,
            parent=None
        )
        for i in range(dialog_no_elf.list_widget.count()):
            item = dialog_no_elf.list_widget.item(i)
            if "No_Elf_Release" in item.text():
                dialog_no_elf.list_widget.setCurrentRow(i)
                break
        dialog_no_elf.on_load_release()
        
        # Verify parser and matcher are cleared (set to None)
        assert controller.parser is None
        assert controller.matcher is None
        
        controller.release_manager._db.close()
    print("EMPTY PROJECT + EXCEL + JSON EDGECASE TEST PASSED!")

if __name__ == "__main__":
    test_release_selection_dialog_bugs()
    test_empty_project_excel_import_json_import_edgecase()
