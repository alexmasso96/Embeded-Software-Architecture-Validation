"""
Tests for #8 — Rhapsody-import architecture cleanup helpers on the controller:

 * _drop_unmapped_rhapsody_columns: drops the redundant Mapped Func / Mapped
   Parameter column families (kept only if the import mapped onto them), and
   purges the orphaned cells from every model's cached rows.
 * _delete_default_model_if_untouched: soft-deletes the empty default
   Architecture_1 placeholder once real models have been imported — but only the
   untouched default, and only when models were actually produced.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication, QMainWindow
app = QApplication.instance() or QApplication(sys.argv)

import UI
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
from Tests.test_helpers import make_project_db


def _controller(tmp, models):
    proj_path = os.path.join(tmp, "p.arch")
    db = make_project_db(
        proj_path,
        layout=[("Port", "PortSearchColumn", True)],
        models=models,
    )
    mgr = ArchitectureManager()
    mgr.set_db(db)

    window = QMainWindow()
    window.ui = UI.Ui_MainWindow()
    window.ui.setupUi(window)
    window.current_project_file = proj_path
    window.project_db = db

    controller = ArchitectureTabController(window)
    controller.model_manager = mgr
    controller._db = db
    window.arch_controller = controller
    return controller, mgr, db


def test_drop_unmapped_columns_removes_mapped_families():
    with tempfile.TemporaryDirectory() as tmp:
        controller, mgr, db = _controller(
            tmp, [{"name": "Architecture_1", "status": "In Work", "rows": []}])

        # Default schema carries the Mapped Func / Mapped Parameter families.
        controller.active_config = [
            ("TC. ID", "Static Text", True),
            ("Input Port", "Port Search", True),
            ("Input Port (Match)", "Static Text", True),
            ("Mapped Func", "Function Search", True),
            ("Mapped Func (Match)", "Static Text", True),
            ("Mapped Parameter", "Variable Search", True),
            ("Mapped Parameter (Match)", "Static Text", True),
            ("Port State", "PortStateColumn", True),
        ]
        controller._rebuild_column_objects()
        controller._setup_table_style()

        # Operations were mapped onto Input Port only — both families are unmapped.
        controller._drop_unmapped_rhapsody_columns({"Input Port"})

        names = [c[0] for c in controller.active_config]
        assert "Mapped Func" not in names
        assert "Mapped Func (Match)" not in names
        assert "Mapped Parameter" not in names
        assert "Mapped Parameter (Match)" not in names
        assert "Input Port" in names
        assert "Port State" in names
        db.close()


def test_drop_keeps_family_that_was_mapped():
    with tempfile.TemporaryDirectory() as tmp:
        controller, mgr, db = _controller(
            tmp, [{"name": "Architecture_1", "status": "In Work", "rows": []}])
        controller.active_config = [
            ("Input Port", "Port Search", True),
            ("Mapped Func", "Function Search", True),
            ("Mapped Func (Match)", "Static Text", True),
            ("Mapped Parameter", "Variable Search", True),
            ("Mapped Parameter (Match)", "Static Text", True),
        ]
        controller._rebuild_column_objects()
        controller._setup_table_style()

        # The import mapped a source column onto Mapped Func — keep that family,
        # drop the unmapped Mapped Parameter family.
        controller._drop_unmapped_rhapsody_columns({"Input Port", "Mapped Func"})
        names = [c[0] for c in controller.active_config]
        assert "Mapped Func" in names
        assert "Mapped Func (Match)" in names
        assert "Mapped Parameter" not in names
        db.close()


def test_drop_purges_orphaned_cells_from_rows():
    with tempfile.TemporaryDirectory() as tmp:
        controller, mgr, db = _controller(
            tmp, [{"name": "Architecture_1", "status": "In Work", "rows": []}])
        controller.active_config = [
            ("Input Port", "Port Search", True),
            ("Mapped Parameter", "Variable Search", True),
            ("Mapped Parameter (Match)", "Static Text", True),
        ]
        controller._rebuild_column_objects()
        controller._setup_table_style()

        model = mgr.models[0]
        model.data_cache = {"rows": [
            {"Input Port": {"text": "p"}, "Mapped Parameter": {"text": "v"},
             "Mapped Parameter (Match)": {"widget_text": "v (90%)"}},
        ]}
        controller._drop_unmapped_rhapsody_columns({"Input Port"})

        row = model.data_cache["rows"][0]
        assert "Mapped Parameter" not in row
        assert "Mapped Parameter (Match)" not in row
        assert "Input Port" in row
        db.close()


def test_delete_default_model_when_import_produced_models():
    with tempfile.TemporaryDirectory() as tmp:
        controller, mgr, db = _controller(tmp, [
            {"name": "Architecture_1", "status": "In Work", "rows": []},
            {"name": "SWC_A", "status": "In Work", "rows": []},
        ])
        imported = next(m for m in mgr.models if m.name == "SWC_A")
        imported.data_cache = {"rows": [{"Port": {"text": "p"}}]}

        arch1 = next(m for m in mgr.models if m.name == "Architecture_1")
        assert not arch1.is_deleted

        controller._delete_default_model_if_untouched([imported])
        assert arch1.is_deleted is True
        db.close()


def test_keep_default_model_when_it_has_rows():
    with tempfile.TemporaryDirectory() as tmp:
        controller, mgr, db = _controller(tmp, [
            {"name": "Architecture_1", "status": "In Work", "rows": []},
            {"name": "SWC_A", "status": "In Work", "rows": []},
        ])
        arch1 = next(m for m in mgr.models if m.name == "Architecture_1")
        arch1.data_cache = {"rows": [{"Port": {"text": "real"}}]}
        imported = next(m for m in mgr.models if m.name == "SWC_A")
        imported.data_cache = {"rows": [{"Port": {"text": "p"}}]}

        controller._delete_default_model_if_untouched([imported])
        assert arch1.is_deleted is False
        db.close()


def test_no_default_deletion_when_no_models_produced():
    with tempfile.TemporaryDirectory() as tmp:
        controller, mgr, db = _controller(
            tmp, [{"name": "Architecture_1", "status": "In Work", "rows": []}])
        arch1 = mgr.models[0]
        controller._delete_default_model_if_untouched([])
        assert arch1.is_deleted is False
        db.close()
