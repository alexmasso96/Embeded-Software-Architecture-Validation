"""
Integration tests for ArchitectureBaselineMixin (Logic_Architecture_Baseline):
create / load / exit baseline flows driven through a real ApplicationWindow
with all user dialogs mocked.
"""
import os
import sys
import logging
import tempfile
from unittest.mock import patch

logging.disable(logging.CRITICAL)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.abspath("src"))

from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox
app = QApplication.instance() or QApplication(sys.argv)

from main import ApplicationWindow
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Tests.test_helpers import make_project_db


def _make_project(db_path):
    db = make_project_db(
        db_path,
        layout=[
            ("TC. ID", "Static Text", True),
            ("Review Status", "Review Status", True),
            ("Port State", "PortStateColumn", True),
        ],
        models=[{
            "name": "Architecture_1",
            "status": "In Work",
            "rows": [{
                "TC. ID": {"text": "TC_001"},
                "Review Status": {"text": "Not Reviewed"},
                "Port State": {"text": "In Work"},
            }],
        }],
        releases=[{"name": "R1", "elf_hash": "h1", "description": "rel"}],
        settings={"default_cyclicity": "10"},
    )
    releases = db.get_all_releases()
    db.set_active_release(releases[0]["id"])
    db.commit()
    db.close()


def _window_with_project(tmp):
    proj = os.path.join(tmp, "p.arch")
    _make_project(proj)
    with patch.object(ApplicationWindow, "new_project"):
        window = ApplicationWindow()
    ok, msg = ProjectSaver.load_project(window, proj)
    assert ok, msg
    return window, proj


def test_get_current_layout_data_shape():
    with tempfile.TemporaryDirectory() as tmp:
        window, _ = _window_with_project(tmp)
        data = window.arch_controller.get_current_layout_data()
        assert data["version"] == "2.0"
        assert "layout" in data and "settings" in data
        assert "test_case_design" in data


def test_create_baseline_success():
    with tempfile.TemporaryDirectory() as tmp:
        window, _ = _window_with_project(tmp)
        ctrl = window.arch_controller

        with patch.object(QInputDialog, "getText", return_value=("MyBaseline", True)), \
             patch.object(QMessageBox, "information"), \
             patch.object(QMessageBox, "warning"), \
             patch.object(QMessageBox, "critical"):
            ctrl.handle_create_baseline()

        names = [r.name for r in ctrl.release_manager.releases]
        assert "MyBaseline" in names
        baseline = next(r for r in ctrl.release_manager.releases if r.name == "MyBaseline")
        assert baseline.is_baseline


def test_create_baseline_cancelled():
    with tempfile.TemporaryDirectory() as tmp:
        window, _ = _window_with_project(tmp)
        ctrl = window.arch_controller
        before = len(ctrl.release_manager.releases)
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            ctrl.handle_create_baseline()
        assert len(ctrl.release_manager.releases) == before


def test_create_baseline_without_project_warns():
    with tempfile.TemporaryDirectory() as tmp:
        window, _ = _window_with_project(tmp)
        ctrl = window.arch_controller
        ctrl.release_manager.project_path = ""  # simulate unsaved project
        with patch.object(QMessageBox, "warning") as mock_warn, \
             patch.object(QInputDialog, "getText") as mock_text:
            ctrl.handle_create_baseline()
        mock_warn.assert_called_once()
        mock_text.assert_not_called()


def test_load_baseline_none_available_info():
    with tempfile.TemporaryDirectory() as tmp:
        window, _ = _window_with_project(tmp)
        ctrl = window.arch_controller
        with patch.object(QMessageBox, "information") as mock_info, \
             patch.object(QInputDialog, "getItem") as mock_item:
            ctrl.handle_load_baseline()
        mock_info.assert_called_once()
        mock_item.assert_not_called()


def test_load_and_exit_baseline():
    # The LoadingDialog (a background progress widget) plus QApplication.processEvents()
    # are pure UI chrome here and destabilise the headless event loop, so we stub them
    # out and exercise the actual baseline load/exit logic only.
    with tempfile.TemporaryDirectory() as tmp, \
         patch("Application_Logic.Logic_Loading_Window.LoadingDialog", return_value=MagicMock()), \
         patch.object(QApplication, "processEvents"):
        window, proj = _window_with_project(tmp)
        ctrl = window.arch_controller

        # Create a baseline first
        with patch.object(QInputDialog, "getText", return_value=("BL", True)), \
             patch.object(QMessageBox, "information"), \
             patch.object(QMessageBox, "warning"), \
             patch.object(QMessageBox, "critical"):
            ctrl.handle_create_baseline()

        # Load it
        with patch.object(QInputDialog, "getItem", return_value=("BL", True)), \
             patch.object(ProjectSaver, "has_temp_changes", return_value=False), \
             patch.object(QMessageBox, "critical"):
            ctrl.handle_load_baseline()

        assert "BASELINE" in window.windowTitle()

        # Exit baseline view restores the live project
        with patch.object(QMessageBox, "critical"):
            ctrl.handle_exit_baseline()
        assert ctrl.btn_exit_baseline.isVisible() is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
