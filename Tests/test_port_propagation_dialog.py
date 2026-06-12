"""
#8.2 — PortPropagationDialog + its wiring into ArchitectureManagerDialog.

The dialog is built from plain data (columns/rows/new_status), so most of it is
testable without simulating real mouse events. The manager-dialog wiring is tested
with the dialog patched out (accept/cancel/selection), per the testing strategy.
"""
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Tests.test_helpers import make_project_db
from UI.Dialog_Port_Propagation import PortPropagationDialog
from UI.Dialog_Architecture_Manager import ArchitectureManagerDialog

MOD = "UI.Dialog_Architecture_Manager"

COLUMNS = [("Port", "PortSearchColumn"),
           ("Port State", "PortStateColumn"),
           ("Note", "TextColumn")]


def _rows():
    return [
        {"Port": {"text": "p_a"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
        {"Port": {"text": "p_b"}, "Port State": {"text": "Released"}},
        {"Port": {"text": "p_a"}, "Port State": {"text": "In Work"}},   # dup of p_a
        {"Port": {"text": "p_c"}, "Port State": {"text": "In Work"}},
    ]


# ── dialog: column defaults + scanning ───────────────────────────────────────

def test_default_columns_selected_by_type():
    dlg = PortPropagationDialog(COLUMNS, _rows(), "Released")
    assert dlg.get_port_name_column() == "Port"
    assert dlg.get_port_state_column() == "Port State"


def test_scan_dedupes_and_filters_in_work():
    dlg = PortPropagationDialog(COLUMNS, _rows(), "Released")
    assert dlg.scan_in_work_ports() == ["p_a", "p_c"]   # p_b Released excluded, p_a once
    assert dlg.has_ports() is True
    assert dlg.list_widget.count() == 2


def test_all_items_checked_by_default():
    dlg = PortPropagationDialog(COLUMNS, _rows(), "Released")
    assert dlg.get_selected_ports() == ["p_a", "p_c"]


def test_select_none_and_all():
    dlg = PortPropagationDialog(COLUMNS, _rows(), "Released")
    dlg.on_select_none()
    assert dlg.get_selected_ports() == []
    dlg.on_select_all()
    assert dlg.get_selected_ports() == ["p_a", "p_c"]


def test_manual_uncheck_reflected():
    dlg = PortPropagationDialog(COLUMNS, _rows(), "Released")
    dlg.list_widget.item(0).setCheckState(Qt.CheckState.Unchecked)   # uncheck p_a
    assert dlg.get_selected_ports() == ["p_c"]


def test_changing_state_column_rescans():
    dlg = PortPropagationDialog(COLUMNS, _rows(), "Released")
    # Point the "state" column at 'Port' (no cell equals 'In Work') → no candidates.
    dlg.cmb_port_state.setCurrentIndex(0)   # "Port"
    assert dlg.scan_in_work_ports() == []
    assert dlg.has_ports() is False


def test_no_ports_when_none_in_work():
    rows = [{"Port": {"text": "p_a"}, "Port State": {"text": "Released"}}]
    dlg = PortPropagationDialog(COLUMNS, rows, "Released")
    assert dlg.has_ports() is False
    assert dlg.get_selected_ports() == []


# ── wiring: ArchitectureManagerDialog._propagate_state_to_ports ──────────────

def _mgr_with_ports(tmp):
    db = make_project_db(
        os.path.join(tmp, "p.arch"),
        layout=[("Port", "PortSearchColumn", True),
                ("Port State", "PortStateColumn", True)],
        models=[{"name": "Model_A", "status": "In Work", "rows": [
            {"Port": {"text": "p_a"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
            {"Port": {"text": "p_d"}, "Port State": {"text": "In Work", "widget_text": "In Work"}},
        ]}],
    )
    mgr = ArchitectureManager()
    mgr.set_db(db)
    return mgr, db


def _fake_dialog(selected, accepted=True, has_ports=True):
    fake = MagicMock()
    fake.has_ports.return_value = has_ports
    fake.exec.return_value = accepted
    fake.get_selected_ports.return_value = selected
    fake.get_port_state_column.return_value = "Port State"
    fake.get_port_name_column.return_value = "Port"
    return fake


def test_wiring_confirm_propagates_only_selected():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr_with_ports(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        model = mgr.models[0]
        with patch(f"{MOD}.PortPropagationDialog", return_value=_fake_dialog(["p_a"])):
            dlg._propagate_state_to_ports(model, "In Work", "Released")
        states = {r["Port"]["text"]: r["Port State"]["text"]
                  for r in model.data_cache["rows"]}
        assert states == {"p_a": "Released", "p_d": "In Work"}
        db.close()


def test_wiring_cancel_changes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr_with_ports(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        model = mgr.models[0]
        with patch(f"{MOD}.PortPropagationDialog",
                   return_value=_fake_dialog(["p_a"], accepted=False)):
            dlg._propagate_state_to_ports(model, "In Work", "Released")
        states = [r["Port State"]["text"] for r in model.data_cache["rows"]]
        assert states == ["In Work", "In Work"]
        db.close()


def test_wiring_non_transition_never_opens_dialog():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr_with_ports(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        model = mgr.models[0]
        with patch(f"{MOD}.PortPropagationDialog") as MockDlg:
            # Released → Retired is not an 'In Work' exit.
            dlg._propagate_state_to_ports(model, "Released", "Retired")
            # Staying In Work likewise.
            dlg._propagate_state_to_ports(model, "In Work", "In Work")
        MockDlg.assert_not_called()
        db.close()


def test_wiring_no_ports_does_not_exec():
    with tempfile.TemporaryDirectory() as tmp:
        mgr, db = _mgr_with_ports(tmp)
        dlg = ArchitectureManagerDialog(mgr)
        model = mgr.models[0]
        fake = _fake_dialog([], has_ports=False)
        with patch(f"{MOD}.PortPropagationDialog", return_value=fake):
            dlg._propagate_state_to_ports(model, "In Work", "Released")
        fake.exec.assert_not_called()
        states = [r["Port State"]["text"] for r in model.data_cache["rows"]]
        assert states == ["In Work", "In Work"]
        db.close()
