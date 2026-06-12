"""
Direct test for ArchitectureTabController._cell_of_widget.

Regression guard for the stale-row bug: combobox change-handlers used to bind the
row index captured when the widget was created, so inserting/removing rows above a
combobox made edits dirty-mark and log the wrong row. _cell_of_widget resolves the
widget's CURRENT cell instead, so it must track the widget as rows shift.
"""
import sys
import os
import types

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QTableWidget, QComboBox

app = QApplication.instance() or QApplication(sys.argv)

from UI.architecture_table import ArchitectureTabController


def _bind_cell_of_widget(table):
    obj = types.SimpleNamespace(table=table)
    obj._cell_of_widget = types.MethodType(
        ArchitectureTabController._cell_of_widget, obj
    )
    return obj


def test_cell_of_widget_tracks_row_shift():
    table = QTableWidget(3, 2)
    combo = QComboBox()
    table.setCellWidget(1, 0, combo)
    ctl = _bind_cell_of_widget(table)

    # Initially at row 1.
    assert ctl._cell_of_widget(combo) == (1, 0)

    # Insert a row at the top: the combo is now physically at row 2. The old
    # captured-index approach would still say row 1 — live resolution says 2.
    table.insertRow(0)
    assert ctl._cell_of_widget(combo) == (2, 0)

    # Remove a row above it again: back to row 1.
    table.removeRow(0)
    assert ctl._cell_of_widget(combo) == (1, 0)


def test_cell_of_widget_absent_returns_sentinel():
    table = QTableWidget(2, 2)
    orphan = QComboBox()  # never placed in the table
    ctl = _bind_cell_of_widget(table)
    assert ctl._cell_of_widget(orphan) == (-1, -1)
