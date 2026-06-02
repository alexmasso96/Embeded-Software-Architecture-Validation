"""
Tests for ColumnCustomizer (Logic_Column_Customizer): config round-trip,
add/rename/delete column logic, dependent-column handling, locking
constraints, cyclicity and filter-state accessors. User prompts are mocked.
"""
import os
import sys
from unittest.mock import patch

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from PyQt6 import QtCore
app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic.Logic_Column_Customizer import ColumnCustomizer

LOGIC_OPTIONS = ["Port Search", "Function Search", "Static Text", "Link", "Last Result"]

BASE_CONFIG = [
    ("TC. ID", "Static Text", True, 100),
    ("Port", "Port Search", True, 120),
    ("Port (Match)", "Static Text", True, 80),
    ("Review Status", "Review Status", True, 90),
    ("Port State", "Static Text", True, 70),
]


def _dlg(locked=None):
    return ColumnCustomizer(BASE_CONFIG, LOGIC_OPTIONS, locked_columns=locked or set())


def _row_of(dlg, name):
    for i in range(dlg.active_list.count()):
        if dlg.active_list.item(i).text().split(" | ")[0].strip() == name:
            return i
    return -1


def _names(dlg):
    return [dlg.active_list.item(i).text().split(" | ")[0].strip()
            for i in range(dlg.active_list.count())]


# --------------------------------------------------------------------------
# Accessors / round-trip
# --------------------------------------------------------------------------

def test_get_selected_config_roundtrip():
    dlg = _dlg()
    cfg = dlg.get_selected_config()
    names = [c[0] for c in cfg]
    assert "TC. ID" in names and "Port" in names
    # width preserved
    tc = next(c for c in cfg if c[0] == "TC. ID")
    assert tc[3] == 100
    assert tc[2] is True  # visible


def test_default_cyclicity_default_and_set():
    dlg = _dlg()
    assert dlg.get_default_cyclicity() == "10"
    dlg.cyclicity_input.setText("25")
    assert dlg.get_default_cyclicity() == "25"


def test_filter_states():
    dlg = _dlg()
    dlg.set_filter_states(False, True)
    assert dlg.get_filter_states() == (False, True)
    dlg.set_filter_states(True, False)
    assert dlg.get_filter_states() == (True, False)


def test_unique_name_generation():
    dlg = _dlg()
    # "Port" already exists -> a suffix is appended
    assert dlg._get_unique_name("Port") == "Port (1)"
    assert dlg._get_unique_name("Brand New") == "Brand New"


# --------------------------------------------------------------------------
# Add
# --------------------------------------------------------------------------

def test_add_search_column_creates_dependents():
    dlg = _dlg()
    before = dlg.active_list.count()
    dlg.new_name_input.setText("Speed")
    dlg.type_combo.setCurrentText("Port Search")
    dlg._add_custom_item()
    names = _names(dlg)
    assert "Speed" in names
    assert "Speed (Match)" in names
    assert "Speed (Init)" in names
    assert "Speed (Cyclic)" in names
    assert dlg.active_list.count() == before + 4
    assert dlg.new_name_input.text() == ""  # cleared


def test_add_empty_name_is_noop():
    dlg = _dlg()
    before = dlg.active_list.count()
    dlg.new_name_input.setText("   ")
    dlg._add_custom_item()
    assert dlg.active_list.count() == before


def test_add_duplicate_link_warns():
    dlg = _dlg()
    dlg.new_name_input.setText("Link1")
    dlg.type_combo.setCurrentText("Link")
    dlg._add_custom_item()
    before = dlg.active_list.count()
    dlg.new_name_input.setText("Link2")
    dlg.type_combo.setCurrentText("Link")
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        dlg._add_custom_item()
    mock_warn.assert_called_once()
    assert dlg.active_list.count() == before  # second link rejected


# --------------------------------------------------------------------------
# Rename
# --------------------------------------------------------------------------

def test_rename_search_column_renames_dependents():
    dlg = _dlg()
    dlg.active_list.setCurrentRow(_row_of(dlg, "Port"))
    with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Throttle", True)):
        dlg._rename_selected_item()
    names = _names(dlg)
    assert "Throttle" in names
    assert "Throttle (Match)" in names
    assert "Port" not in names


def test_rename_dependent_column_blocked():
    dlg = _dlg()
    dlg.active_list.setCurrentRow(_row_of(dlg, "Port (Match)"))
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn, \
         patch("PyQt6.QtWidgets.QInputDialog.getText") as mock_input:
        dlg._rename_selected_item()
    mock_warn.assert_called_once()
    mock_input.assert_not_called()


def test_rename_port_state_blocked():
    dlg = _dlg()
    dlg.active_list.setCurrentRow(_row_of(dlg, "Port State"))
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        dlg._rename_selected_item()
    mock_warn.assert_called_once()


def test_rename_locked_column_blocked():
    dlg = _dlg(locked={"TC. ID"})
    dlg.active_list.setCurrentRow(_row_of(dlg, "TC. ID"))
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        dlg._rename_selected_item()
    mock_warn.assert_called_once()


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------

def test_delete_search_column_removes_dependents():
    dlg = _dlg()
    dlg.active_list.setCurrentRow(_row_of(dlg, "Port"))
    dlg._delete_selected_item()
    names = _names(dlg)
    assert "Port" not in names
    assert "Port (Match)" not in names


def test_delete_dependent_blocked():
    dlg = _dlg()
    dlg.active_list.setCurrentRow(_row_of(dlg, "Port (Match)"))
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        dlg._delete_selected_item()
    mock_warn.assert_called_once()
    assert "Port (Match)" in _names(dlg)


def test_delete_locked_blocked():
    dlg = _dlg(locked={"TC. ID"})
    dlg.active_list.setCurrentRow(_row_of(dlg, "TC. ID"))
    with patch("PyQt6.QtWidgets.QMessageBox.warning") as mock_warn:
        dlg._delete_selected_item()
    mock_warn.assert_called_once()
    assert "TC. ID" in _names(dlg)


def test_delete_review_status_also_removes_port_state():
    dlg = _dlg()
    dlg.active_list.setCurrentRow(_row_of(dlg, "Review Status"))
    dlg._delete_selected_item()
    names = _names(dlg)
    assert "Review Status" not in names
    assert "Port State" not in names


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
