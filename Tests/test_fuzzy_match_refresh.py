"""
Regression tests for ArchitectureTabController.refresh_fuzzy_matches.

The "active" (eager) fuzzy-match branch should populate the adjacent (Match)
column with real fuzzy results immediately — this is the path used on import
and when a different ELF is loaded, instead of the lazy placeholder that only
mirrors the search text.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow, QComboBox, QTableWidgetItem
app = QApplication.instance() or QApplication(sys.argv)

import UI
from UI.architecture_table import ArchitectureTabController
from UI.column_types import (
    FunctionSearchColumn, PortSearchColumn, VariableSearchColumn,
)


class FakeMatcher:
    """Deterministic stand-in for SymbolMatcher."""
    search_pool = ["dummy"]

    def find_top_matches(self, text, limit=10):
        return [(f"Port_{text}", 95), (f"PortAlt_{text}", 70)]

    def find_top_function_matches(self, text, limit=10):
        return [(f"Func_{text}", 90), (f"FuncAlt_{text}", 65)]

    def find_top_variable_matches(self, text, limit=10):
        return [(f"Var_{text}", 88)]


def _make_controller():
    window = QMainWindow()
    window.ui = UI.Ui_MainWindow()
    window.ui.setupUi(window)
    window.current_project_file = None
    window.edit_mode = True
    controller = ArchitectureTabController(window)
    controller._rebuild_column_objects()
    controller._setup_table_style()
    return controller


def _set_cell_text(controller, row, col, text):
    item = controller.table.item(row, col)
    if not item:
        item = QTableWidgetItem()
        controller.table.setItem(row, col, item)
    item.setText(text)


def test_refresh_populates_match_column_eagerly():
    controller = _make_controller()
    func_idx = next(i for i, c in enumerate(controller.active_columns)
                    if isinstance(c, FunctionSearchColumn))

    if controller.table.rowCount() == 0:
        controller.table.insertRow(0)

    controller.table.blockSignals(True)
    _set_cell_text(controller, 0, func_idx, "ReadTemp")
    controller.table.blockSignals(False)

    controller.matcher = FakeMatcher()
    controller.refresh_fuzzy_matches(show_progress=False)

    match_widget = controller.table.cellWidget(0, func_idx + 1)
    assert isinstance(match_widget, QComboBox)
    assert match_widget.count() == 2
    # Best match is shown first, carrying the score suffix.
    assert match_widget.itemText(0) == "Func_ReadTemp (90%)"


def test_refresh_handles_all_search_column_types():
    controller = _make_controller()
    if controller.table.rowCount() == 0:
        controller.table.insertRow(0)

    type_to_prefix = {
        PortSearchColumn: "Port_",
        FunctionSearchColumn: "Func_",
        VariableSearchColumn: "Var_",
    }
    indices = {}
    controller.table.blockSignals(True)
    for i, col in enumerate(controller.active_columns):
        for cls in type_to_prefix:
            if isinstance(col, cls):
                _set_cell_text(controller, 0, i, "Signal")
                indices[cls] = i
    controller.table.blockSignals(False)

    controller.matcher = FakeMatcher()
    controller.refresh_fuzzy_matches(show_progress=False)

    for cls, idx in indices.items():
        widget = controller.table.cellWidget(0, idx + 1)
        assert isinstance(widget, QComboBox), f"{cls.__name__} produced no combo"
        assert widget.itemText(0).startswith(type_to_prefix[cls])


def test_refresh_is_noop_without_matcher():
    controller = _make_controller()
    func_idx = next(i for i, c in enumerate(controller.active_columns)
                    if isinstance(c, FunctionSearchColumn))
    if controller.table.rowCount() == 0:
        controller.table.insertRow(0)
    controller.table.blockSignals(True)
    _set_cell_text(controller, 0, func_idx, "ReadTemp")
    controller.table.blockSignals(False)

    controller.matcher = None
    # Should return quietly and not raise.
    controller.refresh_fuzzy_matches(show_progress=False)

    widget = controller.table.cellWidget(0, func_idx + 1)
    assert not isinstance(widget, QComboBox)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
