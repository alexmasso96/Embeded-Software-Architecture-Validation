import sys
import os
import tempfile
from unittest.mock import MagicMock, patch

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
from main import ApplicationWindow
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Tests.test_helpers import make_project_db

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)


def test_project_isolation():
    print("=" * 70)
    print("TESTING PROJECT ISOLATION AND LOADING")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        proj_a_path = os.path.join(tmp, "project_empty.arch")
        proj_b_path = os.path.join(tmp, "project_data.arch")

        # --- Project A: minimal layout, one model, one release ---
        make_project_db(
            proj_a_path,
            layout=[
                ("TC. ID", "Static Text", True),
                ("Input Port", "Port Search", True),
            ],
            models=[{
                "name": "Architecture_1",
                "status": "In Work",
                "rows": [{"TC. ID": {"text": ""}}],
            }],
            releases=[{"name": "R1.0"}],
            settings={"default_cyclicity": "10"},
        ).close()

        # --- Project B: different layout, two models, one release ---
        make_project_db(
            proj_b_path,
            layout=[
                ("TC. ID", "Static Text", True),
                ("Input Port", "Port Search", True),
                ("Link", "Link", True),
                ("Release_R12_Result", "ReleaseResultColumn", True),
            ],
            models=[
                {
                    "name": "HDR_Supervisor",
                    "status": "In Work",
                    "rows": [{"TC. ID": {"text": "TC_HDR"}, "Input Port": {"text": "Port_HDR"}}],
                },
                {
                    "name": "LeAdapter_Sw",
                    "status": "In Work",
                    "rows": [{"TC. ID": {"text": "TC_LE"}, "Input Port": {"text": "Port_LE"}, "Link": {"text": "Yes"}}],
                },
            ],
            releases=[{"name": "R12"}],
            settings={"default_cyclicity": "20"},
        ).close()
        # Set LeAdapter_Sw as active model in project B
        from Application_Logic.Logic_Database import ProjectDatabase
        tmp_db = ProjectDatabase()
        tmp_db.open(proj_b_path)
        models = tmp_db.get_all_models()
        le_model = next(m for m in models if m["name"] == "LeAdapter_Sw")
        tmp_db.set_ui_state("active_model_id", str(le_model["id"]))
        releases = tmp_db.get_all_releases()
        r12 = next(r for r in releases if r["name"] == "R12")
        tmp_db.set_active_release(r12["id"])
        tmp_db.commit()
        tmp_db.close()

        with patch.object(ApplicationWindow, 'new_project'):
            window = ApplicationWindow()

        # ---- Load Project A ----
        print("\nLoading Project A...")
        success, msg = ProjectSaver.load_project(window, proj_a_path)
        assert success, f"Failed to load Project A: {msg}"
        window.current_project_file = proj_a_path

        assert len(window.arch_controller.active_config) == 2
        assert window.arch_controller.release_manager.get_active_release().name == "R1.0"
        assert window.arch_controller.model_manager.get_active_model().name == "Architecture_1"
        print("Project A loaded correctly.")

        # ---- Load Project B ----
        print("\nLoading Project B...")
        success, msg = ProjectSaver.load_project(window, proj_b_path)
        assert success, f"Failed to load Project B: {msg}"
        window.current_project_file = proj_b_path

        assert window.arch_controller.release_manager.get_active_release().name == "R12"
        assert window.arch_controller.model_manager.get_active_model().name == "LeAdapter_Sw"

        print(f"Columns after loading Project B: {[c.name for c in window.arch_controller.active_columns]}")
        assert len(window.arch_controller.active_config) == 4
        assert len(window.arch_controller.active_columns) == 4
        assert window.arch_controller.active_columns[2].name == "Link"
        assert window.arch_controller.active_columns[3].name == "Release_R12_Result"

        assert window.arch_controller.table.rowCount() == 1
        tc_id_item = window.arch_controller.table.item(0, 0)
        port_item = window.arch_controller.table.item(0, 1)
        assert tc_id_item is not None and tc_id_item.text() == "TC_LE"
        assert port_item is not None and port_item.text() == "Port_LE"

        # Verify Project B DB is intact (not contaminated by project A load)
        check_db = ProjectDatabase()
        check_db.open(proj_b_path)
        rels = check_db.get_all_releases()
        assert any(r["name"] == "R12" for r in rels), "Project B release registry was corrupted!"
        check_db.close()

        # Verify Resizability Properties (Splitter & Headers)
        print("Verifying Resizability Properties...")
        splitter = window.ui.splitter
        assert splitter.handleWidth() == 8
        assert not splitter.isCollapsible(0)
        assert not splitter.isCollapsible(1)

        header = window.arch_controller.table.horizontalHeader()
        from PyQt6.QtWidgets import QHeaderView
        for i in range(window.arch_controller.table.columnCount()):
            mode = header.sectionResizeMode(i)
            assert mode == QHeaderView.ResizeMode.Interactive

        from Application_Logic.Logic_Column_Types import LastResultColumn, ReleaseResultColumn
        assert window.arch_controller.available_logics.get("Last Result") is LastResultColumn

        # Test creating release result columns
        release_mock = MagicMock()
        release_mock.name = "Rtest"
        window.arch_controller.create_result_columns_for_release(release_mock)

        active_col_types = [type(c) for c in window.arch_controller.active_columns]
        assert LastResultColumn in active_col_types
        assert ReleaseResultColumn in active_col_types

        rel_idx = -1
        for i, c in enumerate(window.arch_controller.active_columns):
            if isinstance(c, ReleaseResultColumn) and "Rtest" in c.name:
                rel_idx = i
                break
        assert rel_idx != -1

        cb = window.arch_controller.table.cellWidget(0, rel_idx)
        assert cb is not None
        cb.setCurrentText("Passed")

        last_idx = -1
        for i, c in enumerate(window.arch_controller.active_columns):
            if isinstance(c, LastResultColumn):
                last_idx = i
                break
        assert last_idx != -1
        item = window.arch_controller.table.item(0, last_idx)
        assert item is not None and item.text() == "Passed"

        config = window.arch_controller.active_config
        window.arch_controller.apply_new_columns(config)

        cb_after = window.arch_controller.table.cellWidget(0, rel_idx)
        assert cb_after is not None
        assert cb_after.currentText() == "Passed"

        # ---- Duplicate Last Result prevention ----
        print("Testing duplicate Last Result column prevention...")
        from PyQt6 import QtWidgets
        from Application_Logic.Logic_Column_Customizer import ColumnCustomizer

        customizer = ColumnCustomizer(
            current_config=[("Last Result", "Last Result", True)],
            logic_options=["Last Result", "Link", "Static Text"],
            parent=None
        )
        customizer.new_name_input.setText("Duplicate Last Result")
        customizer.type_combo.setCurrentText("Last Result")
        with patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
            customizer._add_custom_item()
            mock_warning.assert_called_once()
            assert customizer.active_list.count() == 1
        print("Duplicate Last Result prevention: PASSED")

        # ---- Link Last Result ----
        print("Testing Link Last Result feature...")
        from UI.Dialog_Release_Selection import ReleaseSelectionDialog

        window.current_project_file = proj_b_path

        dialog = ReleaseSelectionDialog(
            release_manager=window.arch_controller.release_manager,
            architecture_controller=window.arch_controller,
            parent=None
        )
        dialog.list_widget.setCurrentRow(0)

        with patch('PyQt6.QtWidgets.QMessageBox.question',
                   return_value=QtWidgets.QMessageBox.StandardButton.Yes), \
             patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            dialog.on_link_result()
            mock_info.assert_called_once()

        active_model = window.arch_controller.model_manager.get_active_model()
        assert active_model.data_cache.get("linked_release_column") == "Release_R12_Result"

        rel_idx_r12 = -1
        for i, c in enumerate(window.arch_controller.active_columns):
            if isinstance(c, ReleaseResultColumn) and c.name == "Release_R12_Result":
                rel_idx_r12 = i
                break
        assert rel_idx_r12 != -1

        cb_r12 = window.arch_controller.table.cellWidget(0, rel_idx_r12)
        assert cb_r12 is not None
        cb_r12.setCurrentText("Failed")
        item = window.arch_controller.table.item(0, last_idx)
        assert item is not None and item.text() == "Failed"

        window.arch_controller.flush_current_data_to_model()
        window.arch_controller.load_active_model_to_table()
        item = window.arch_controller.table.item(0, last_idx)
        assert item is not None and item.text() == "Failed"
        print("Link Last Result: PASSED")

        # ---- Column exclusion & sanitization ----
        print("Testing column customizer options exclusion...")
        logic_options = [
            key for key in window.arch_controller.available_logics.keys()
            if key not in ["InitColumn", "CyclicColumn", "Review Status", "PortStateColumn",
                           "ReleaseResultColumn", "Last Result"]
        ]
        assert "ReleaseResultColumn" not in logic_options
        assert "Last Result" not in logic_options
        print("Column customizer options exclusion: PASSED")

        print("Testing configuration sanitization...")
        invalid_config = [
            ("TC. ID", "Static Text", True),
            ("ManualReleaseCol", "ReleaseResultColumn", True),
            ("ManualLastResultCol", "Last Result", True),
            ("Release_Valid_Result", "ReleaseResultColumn", True),
            ("Last Result", "Last Result", True)
        ]
        sanitized = window.arch_controller.sanitize_column_config(invalid_config)
        assert sanitized[1][1] == "Static Text"
        assert sanitized[2][1] == "Static Text"
        assert sanitized[3][1] == "ReleaseResultColumn"
        assert sanitized[4][1] == "Last Result"
        print("Configuration sanitization: PASSED")

        print("Testing empty row prepopulation prevention...")
        tc_id_col = -1
        input_port_col = -1
        for i, col_obj in enumerate(window.arch_controller.active_columns):
            if col_obj.name == "TC. ID":
                tc_id_col = i
            elif col_obj.name == "Input Port":
                input_port_col = i

        window.arch_controller.table.item(0, tc_id_col).setText("")
        ip_item = window.arch_controller.table.item(0, input_port_col)
        if ip_item:
            ip_item.setText("")
        ip_widget = window.arch_controller.table.cellWidget(0, input_port_col)
        if ip_widget:
            ip_widget.setCurrentText("")

        for i, col_obj in enumerate(window.arch_controller.active_columns):
            if col_obj.name not in ["TC. ID", "Input Port"]:
                col_obj.on_change(window.arch_controller.table, 0, i, "Passed", window.arch_controller)

        for i, col_obj in enumerate(window.arch_controller.active_columns):
            if col_obj.name not in ["TC. ID", "Input Port"]:
                widget = window.arch_controller.table.cellWidget(0, i)
                item = window.arch_controller.table.item(0, i)
                assert widget is None
                assert item is None or item.text() == ""
        print("Empty row prepopulation prevention: PASSED")

        print("Project B loaded correctly and was isolated: PASSED")


if __name__ == "__main__":
    test_project_isolation()
    os._exit(0)

