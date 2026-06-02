"""
Tests for the Rhapsody export parser (Logic_Rhapsody_Import).
Pure-logic module: CSV/XLSX reading, path parsing, operation splitting,
model preview and import-data building. No Qt required.
"""
import os
import sys
import csv
import tempfile
from pathlib import Path

sys.path.append(os.path.abspath("src"))

import openpyxl
from Application_Logic import Logic_Rhapsody_Import as R


P10 = "P10_SW_Arch_Public"
PATH_A1 = f"Components::P_SW_Components::ModelA::{P10}::IfTemp"
PATH_A2 = f"Components::P_SW_Components::ModelA::{P10}::IfSpeed"
PATH_A_PROVIDED = f"Components::P_SW_Components::ModelA::{P10}::IfProvided"
PATH_B_NON_P10 = "Components::P_SW_Components::ModelB::P11_Other::IfX"

HEADER = ["Port Name", "Path", "Required Interface", "Operations"]
DATA_ROWS = [
    ["p_i_temp", PATH_A1, "ITemp", "op_read,\nop_write,\nop_reset"],
    ["p_i_speed", PATH_A2, "ISpeed", "op_get"],
    ["p_provided", PATH_A_PROVIDED, "", ""],          # provided stub, empty required
    ["p_x", PATH_B_NON_P10, "IX", "op_x"],            # non-P10, excluded
]


def _write_csv(path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(DATA_ROWS)


def _write_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for row in DATA_ROWS:
        ws.append(row)
    wb.save(path)


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def test_detect_rhapsody_format_csv():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "export.csv")
        _write_csv(p)
        is_rh, col = R.detect_rhapsody_format(p)
        assert is_rh is True
        assert col == "Path"


def test_detect_rhapsody_format_xlsx():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "export.xlsx")
        _write_xlsx(p)
        is_rh, col = R.detect_rhapsody_format(p)
        assert is_rh is True
        assert col == "Path"


def test_detect_rhapsody_format_negative():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "plain.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["A", "B"])
            w.writerow(["1", "2"])
        is_rh, col = R.detect_rhapsody_format(p)
        assert is_rh is False
        assert col is None


def test_detect_rhapsody_format_missing_file():
    is_rh, col = R.detect_rhapsody_format("/no/such/file.csv")
    assert is_rh is False
    assert col is None


# --------------------------------------------------------------------------
# File reading
# --------------------------------------------------------------------------

def test_read_file_csv():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "export.csv")
        _write_csv(p)
        columns, rows = R.read_file(p)
        assert columns == HEADER
        assert len(rows) == 4
        assert rows[0]["Port Name"] == "p_i_temp"
        assert rows[0]["Path"] == PATH_A1


def test_read_file_xlsx():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "export.xlsx")
        _write_xlsx(p)
        columns, rows = R.read_file(p)
        assert columns == HEADER
        assert len(rows) == 4
        assert rows[1]["Port Name"] == "p_i_speed"


# --------------------------------------------------------------------------
# Path helpers
# --------------------------------------------------------------------------

def test_extract_model_name():
    assert R.extract_model_name(PATH_A1) == "ModelA"
    assert R.extract_model_name("only::two") is None
    assert R.extract_model_name("") is None


def test_is_p10_row():
    assert R.is_p10_row(PATH_A1) is True
    assert R.is_p10_row(PATH_B_NON_P10) is False


def test_detect_required_interface_col():
    assert R.detect_required_interface_col(HEADER, "Path", "Operations") == "Required Interface"
    # No interface-like column -> None
    assert R.detect_required_interface_col(["Port Name", "Path"], "Path") is None


# --------------------------------------------------------------------------
# Operation splitting
# --------------------------------------------------------------------------

def test_split_operations_basic():
    assert R.split_operations("op_read,\nop_write,\nop_reset") == ["op_read", "op_write", "op_reset"]


def test_split_operations_xml_cr_entity():
    # openpyxl sometimes emits _x000D_ instead of \r
    assert R.split_operations("op_a,_x000D_\nop_b") == ["op_a", "op_b"]


def test_split_operations_empty():
    assert R.split_operations("") == []
    assert R.split_operations("   ") == []
    assert R.split_operations(None) == []


def test_split_operations_single():
    assert R.split_operations("only_op") == ["only_op"]


# --------------------------------------------------------------------------
# Model preview
# --------------------------------------------------------------------------

def test_get_model_preview_with_required_col():
    _, rows = _read_rows()
    preview = R.get_model_preview(rows, "Path", required_col="Required Interface")
    # ModelA has p_i_temp + p_i_speed (provided excluded); ModelB is non-P10
    assert preview == {"ModelA": 2}


def test_get_model_preview_without_required_col():
    _, rows = _read_rows()
    preview = R.get_model_preview(rows, "Path")
    # provided stub now counted too
    assert preview == {"ModelA": 3}


# --------------------------------------------------------------------------
# Import data builder
# --------------------------------------------------------------------------

def test_build_import_data_expands_operations():
    _, rows = _read_rows()
    col_mapping = {
        "Port Name": "PortCol",
        "Required Interface": "ReqCol",
        "Operations": "OpsCol",
    }
    data = R.build_import_data(
        rows, col_mapping, path_col="Path",
        ops_col="Operations", required_col="Required Interface",
    )
    assert set(data.keys()) == {"ModelA"}
    # p_i_temp -> 3 ops, p_i_speed -> 1 op = 4 rows
    assert len(data["ModelA"]) == 4
    # Each expanded row carries the operation in OpsCol
    ops = sorted(r["OpsCol"]["text"] for r in data["ModelA"])
    assert ops == ["op_get", "op_read", "op_reset", "op_write"]
    # Base columns preserved
    assert any(r["PortCol"]["text"] == "p_i_temp" for r in data["ModelA"])


def test_build_import_data_no_ops_column():
    _, rows = _read_rows()
    col_mapping = {"Port Name": "PortCol", "Required Interface": "ReqCol"}
    data = R.build_import_data(
        rows, col_mapping, path_col="Path",
        ops_col=None, required_col="Required Interface",
    )
    # No expansion: one row per qualifying P10 port = 2
    assert len(data["ModelA"]) == 2


def test_build_import_data_keeps_provided_without_required_filter():
    _, rows = _read_rows()
    col_mapping = {"Port Name": "PortCol", "Operations": "OpsCol"}
    data = R.build_import_data(
        rows, col_mapping, path_col="Path",
        ops_col="Operations", required_col=None,
    )
    # Without required filter, provided stub has a port name so it is kept.
    port_names = sorted(r["PortCol"]["text"] for r in data["ModelA"])
    assert "p_provided" in port_names


def _read_rows():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "export.csv")
        _write_csv(p)
        return R.read_file(p)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
