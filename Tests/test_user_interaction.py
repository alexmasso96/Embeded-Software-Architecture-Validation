"""
Tests for UserInteractionLogic: per-cell override/conflict/purple metadata
and review-status helpers.
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QComboBox
app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic.Logic_User_Interaction import UserInteractionLogic as UIL


def test_mark_and_clear_manual_override():
    item = QTableWidgetItem("x")
    assert UIL.is_item_user_changed(item) is False
    UIL.mark_manual_override(item)
    assert UIL.is_item_user_changed(item) is True
    assert item.font().bold() is True
    UIL.clear_manual_override(item)
    assert UIL.is_item_user_changed(item) is False
    assert item.font().bold() is False


def test_mark_conflict_sets_flag_and_bold():
    item = QTableWidgetItem("x")
    UIL.mark_conflict(item)
    assert UIL.is_item_user_changed(item) is True
    assert item.font().bold() is True


def test_last_function_roundtrip():
    item = QTableWidgetItem("x")
    assert UIL.get_last_function(item) is None
    UIL.set_last_function(item, "Read_Temp")
    assert UIL.get_last_function(item) == "Read_Temp"


def test_purple_marking():
    item = QTableWidgetItem("x")
    assert UIL.is_purple(item) is False
    UIL.mark_purple(item)
    assert UIL.is_purple(item) is True
    UIL.clear_purple(item)
    assert UIL.is_purple(item) is False


def test_none_item_guards():
    # All helpers must tolerate a None item without raising
    assert UIL.is_item_user_changed(None) is False
    assert UIL.get_last_function(None) is None
    assert UIL.is_purple(None) is False
    UIL.mark_manual_override(None)
    UIL.mark_conflict(None)
    UIL.clear_manual_override(None)
    UIL.set_last_function(None, "f")
    UIL.mark_purple(None)
    UIL.clear_purple(None)


class _StubController:
    """Minimal controller exposing get_column_index_by_type for a ReviewColumn."""
    def __init__(self, review_idx):
        self._idx = review_idx

    def get_column_index_by_type(self, col_type):
        return self._idx if col_type == "ReviewColumn" else -1


def _table_with_review(initial="Reviewed"):
    table = QTableWidget(1, 2)
    combo = QComboBox()
    combo.addItems(["Not Reviewed", "Reviewed"])
    combo.setCurrentText(initial)
    table.setCellWidget(0, 1, combo)
    return table


def test_get_review_status():
    table = _table_with_review("Reviewed")
    ctrl = _StubController(review_idx=1)
    assert UIL.get_review_status(table, 0, ctrl) == "Reviewed"


def test_get_review_status_no_review_column():
    table = _table_with_review()
    ctrl = _StubController(review_idx=-1)
    assert UIL.get_review_status(table, 0, ctrl) is None


def test_reset_review_status():
    table = _table_with_review("Reviewed")
    ctrl = _StubController(review_idx=1)
    UIL.reset_review_status(table, 0, ctrl)
    assert table.cellWidget(0, 1).currentText() == "Not Reviewed"
    # Idempotent: resetting again leaves it as Not Reviewed
    UIL.reset_review_status(table, 0, ctrl)
    assert table.cellWidget(0, 1).currentText() == "Not Reviewed"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
