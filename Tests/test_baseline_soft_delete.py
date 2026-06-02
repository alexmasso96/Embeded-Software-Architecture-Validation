import sys
import os
import tempfile
from unittest.mock import MagicMock, patch

# Setup path
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox
from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Database import ProjectDatabase
from UI.Dialog_Release_Selection import ReleaseSelectionDialog, AllBaselinesDialog

# Initialize QApplication for widget tests
app = QApplication.instance() or QApplication(sys.argv)


def _make_mgr(db_path: str):
    db = ProjectDatabase()
    db.open(db_path)
    mgr = ReleaseManager()
    mgr.set_db(db)
    return db, mgr


def test_baseline_soft_delete():
    print("=" * 70)
    print("STARTING BASELINE SOFT DELETE UNIT TESTS")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_soft_delete.arch")
        db, mgr = _make_mgr(db_path)

        try:
            # 1. Create normal release
            rel = mgr.create_release("Release_1.0", "Active Release", copy_from_active=False)
            assert len(mgr.releases) == 1
            assert mgr.releases[0].name == "Release_1.0"
            print("Test 1: Release created.")

            # 2. Create baseline
            sample_data = {"rows": [{"TC. ID": {"text": "TC_001"}}]}
            baseline = mgr.create_baseline(0, "Baseline_A", active_model_data=sample_data)
            assert len(mgr.releases) == 2
            assert mgr.releases[1].name == "Baseline_A"
            assert not mgr.releases[1].is_deleted
            print("Test 2: Baseline created in DB.")

            # 3. Soft-delete the baseline with a comment
            baseline_idx = mgr.releases.index(baseline)
            success, msg = mgr.delete_release(baseline_idx, deletion_comment="Outdated baseline comment")
            assert success is True
            assert mgr.releases[baseline_idx].is_deleted is True
            assert mgr.releases[baseline_idx].deletion_comment == "Outdated baseline comment"
            print("Test 3: Baseline soft-deleted.")

            # 4. Verify persistence of soft-delete fields — reload fresh manager
            db.close()
            db2 = ProjectDatabase()
            db2.open(db_path)
            mgr2 = ReleaseManager()
            mgr2.set_db(db2)
            loaded_baseline = next(r for r in mgr2.releases if r.name == "Baseline_A")
            assert loaded_baseline.is_deleted is True
            assert loaded_baseline.deletion_comment == "Outdated baseline comment"
            print("Test 4: Registry serialization and loading of soft-deleted baseline passed.")

            # 5. Reuse soft-deleted baseline name — should succeed
            new_baseline = mgr2.create_baseline(0, "Baseline_A", active_model_data=sample_data)
            assert len(mgr2.releases) == 3
            assert mgr2.releases[2].name == "Baseline_A"
            assert not mgr2.releases[2].is_deleted
            print("Test 5: Reuse name for soft-deleted baseline passed.")

            # 6. GUI Filter & Dialog listings test
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
            print("Test 6: ReleaseSelectionDialog hides soft-deleted baselines.")

            # Test baseline deletion comment prompt in ReleaseSelectionDialog
            # Select active Baseline_A in the list (row index 1 in dlg.active_releases)
            dlg.list_widget.setCurrentRow(1)

            with patch.object(QInputDialog, 'getMultiLineText',
                               return_value=("Delete because obsolete", True)) as mock_prompt:
                dlg.on_delete()
                assert mock_prompt.called is True
                assert mgr2.releases[2].is_deleted is True
                assert mgr2.releases[2].deletion_comment == "Delete because obsolete"

            print("Test 7: ReleaseSelectionDialog delete prompt and soft-delete passed.")

            # 7. AllBaselinesDialog shows ALL baselines regardless of deletion state
            all_baselines_dlg = AllBaselinesDialog(mgr2, mock_controller)
            assert len(all_baselines_dlg.baselines) == 2
            assert all_baselines_dlg.baselines[0].is_deleted is True
            assert all_baselines_dlg.baselines[1].is_deleted is True

            item_0 = all_baselines_dlg.list_widget.item(0)
            assert item_0.text() == "Baseline_A [DELETED]"
            assert item_0.font().italic() is True

            # Try loading a soft-deleted baseline
            all_baselines_dlg.list_widget.setCurrentRow(0)

            with patch.object(QMessageBox, 'information') as mock_info:
                all_baselines_dlg.on_load_baseline()
                assert mock_info.called is True
                args, kwargs = mock_info.call_args
                assert "Outdated baseline comment" in args[2]
                mock_controller.load_baseline_by_model.assert_called_with(mgr2.releases[1])

            print("Test 8: AllBaselinesDialog loads deleted baseline and shows popup comment dialog.")

            print("\nALL BASELINE SOFT-DELETE TESTS PASSED SUCCESSFULLY!")

        finally:
            try:
                db2.close()
            except Exception:
                pass


if __name__ == "__main__":
    test_baseline_soft_delete()
    os._exit(0)
