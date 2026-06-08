import sys
import os
import tempfile
import json
import datetime
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt6 import QtWidgets

# Setup path
sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
from UI.Dialog_Release_Selection import ReleaseSelectionDialog
from Tests.test_helpers import make_project_db

app = QApplication.instance() or QApplication(sys.argv)

def _make_controller(window, db_path):
    import UI
    window.ui = UI.Ui_MainWindow()
    window.ui.setupUi(window)
    window.current_project_file = db_path
    window.edit_mode = True
    
    db = ProjectDatabase()
    db.open(db_path)
    window.project_db = db
    
    # Instantiate history manager for testing
    from Application_Logic.Logic_History import HistoryManager
    window.history_manager = HistoryManager(db)
    
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

def test_linear_auto_baselining():
    """Verify that adding Release B automatically baselines the previous active Release A."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_auto_baseline.arch")
        make_project_db(db_path)
        
        db = ProjectDatabase()
        db.open(db_path)
        
        manager = ReleaseManager(db_path)
        manager.set_db(db)
        
        # 1. Create Release A
        r_a = manager.create_release("Release_A", copy_from_active=False)
        assert r_a.is_baseline is False
        assert manager.active_release_index == 0
        
        # 2. Create Release B and baseline A
        r_b = manager.create_release("Release_B", copy_from_active=True, baseline_previous=True)
        assert r_b.is_baseline is False
        
        # Verify in memory
        assert r_a.is_baseline is True
        
        # Verify in DB
        db.close()
        db2 = ProjectDatabase()
        db2.open(db_path)
        releases = db2.get_all_releases()
        rel_a_db = next(r for r in releases if r["name"] == "Release_A")
        rel_b_db = next(r for r in releases if r["name"] == "Release_B")
        
        assert rel_a_db["is_baseline"] == 1
        assert rel_b_db["is_baseline"] == 0
        db2.close()

def test_history_snapshotting_and_isolation():
    """Verify that history logs are snapshot to new releases and changes to baselines do not bleed."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_history_isolation.arch")
        make_project_db(db_path)
        
        db = ProjectDatabase()
        db.open(db_path)
        
        # Enable history tracking
        window = QMainWindow()
        controller = _make_controller(window, db_path)
        manager = controller.release_manager
        
        # 1. Create Release A and set active
        r_a = manager.create_release("Release_A")
        db.set_active_release(r_a.id)
        
        # Add a history entry to Release A
        window.history_manager.add_entry("Initial architecture definition in Release A")
        assert len(db.get_history(r_a.id)) == 1
        assert db.get_history(r_a.id)[0]["description"] == "Initial architecture definition in Release A"
        
        # 2. Create Release B (cloned from active A)
        r_b = manager.create_release("Release_B", copy_from_active=True, baseline_previous=True)
        
        # Verify B snapshot contains A's history
        history_b = db.get_history(r_b.id)
        assert len(history_b) == 1
        assert history_b[0]["description"] == "Initial architecture definition in Release A"
        
        # Set B active and log change
        db.set_active_release(r_b.id)
        window.history_manager.load_history()
        window.history_manager.add_entry("Added new port in Release B")
        
        # Verify A's history is NOT modified
        assert len(db.get_history(r_a.id)) == 1
        # Verify B has both entries
        assert len(db.get_history(r_b.id)) == 2
        assert db.get_history(r_b.id)[1]["description"] == "Added new port in Release B"
        
        # 3. Simulate unfreezing A (baseline) and editing
        db.set_active_release(r_a.id)
        window.history_manager.load_history()
        window.history_manager.add_entry("Late correction in Release A")
        
        # Verify A's history has the edit
        assert len(db.get_history(r_a.id)) == 2
        assert db.get_history(r_a.id)[1]["description"] == "Late correction in Release A"
        
        # Verify B's history is untouched by A's late edit
        assert len(db.get_history(r_b.id)) == 2
        
        db.close()

@patch('UI.Dialog_Release_Selection.QMessageBox.question')
@patch('UI.Dialog_Release_Selection.QMessageBox.information')
@patch('UI.Dialog_Release_Selection.QMessageBox.critical')
@patch('UI.Dialog_Release_Selection.QInputDialog.getText')
def test_dialog_lock_unlock_actions(mock_get_text, mock_critical, mock_info, mock_question):
    """Verify password prompting, dynamic toggle state, and Main Window triggers update."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_dialog.arch")
        make_project_db(db_path)
        
        # Set master password in metadata
        db = ProjectDatabase()
        db.open(db_path)
        from Application_Logic.Logic_Security import SecurityManager
        db.set_meta("master_password_hash", SecurityManager.hash_password("master123"))
        db.close()
        
        window = QMainWindow()
        controller = _make_controller(window, db_path)
        controller.master_password_hash = SecurityManager.hash_password("master123")
        
        # Add Release A (active) and Release B (baseline)
        r_a = controller.release_manager.create_release("Release_A")
        r_b = controller.release_manager.create_baseline(0, "Baseline_B", active_model_data={"rows": []})
        
        dialog = ReleaseSelectionDialog(controller.release_manager, controller)
        
        # Select Baseline_B
        idx = dialog.active_releases.index(r_b)
        dialog.list_widget.setCurrentRow(idx)
        dialog.update_buttons()
        
        # Button should show unlock text
        assert dialog.btn_toggle_lock.text() == "🔓 Unfreeze Baseline"
        
        # Click Unlock -> mock wrong password
        with patch('Application_Logic.Logic_Security.MasterPasswordPromptDialog.exec', return_value=True), \
             patch('Application_Logic.Logic_Security.MasterPasswordPromptDialog.get_password', return_value="wrong"):
            dialog.on_toggle_lock()
            mock_critical.assert_called_with(dialog, "Access Denied", "Incorrect master password.")
            assert r_b.is_baseline is True
            
        # Click Unlock -> mock correct password
        with patch('Application_Logic.Logic_Security.MasterPasswordPromptDialog.exec', return_value=True), \
             patch('Application_Logic.Logic_Security.MasterPasswordPromptDialog.get_password', return_value="master123"):
            dialog.on_toggle_lock()
            mock_info.assert_called_with(dialog, "Success", "Baseline 'Baseline_B' has been unfrozen. You can now edit its table data.")
            assert r_b.is_baseline is False
            
        # Dynamic button updates to Lock
        dialog.update_buttons()
        assert dialog.btn_toggle_lock.text() == "🔒 Freeze Release"
        
        # Lock back
        dialog.on_toggle_lock()
        assert r_b.is_baseline is True
