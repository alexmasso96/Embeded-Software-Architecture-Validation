"""
Tests for HistoryDialog (Dialog_History): population, timestamp formatting,
newest-first sorting, and graceful handling of invalid timestamps.
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from UI.Dialog_History import HistoryDialog


def test_populates_rows_sorted_newest_first():
    entries = [
        {"timestamp": "2024-01-01T10:00:00", "user": "alice", "model": "M1", "description": "old"},
        {"timestamp": "2024-06-01T10:00:00", "user": "bob", "model": "M2", "description": "new"},
    ]
    dlg = HistoryDialog(entries)
    assert dlg.table.rowCount() == 2
    # Newest first
    assert dlg.table.item(0, 1).text() == "bob"
    assert dlg.table.item(1, 1).text() == "alice"


def test_valid_timestamp_formatted():
    dlg = HistoryDialog([
        {"timestamp": "2024-01-02T03:04:05", "user": "u", "model": "m", "description": "d"}
    ])
    assert dlg.table.item(0, 0).text() == "2024-01-02 03:04:05 UTC"


def test_invalid_timestamp_kept_raw():
    dlg = HistoryDialog([
        {"timestamp": "not-a-date", "user": "u", "model": "m", "description": "d"}
    ])
    assert dlg.table.item(0, 0).text() == "not-a-date"


def test_missing_fields_use_defaults():
    dlg = HistoryDialog([{"timestamp": ""}])
    assert dlg.table.rowCount() == 1
    assert dlg.table.item(0, 2).text() == "N/A"  # model default


def test_empty_history():
    dlg = HistoryDialog([])
    assert dlg.table.rowCount() == 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
