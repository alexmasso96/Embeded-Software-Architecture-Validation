"""
Tests for NewProjectController (Logic_New_Project): the background parse logic
for ELF and JSON modes, plus the file/input-dialog handlers with all user
interaction mocked out.
"""
import os
import sys
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

logging.disable(logging.CRITICAL)
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

import UI  # noqa: F401  (ensure UI package initialised)
from Application_Logic.Logic_New_Project import NewProjectController
from Application_Logic.Logic_Database import ProjectDatabase
from core.elf_parser import ELFParser

ELF = str(Path(__file__).parent / "Resources" / "sample.elf")


def _open_db(tmp):
    db = ProjectDatabase()
    db.open(os.path.join(tmp, "p.arch"))
    return db


def test_parse_logic_elf_streams_to_db():
    with tempfile.TemporaryDirectory() as tmp:
        db = _open_db(tmp)
        ctrl = NewProjectController(main_window=None, project_db=db)
        parser = ctrl._parse_logic("ELF", ELF)
        assert parser.md5_hash
        assert db.has_elf(parser.md5_hash)
        db.close()


def test_parse_logic_json_loads_and_flushes():
    with tempfile.TemporaryDirectory() as tmp:
        # Build a JSON cache from the fixture
        src = ELFParser()
        src.load_elf(ELF)
        src.extract_all()
        cache = os.path.join(tmp, "cache.json")
        src.save_cache(cache)

        db = _open_db(tmp)
        ctrl = NewProjectController(main_window=None, project_db=db)
        parser = ctrl._parse_logic("JSON", cache)
        assert parser.md5_hash == src.md5_hash
        assert db.has_elf(parser.md5_hash)
        db.close()


def test_parse_logic_json_invalid_raises():
    with tempfile.TemporaryDirectory() as tmp:
        bad = os.path.join(tmp, "bad.json")
        with open(bad, "w") as f:
            f.write("{not valid json")
        ctrl = NewProjectController(main_window=None, project_db=None)
        try:
            ctrl._parse_logic("JSON", bad)
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_start_empty_handler_sets_flag():
    ctrl = NewProjectController(main_window=None, project_db=None)
    assert ctrl._start_empty is False
    ctrl.start_empty_handler()
    assert ctrl._start_empty is True


def test_help_new_project_opens_window():
    ctrl = NewProjectController(main_window=None, project_db=None)
    ctrl.help_new_project()
    assert ctrl.help_window is not None
    ctrl.help_window.close()


def test_open_elf_handler_success():
    with tempfile.TemporaryDirectory() as tmp:
        db = _open_db(tmp)
        ctrl = NewProjectController(main_window=None, project_db=db)

        fake_parser = MagicMock()
        fake_parser.get_statistics.return_value = {"functions": 4}
        fake_loader = MagicMock()
        fake_loader.run_task.return_value = True
        fake_loader.result = fake_parser

        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                   return_value=(ELF, "")), \
             patch("PyQt6.QtWidgets.QInputDialog.getText",
                   return_value=("R1.0", True)), \
             patch("Application_Logic.Logic_New_Project.LoadingDialog",
                   return_value=fake_loader), \
             patch.object(ctrl, "show_message") as mock_show:
            ctrl.open_elf_handler()

        assert ctrl.parser is fake_parser
        assert ctrl.release_name == "R1.0"
        # Inc-03: a successful load proceeds straight to the workspace — no
        # blocking success popup; the dialog closes so main.py enters the table.
        mock_show.assert_not_called()
        assert ctrl._closing is True
        db.close()


def test_open_elf_handler_cancelled_release_name():
    ctrl = NewProjectController(main_window=None, project_db=None)
    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
               return_value=(ELF, "")), \
         patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("", False)):
        ctrl.open_elf_handler()
    # User cancelled the release-name prompt -> no parser set
    assert ctrl.parser is None


def test_open_json_handler_success():
    with tempfile.TemporaryDirectory() as tmp:
        ctrl = NewProjectController(main_window=None, project_db=None)
        fake_loader = MagicMock()
        fake_loader.run_task.return_value = True
        fake_loader.result = MagicMock()

        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
                   return_value=("/tmp/cache.json", "")), \
             patch("PyQt6.QtWidgets.QInputDialog.getText",
                   return_value=("R2.0", True)), \
             patch("Application_Logic.Logic_New_Project.LoadingDialog",
                   return_value=fake_loader), \
             patch.object(ctrl, "show_message") as mock_show:
            ctrl.open_json_handler()

        assert ctrl.release_name == "R2.0"
        # Inc-03: successful load proceeds straight to the workspace (no popup).
        mock_show.assert_not_called()
        assert ctrl._closing is True


def test_open_elf_handler_failure_shows_error():
    ctrl = NewProjectController(main_window=None, project_db=None)
    fake_loader = MagicMock()
    fake_loader.run_task.return_value = False
    fake_loader.error_msg = "parse blew up"

    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName",
               return_value=(ELF, "")), \
         patch("PyQt6.QtWidgets.QInputDialog.getText",
               return_value=("R1.0", True)), \
         patch("Application_Logic.Logic_New_Project.LoadingDialog",
               return_value=fake_loader), \
         patch.object(ctrl, "show_message") as mock_show:
        ctrl.open_elf_handler()

    mock_show.assert_called_once()
    assert ctrl.parser is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
