import sys
import os
import shutil
import json
import datetime
from unittest.mock import MagicMock, patch

# Setup path
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox
from Application_Logic.Logic_Release_Manager import ReleaseManager, ReleaseModel
from UI.Dialog_Release_Selection import ReleaseSelectionDialog, AllBaselinesDialog

# Initialize QApplication for widget tests
app = QApplication.instance() or QApplication(sys.argv)

def test_baseline_soft_delete():
    print("=" * 70)
    print("STARTING BASELINE SOFT DELETE UNIT TESTS")
    print("=" * 70)
    
    test_dir = "test_soft_delete_proj.arch"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    try:
        # 1. Initialize ReleaseManager
        mgr = ReleaseManager(test_dir)
        
        # 2. Create normal release
        rel = mgr.create_release("Release_1.0", "Active Release", copy_from_active=False)
        assert len(mgr.releases) == 1
        assert mgr.releases[0].name == "Release_1.0"
        print("Test 1: Release created.")
        
        # 3. Create baseline
        sample_data = {
            "rows": [
                {"TC. ID": {"text": "TC_001"}}
            ]
        }
        baseline = mgr.create_baseline(0, "Baseline_A", active_model_data=sample_data)
        assert len(mgr.releases) == 2
        assert mgr.releases[1].name == "Baseline_A"
        assert not mgr.releases[1].is_deleted
        
        baseline_dir = os.path.join(test_dir, "Baselines", "Baseline_A")
        assert os.path.exists(baseline_dir)
        print("Test 2: Baseline created with directory.")
        
        # 4. Soft-delete the baseline with a comment
        baseline_idx = mgr.releases.index(baseline)
        success, msg = mgr.delete_release(baseline_idx, deletion_comment="Outdated baseline comment")
        assert success is True
        assert mgr.releases[baseline_idx].is_deleted is True
        assert mgr.releases[baseline_idx].deletion_comment == "Outdated baseline comment"
        
        # Folder MUST remain on disk to ensure immutability
        assert os.path.exists(baseline_dir)
        print("Test 3: Baseline soft-deleted and folder preserved.")
        
        # 5. Verify persistence of soft-delete fields
        mgr.save_registry()
        mgr2 = ReleaseManager(test_dir)
        loaded_baseline = next(r for r in mgr2.releases if r.name == "Baseline_A")
        assert loaded_baseline.is_deleted is True
        assert loaded_baseline.deletion_comment == "Outdated baseline comment"
        print("Test 4: Registry serialization and loading of soft-deleted baseline passed.")
        
        # 6. Verify duplicate baseline name creation (reusing soft-deleted baseline name)
        # Should succeed because the existing one is soft-deleted
        new_baseline = mgr2.create_baseline(0, "Baseline_A", active_model_data=sample_data)
        assert len(mgr2.releases) == 3
        assert mgr2.releases[2].name == "Baseline_A"
        assert not mgr2.releases[2].is_deleted
        
        # Directory conflict resolution check: new baseline must reside in Baseline_A_1
        new_baseline_dir = os.path.join(test_dir, "Baselines", "Baseline_A_1")
        assert os.path.exists(new_baseline_dir)
        # Verify the original soft-deleted directory was NOT overwritten or modified
        assert os.path.exists(baseline_dir)
        
        print("Test 5: Reuse name for soft-deleted baseline and path collision resolution passed.")
        
        # 7. GUI Filter & Dialog listings test
        mock_controller = MagicMock()
        mock_controller.parser = MagicMock()
        mock_controller.parser.elf_path = None
        
        # ReleaseSelectionDialog must hide soft-deleted baselines from standard list
        dlg = ReleaseSelectionDialog(mgr2, mock_controller)
        # active_releases should only contain Release_1.0 and the new active Baseline_A (total 2)
        assert len(dlg.active_releases) == 2
        active_names = [r.name for r in dlg.active_releases]
        assert "Release_1.0" in active_names
        assert "Baseline_A" in active_names
        # The soft-deleted Baseline_A (at index 1 in mgr2.releases) should not be there
        assert dlg.active_releases[1].is_deleted is False # The loaded index 1 active release is actually the new Baseline_A in the active mapping
        
        print("Test 6: ReleaseSelectionDialog hides soft-deleted baselines.")
        
        # Test baseline deletion comment prompt in ReleaseSelectionDialog
        # Select active Baseline_A in the list (row index 1 in dlg.active_releases)
        dlg.list_widget.setCurrentRow(1)
        
        with patch.object(QInputDialog, 'getMultiLineText', return_value=("Delete because obsolete", True)) as mock_prompt:
            dlg.on_delete()
            assert mock_prompt.called is True
            # Verify the second baseline (index 2 in mgr2.releases) has now been soft-deleted too
            assert mgr2.releases[2].is_deleted is True
            assert mgr2.releases[2].deletion_comment == "Delete because obsolete"
            
        print("Test 7: ReleaseSelectionDialog delete prompt and soft-delete passed.")
        
        # 8. Options Menu AllBaselinesDialog tests
        # Re-initialize to have a clear state with:
        # mgr2.releases[0]: Release_1.0 (active release)
        # mgr2.releases[1]: Baseline_A (soft-deleted with 'Outdated baseline comment')
        # mgr2.releases[2]: Baseline_A (soft-deleted with 'Delete because obsolete')
        
        all_baselines_dlg = AllBaselinesDialog(mgr2, mock_controller)
        # Should display ALL baselines regardless of deletion state (total 2)
        assert len(all_baselines_dlg.baselines) == 2
        assert all_baselines_dlg.baselines[0].is_deleted is True
        assert all_baselines_dlg.baselines[1].is_deleted is True
        
        # Test item rendering status in the list widget
        item_0 = all_baselines_dlg.list_widget.item(0)
        assert item_0.text() == "Baseline_A [DELETED]"
        assert item_0.font().italic() is True
        
        # Try loading a soft-deleted baseline
        # Select the first soft-deleted baseline
        all_baselines_dlg.list_widget.setCurrentRow(0)
        
        with patch.object(QMessageBox, 'information') as mock_info:
            all_baselines_dlg.on_load_baseline()
            # Must show information popup with deletion comment
            assert mock_info.called is True
            args, kwargs = mock_info.call_args
            assert "Outdated baseline comment" in args[2]
            
            # Controller must be asked to load it
            mock_controller.load_baseline_by_model.assert_called_with(mgr2.releases[1])
            
        print("Test 8: AllBaselinesDialog loads deleted baseline and shows popup comment dialog.")
        
        print("\nALL BASELINE SOFT-DELETE TESTS PASSED SUCCESSFULLY!")
        
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_baseline_soft_delete()
