"""
Regression tests for two interface bugs found while fixing lazy-loading:

A. ELF force-reload from the Release Selection window wiped every column,
   leaving only the row-number gutter.  Cause: a Software Release data dict
   carries no "config" key, and load_project_data rebuilt the schema from that
   empty config.  Fix: load_project_data must keep the current columns when no
   config is supplied.

B. The (Match) column was not populated on Excel import for any model other
   than the active one.  Cause: refresh_fuzzy_matches ran once against the
   active model, but imports distribute rows across several models and newly
   created models are not active.  Fix: _eager_match_imported_models matches
   and persists every model that received rows.
"""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from PyQt6.QtWidgets import QApplication, QMainWindow
app = QApplication.instance() or QApplication(sys.argv)

import UI
import openpyxl
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Column_Types import PortSearchColumn
from Tests.test_helpers import make_project_db


class FakeMatcher:
    """Deterministic stand-in for SymbolMatcher — best match is 'Port_<text>'."""
    search_pool = ["dummy"]

    def find_top_matches(self, text, limit=10):
        return [(f"Port_{text}", 95), (f"Alt_{text}", 70)]

    def find_top_function_matches(self, text, limit=10):
        return [(f"Func_{text}", 90)]

    def find_top_variable_matches(self, text, limit=10):
        return [(f"Var_{text}", 88)]


def _make_controller(window=None):
    if window is None:
        window = QMainWindow()
        window.ui = UI.Ui_MainWindow()
        window.ui.setupUi(window)
        window.current_project_file = None
        window.edit_mode = True
    controller = ArchitectureTabController(window)
    controller._rebuild_column_objects()
    controller._setup_table_style()
    return controller


# ---------------------------------------------------------------------------
# Bug A — config-less data must not wipe columns
# ---------------------------------------------------------------------------

def test_release_load_preserves_columns():
    """load_project_data with a Release-style dict (no 'config') keeps schema."""
    controller = _make_controller()
    cols_before = [c.name for c in controller.active_columns]
    assert len(cols_before) > 1  # sanity: real schema present

    port_idx = next(i for i, c in enumerate(controller.active_columns)
                    if isinstance(c, PortSearchColumn))
    port_name = controller.active_columns[port_idx].name

    # A Software Release supplies only rows (and results/metadata) — no config.
    release_data = {
        "rows": [
            {port_name: {"text": "throttle_pos"}},
            {port_name: {"text": "brake_pressure"}},
        ]
    }
    controller.load_project_data(release_data)

    cols_after = [c.name for c in controller.active_columns]
    assert cols_after == cols_before, "columns must be preserved on config-less load"
    # Rows were still applied into the preserved schema.
    assert controller.table.rowCount() == 2
    assert controller.table.item(0, port_idx).text() == "throttle_pos"


def test_real_config_still_rebuilds():
    """A genuine config change must still rebuild the schema."""
    controller = _make_controller()
    new_config = [
        ("TC. ID", "Static Text", True),
        ("Only Port", "Port Search", True),
        ("Only Port (Match)", "Static Text", True),
    ]
    controller.load_project_data({"config": new_config, "rows": []})
    assert [c.name for c in controller.active_columns] == [
        "TC. ID", "Only Port", "Only Port (Match)"
    ]


# ---------------------------------------------------------------------------
# Bug B — every imported model gets eager (Match) results, not just the active
# ---------------------------------------------------------------------------

def _assert_all_ports_matched(model, port_name, match_name):
    """Every row with a non-empty port input must carry its eager best-match
    in the (Match) column — never the raw search text (the lazy placeholder)."""
    rows = (model.data_cache or {}).get("rows", [])
    checked = 0
    for r in rows:
        port_text = r.get(port_name, {}).get("text", "").strip()
        if not port_text:
            continue  # init placeholder / blank row
        match_text = r.get(match_name, {}).get("widget_text", "")
        assert match_text == f"Port_{port_text} (95%)", (
            f"{model.name}: port {port_text!r} -> match {match_text!r} "
            f"(expected eager best match, not lazy placeholder)"
        )
        checked += 1
    return checked


def test_excel_import_matches_all_models():
    with tempfile.TemporaryDirectory() as tmp:
        xls = os.path.join(tmp, "imp.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "M1"
        for v in ["alpha", "beta"]:
            ws.append([v])
        ws2 = wb.create_sheet("M2")
        for v in ["gamma", "delta"]:
            ws2.append([v])
        wb.save(xls)

        proj = os.path.join(tmp, "p.arch")
        db = make_project_db(proj, models=[
            {"name": "M1", "status": "In Work", "rows": []},
            {"name": "M2", "status": "In Work", "rows": []},
        ])
        mgr = ArchitectureManager()
        mgr.set_db(db)

        window = QMainWindow()
        window.ui = UI.Ui_MainWindow()
        window.ui.setupUi(window)
        window.current_project_file = proj
        window.edit_mode = True
        controller = _make_controller(window)
        controller.model_manager = mgr
        window.arch_controller = controller
        window.project_db = db
        controller.matcher = FakeMatcher()

        port_idx = next(i for i, c in enumerate(controller.active_columns)
                        if isinstance(c, PortSearchColumn))
        port_col_name = controller.active_columns[port_idx].name
        match_col_name = controller.active_columns[port_idx + 1].name

        with patch('PyQt6.QtWidgets.QFileDialog.getOpenFileName',
                   MagicMock(return_value=(xls, "x"))), \
             patch('Application_Logic.Logic_Architecture_Import.ImportModeDialog') as MM, \
             patch('Application_Logic.Logic_Architecture_Import.ImportConfirmationDialog') as MC, \
             patch('PyQt6.QtWidgets.QMessageBox.information'), \
             patch('PyQt6.QtWidgets.QMessageBox.warning'):
            mi = MagicMock(); mi.exec.return_value = True; mi.selected_mode = "automated"
            MM.return_value = mi
            ci = MagicMock(); ci.exec.return_value = True; ci.selected_action = "confirm"
            MC.return_value = ci
            controller.import_architecture_excel()

        m1 = next(m for m in mgr.models if m.name == "M1")
        m2 = next(m for m in mgr.models if m.name == "M2")

        # BOTH models — not just the active one — must carry eager matches.
        assert _assert_all_ports_matched(m1, port_col_name, match_col_name) == 2
        assert _assert_all_ports_matched(m2, port_col_name, match_col_name) == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
