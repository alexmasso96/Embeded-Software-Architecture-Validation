"""
Tests for RhapsodyImportDialog (Dialog_Rhapsody_Import): column/model combo
auto-selection and the _on_import output mappings (col_mapping, new_columns,
model_mapping). No real user interaction.
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from UI.Dialog_Rhapsody_Import import RhapsodyImportDialog, _SKIP

COLUMNS = ["Port Name", "Path", "Required Interface", "Operations"]
PATH_COL = "Path"
OPS_COL = "Operations"
ROWS = [
    {"Port Name": "p_a", "Path": "x::y::ModelA::P10", "Required Interface": "I", "Operations": "op1"},
    {"Port Name": "p_b", "Path": "x::y::ModelB::P10", "Required Interface": "J", "Operations": "op2"},
]
MODEL_PREVIEW = {"ModelA": 2, "ModelB": 1}
EXISTING_COLS = ["Port Name", "Cyclicity"]
EXISTING_MODELS = ["ModelA"]


def _dlg():
    return RhapsodyImportDialog(
        file_path="/tmp/export.csv",
        columns=COLUMNS,
        rows=ROWS,
        path_col=PATH_COL,
        ops_col=OPS_COL,
        model_preview=MODEL_PREVIEW,
        existing_table_cols=EXISTING_COLS,
        existing_model_names=EXISTING_MODELS,
    )


def test_path_col_has_no_combo():
    dlg = _dlg()
    assert PATH_COL not in dlg._col_combos
    # Every non-path source column has a combo
    assert set(dlg._col_combos.keys()) == {"Port Name", "Required Interface", "Operations"}


def test_column_auto_selection():
    dlg = _dlg()
    # Exact name match -> selects the existing table column
    assert dlg._col_combos["Port Name"].currentText() == "Port Name"
    # No match -> create-new suggestion
    assert dlg._col_combos["Required Interface"].currentText().startswith("<Create new:")


def test_model_auto_selection():
    dlg = _dlg()
    # Matching existing model -> preselected
    assert dlg._model_combos["ModelA"].currentText() == "ModelA"
    # No existing match -> Create New
    assert dlg._model_combos["ModelB"].currentText() == "<Create New>"


def test_on_import_default_mappings():
    dlg = _dlg()
    dlg._on_import()
    assert dlg.result() == dlg.DialogCode.Accepted.value

    # Port Name maps to existing column (not a new column)
    assert dlg.col_mapping["Port Name"] == "Port Name"
    # Required Interface + Operations map to brand-new columns
    assert dlg.col_mapping["Required Interface"] == "Required Interface"
    assert set(dlg.new_columns) == {"Required Interface", "Operations"}

    assert dlg.model_mapping["ModelA"] == "ModelA"
    assert dlg.model_mapping["ModelB"] == "<Create New>"


def test_on_import_respects_skip():
    dlg = _dlg()
    dlg._col_combos["Required Interface"].setCurrentText(_SKIP)
    dlg._on_import()
    # Skipped column excluded from mapping and new columns
    assert "Required Interface" not in dlg.col_mapping
    assert "Required Interface" not in dlg.new_columns


def test_on_import_existing_column_choice():
    dlg = _dlg()
    # Re-target Operations onto an existing column instead of creating a new one
    dlg._col_combos["Operations"].setCurrentText("Cyclicity")
    dlg._on_import()
    assert dlg.col_mapping["Operations"] == "Cyclicity"
    assert "Operations" not in dlg.new_columns


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
