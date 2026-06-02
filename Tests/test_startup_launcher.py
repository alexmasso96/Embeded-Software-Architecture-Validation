"""
Tests for StartupLauncherDialog (Dialog_Startup_Launcher): the three entry-point
buttons, with file dialogs and lock acquisition mocked out.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from PyQt6 import QtCore
app = QApplication.instance() or QApplication(sys.argv)

from UI.Dialog_Startup_Launcher import StartupLauncherDialog


def _dlg():
    # QDialog needs a real (or no) parent; inject the mock main_window after.
    dlg = StartupLauncherDialog(parent=None)
    mw = MagicMock()
    dlg.main_window = mw
    return dlg, mw


def test_dialog_constructs_with_buttons():
    dlg, _ = _dlg()
    assert dlg.btn_new is not None
    assert dlg.btn_view_only is not None
    assert dlg.btn_edit is not None


def test_handle_new_project_accepts_and_defers():
    dlg, mw = _dlg()
    with patch.object(QtCore.QTimer, "singleShot") as mock_single:
        dlg.handle_new_project()
    assert dlg.result() == dlg.DialogCode.Accepted.value
    mock_single.assert_called_once()


def test_handle_view_only_with_file():
    dlg, mw = _dlg()
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
               return_value=("/tmp/proj.arch", "")), \
         patch.object(QtCore.QTimer, "singleShot") as mock_single:
        dlg.handle_view_only()
    assert dlg.result() == dlg.DialogCode.Accepted.value
    mock_single.assert_called_once()


def test_handle_view_only_cancelled():
    dlg, mw = _dlg()
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")):
        dlg.handle_view_only()
    # No file chosen -> dialog not accepted
    assert dlg.result() != dlg.DialogCode.Accepted.value


def test_handle_exclusive_edit_lock_success():
    dlg, mw = _dlg()
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
               return_value=("/tmp/proj.arch", "")), \
         patch("Application_Logic.Logic_File_Locking.FileLockManager.acquire_lock",
               return_value=(True, "ok")), \
         patch.object(QtCore.QTimer, "singleShot") as mock_single:
        dlg.handle_exclusive_edit()
    assert dlg.result() == dlg.DialogCode.Accepted.value
    mock_single.assert_called_once()


def test_handle_exclusive_edit_lock_denied():
    dlg, mw = _dlg()
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
               return_value=("/tmp/proj.arch", "")), \
         patch("Application_Logic.Logic_File_Locking.FileLockManager.acquire_lock",
               return_value=(False, "locked by bob")), \
         patch("PyQt6.QtWidgets.QMessageBox.critical") as mock_crit:
        dlg.handle_exclusive_edit()
    mock_crit.assert_called_once()
    assert dlg.result() != dlg.DialogCode.Accepted.value


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
