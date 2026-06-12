"""
Tests for ArchitectureManagerDialog (Dialog_Architecture_Manager) and its
sub-dialogs (Dialog_Architecture_Edit, Dialog_Restore_Model), driving the
new/edit/duplicate/delete/restore actions with user interaction mocked.
Also exercises ArchitectureListModel.
"""
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QMessageBox
app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Tests.test_helpers import make_project_db
from UI.Dialog_Architecture_Manager import ArchitectureManagerDialog
from UI.Dialog_Architecture_Edit import ArchitectureEditDialog
from UI.Dialog_Restore_Model import RestoreModelDialog
from UI.StyledMessageBox import StyledMessageBox

MOD = "UI.Dialog_Architecture_Manager"


def _manager(tmp):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("PortSearchColumn", "Port", True)],
        models=[
            {"name": "Model_A", "status": "In Work", "rows": []},
            {"name": "Model_B", "status": "Released", "rows": []},
        ],
    )
    mgr = ArchitectureManager()
    mgr.set_db(db)
    return mgr, db


def _select_row(dlg, row):
    dlg.list_view.setCurrentIndex(dlg.model.index(row, 0))


# --------------------------------------------------------------------------
# Sub-dialogs (direct)
# --------------------------------------------------------------------------

def test_edit_dialog_get_data():
    dlg = ArchitectureEditDialog(name="Foo", status="Released")
    assert dlg.get_data() == ("Foo", "Released")
    dlg.txt_name.setText("Bar")
    dlg.cmb_status.setCurrentText("Retired")
    assert dlg.get_data() == ("Bar", "Retired")


def test_restore_dialog_selection():
    m1 = MagicMock(); m1.name = "Del1"; m1.status = "In Work"
    dlg = RestoreModelDialog([m1])
    dlg.list_widget.setCurrentRow(0)
    dlg.on_restore()
    assert dlg.get_selected_index() == 0
    assert dlg.result() == dlg.DialogCode.Accepted.value


def test_restore_dialog_no_selection_warns():
    m1 = MagicMock(); m1.name = "Del1"; m1.status = "In Work"
    dlg = RestoreModelDialog([m1])
    with patch("UI.Dialog_Restore_Model.QMessageBox.warning") as mock_warn:
        dlg.on_restore()
    mock_warn.assert_called_once()
    assert dlg.get_selected_index() == -1


# --------------------------------------------------------------------------
# Manager dialog list model
# --------------------------------------------------------------------------

def test_list_model_rowcount():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        assert dlg.model.rowCount() == 2
        db.close()


# --------------------------------------------------------------------------
# Manager dialog actions
# --------------------------------------------------------------------------

def test_on_new_creates_model():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        before = len(mgr.models)

        fake = MagicMock()
        fake.exec.return_value = True
        fake.get_data.return_value = ("Model_C", "In Work")
        with patch(f"{MOD}.ArchitectureEditDialog", return_value=fake):
            dlg.on_new()
        assert len(mgr.models) == before + 1
        assert any(m.name == "Model_C" for m in mgr.models)
        db.close()


def test_on_new_cancelled_creates_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        before = len(mgr.models)
        fake = MagicMock()
        fake.exec.return_value = False
        with patch(f"{MOD}.ArchitectureEditDialog", return_value=fake):
            dlg.on_new()
        assert len(mgr.models) == before
        db.close()


def test_on_edit_renames_model():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        _select_row(dlg, 0)

        fake = MagicMock()
        fake.exec.return_value = True
        fake.get_data.return_value = ("Renamed_A", "Retired")
        with patch(f"{MOD}.ArchitectureEditDialog", return_value=fake):
            dlg.on_edit_click()
        assert mgr.models[0].name == "Renamed_A"
        assert mgr.models[0].status == "Retired"
        db.close()


def test_on_edit_invalid_index_noop():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        # No selection -> invalid index -> early return (no dialog constructed)
        with patch(f"{MOD}.ArchitectureEditDialog") as MockEdit:
            dlg.on_edit_click()
        MockEdit.assert_not_called()
        db.close()


def test_on_duplicate_adds_copy():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        _select_row(dlg, 0)
        before = len(mgr.models)
        dlg.on_duplicate()
        assert len(mgr.models) == before + 1
        assert any("Copy" in m.name for m in mgr.models)
        db.close()


def test_on_delete_soft_deletes_with_confirmation():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        _select_row(dlg, 0)
        with patch.object(StyledMessageBox, "warning",
                          return_value=QMessageBox.StandardButton.Yes):
            dlg.on_delete()
        assert mgr.models[0].is_deleted is True
        db.close()


def test_on_delete_cancelled_keeps_model():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        _select_row(dlg, 0)
        with patch.object(QMessageBox, "exec",
                          return_value=QMessageBox.StandardButton.No):
            dlg.on_delete()
        assert mgr.models[0].is_deleted is False
        db.close()


def test_on_restore_brings_back_model():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        # Soft-delete model 1 first
        mgr.soft_delete_model(1)
        assert mgr.models[1].is_deleted is True

        dlg = ArchitectureManagerDialog(mgr)
        fake = MagicMock()
        fake.exec.return_value = True
        fake.get_selected_index.return_value = 0  # first (only) deleted model
        with patch(f"{MOD}.RestoreModelDialog", return_value=fake):
            dlg.on_restore()
        assert mgr.models[1].is_deleted is False
        db.close()


def test_on_restore_no_deleted_shows_info():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _manager(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        with patch("PyQt6.QtWidgets.QMessageBox.information") as mock_info:
            dlg.on_restore()
        mock_info.assert_called_once()
        db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
