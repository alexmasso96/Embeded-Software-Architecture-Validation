"""
#2E Phase 1 — Release Selection import/unload UI smoke tests.

Constructs the real ReleaseSelectionDialog and drives on_import_source /
on_unload_source with the folder picker + message boxes mocked, confirming the
worker path stores source into the DB and unload drops it (keeping maps). Full
visual behaviour is checked manually per the project testing strategy.
"""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QMainWindow
app = QApplication.instance() or QApplication(sys.argv)

import UI
from Application_Logic.Logic_Database import ProjectDatabase
from UI.architecture_table import ArchitectureTabController
from UI.Dialog_Release_Selection import ReleaseSelectionDialog
from Tests.test_helpers import make_project_db

MOD = "UI.Dialog_Release_Selection"


def _setup(tmp):
    db_path = os.path.join(tmp, "p.arch")
    make_project_db(db_path,
                    layout=[("Port", "PortSearchColumn", True)],
                    models=[{"name": "Model_A", "status": "In Work", "rows": []}],
                    releases=[{"name": "R1.0"}]).close()

    window = QMainWindow()
    window.ui = UI.Ui_MainWindow()
    window.ui.setupUi(window)
    window.current_project_file = db_path
    window.edit_mode = True
    db = ProjectDatabase()
    db.open(db_path)
    window.project_db = db
    controller = ArchitectureTabController(window)
    controller.model_manager.set_db(db)
    controller.release_manager.set_db(db)
    window.arch_controller = controller

    dlg = ReleaseSelectionDialog(controller.release_manager, controller, window)
    return dlg, controller, db, db_path


def _src_tree(root):
    os.makedirs(os.path.join(root, "src"))
    with open(os.path.join(root, "src", "a.c"), "w") as f:
        f.write("int a(void){return 0;}\n")
    with open(os.path.join(root, "src", "a.h"), "w") as f:
        f.write("int a(void);\n")


def test_import_then_unload_source_via_dialog():
    with tempfile.TemporaryDirectory() as tmp:
        dlg, controller, db, _ = _setup(tmp)
        rid = db.get_all_releases()[0]["id"]
        dlg.list_widget.setCurrentRow(0)

        src = os.path.join(tmp, "code")
        os.makedirs(src)
        _src_tree(src)

        with patch(f"{MOD}.QFileDialog.getExistingDirectory", return_value=src), \
             patch(f"{MOD}.QMessageBox.information"):
            dlg.on_import_source()

        assert db.has_release_source(rid) is True
        files = {f["rel_path"] for f in db.list_release_source_files(rid)}
        assert files == {"src/a.c", "src/a.h"}

        # A code map for the model must survive the unload.
        mid = db.get_all_models()[0]["id"]
        db.save_model_code_map(mid, '{"functions": {}}')

        import UI.Dialog_Release_Selection as M

        def _auto_yes(self):
            self.result_button = M.QMessageBox.StandardButton.Yes
            return 1

        with patch(f"{MOD}.QMessageBox.information"), \
             patch.object(M.QMessageBox, "exec", _auto_yes):
            dlg.on_unload_source()

        assert db.has_release_source(rid) is False
        assert db.get_model_code_map(mid) == {"functions": {}}
        db.close()
