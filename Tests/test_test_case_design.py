import sys
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMainWindow, QLineEdit, QPlainTextEdit, QTextBrowser
from PyQt6 import QtWidgets, QtCore, QtGui

# Setup path
sys.path.append(os.path.abspath("src"))

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)

import UI
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Application_Logic.Logic_Architecture_Table import ArchitectureTabController
from Application_Logic.Logic_TestCase_Design import TestCaseDesignController
from main import ApplicationWindow


def test_test_case_design_flow():
    print("=" * 70)
    print("TESTING TEST CASE DESIGN FEATURE FLOW")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp:
        # .arch is a file, not a directory
        temp_proj = os.path.join(tmp, "tc_design_project.arch")

        window = ApplicationWindow()
        window.current_project_file = temp_proj

        controller = window.test_case_controller
        assert controller is not None

        tab_index = window.ui.tabWidget.indexOf(controller.tab_widget)
        assert tab_index != -1
        assert window.ui.tabWidget.tabText(tab_index) == "Test Case Design"
        print("[TEST 1] Controller Initialization and UI setup: PASSED")

        arch_table = window.ui.Architecture_Table
        arch_controller = window.arch_controller
        assert len(arch_controller.active_columns) > 0

        # Add a row and fill some values
        arch_table.setRowCount(1)
        arch_table.setItem(0, 0, QtWidgets.QTableWidgetItem("TC-001"))

        item_port = QtWidgets.QTableWidgetItem("temp_status")
        arch_table.setItem(0, 1, item_port)
        combo_port = QtWidgets.QComboBox()
        combo_port.addItem("p_i_temp_status (100%)")
        combo_port.setCurrentText("p_i_temp_status (100%)")
        arch_table.setCellWidget(0, 2, combo_port)

        item_func = QtWidgets.QTableWidgetItem("Read_Temp")
        arch_table.setItem(0, 5, item_func)
        combo_func = QtWidgets.QComboBox()
        combo_func.addItem("Read_Temp_Status_Func (95%)")
        combo_func.setCurrentText("Read_Temp_Status_Func (95%)")
        arch_table.setCellWidget(0, 6, combo_func)

        # Row 1: empty TC. ID fallback to NO_ID
        arch_table.setRowCount(2)
        item_port_2 = QtWidgets.QTableWidgetItem("another_port")
        arch_table.setItem(1, 1, item_port_2)
        combo_port_2 = QtWidgets.QComboBox()
        combo_port_2.addItem("p_i_another_port (100%)")
        combo_port_2.setCurrentText("p_i_another_port (100%)")
        arch_table.setCellWidget(1, 2, combo_port_2)

        # Row 2: Retired port state — should be skipped
        arch_table.setRowCount(3)
        item_port_3 = QtWidgets.QTableWidgetItem("retired_port")
        arch_table.setItem(2, 1, item_port_3)
        combo_port_3 = QtWidgets.QComboBox()
        combo_port_3.addItem("p_i_retired_port (100%)")
        combo_port_3.setCurrentText("p_i_retired_port (100%)")
        arch_table.setCellWidget(2, 2, combo_port_3)
        combo_state = QtWidgets.QComboBox()
        combo_state.addItem("Retired")
        combo_state.setCurrentText("Retired")
        arch_table.setCellWidget(2, 12, combo_state)

        controller.completer_title.update_columns()
        cols = controller.completer_title.string_model.stringList()
        assert "TC. ID" in cols
        assert "Input Port" in cols
        print("[TEST 2] Active Columns for Autocomplete: PASSED")

        controller.txt_project_title.setText("[TC. ID]: Validation of [Input Port (Match)]")
        controller.txt_test_case_design.setPlainText(
            "Given:\n"
            "Verify port [Input Port (Match)] with function [Mapped Func (Match)].\n"
            "When.\n"
            "Some event happens.\n"
            "Then\n"
            "The state changes.\n"
        )

        window.ui.tabWidget.setCurrentWidget(controller.tab_widget)
        controller.update_preview()

        preview_markdown = controller.browser_preview.toMarkdown()
        print("Generated Live Preview Markdown:")
        print(preview_markdown)

        assert "TC-001" in preview_markdown
        assert "p_i_temp_status" in preview_markdown
        assert "100%" not in preview_markdown
        assert "Read_Temp_Status_Func" in preview_markdown
        assert "95%" not in preview_markdown
        # Given/When/Then are rendered verbatim (no special formatting).
        assert "Given" in preview_markdown
        assert "When" in preview_markdown
        assert "Then" in preview_markdown
        print("[TEST 3] Real-time Dynamic Token Replacement: PASSED")

        # Test Save
        success, msg = ProjectSaver.save_project(window, temp_proj)
        assert success, f"Project save failed: {msg}"
        assert os.path.exists(temp_proj), "DB file should exist after save"

        # Verify test case data stored in DB
        from Application_Logic.Logic_Database import ProjectDatabase
        verify_db = ProjectDatabase()
        verify_db.open(temp_proj)
        tc_data = verify_db.get_test_case_design()
        verify_db.close()
        assert tc_data is not None
        assert tc_data.get("project_title") == "[TC. ID]: Validation of [Input Port (Match)]"
        assert "Verify port [Input Port (Match)]" in tc_data.get("design_template", "")
        print("[TEST 4] Template Save Persistence: PASSED")

        # Reset text fields, then reload project to see if they get restored
        controller.txt_project_title.setText("")
        controller.txt_test_case_design.setPlainText("")
        controller.update_preview()
        assert controller.txt_project_title.text() == ""

        # Load project back using DB
        success, msg = ProjectSaver.load_project(window, temp_proj)
        assert success, f"Load project failed: {msg}"

        assert controller.txt_project_title.text() == "[TC. ID]: Validation of [Input Port (Match)]"
        assert "Verify port [Input Port (Match)]" in controller.txt_test_case_design.toPlainText()
        print("[TEST 5] Template Load Restoration: PASSED")

        # Test Generation
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            controller.generate_test_cases(scope="current")
            assert mock_info.called

        output_dir = os.path.join(tmp, "Test Case Design")
        assert os.path.exists(output_dir), f"Directory {output_dir} does not exist!"

        files = os.listdir(output_dir)
        print("Files in Test Case Design output directory:", files)
        assert "Architecture_1_Test_Case_Design.md" in files

        gen_file_path = os.path.join(output_dir, "Architecture_1_Test_Case_Design.md")
        with open(gen_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        print("Generated File Content:")
        print(content)
        assert "TC-001: Validation of p_i_temp_status" in content
        assert "NO_ID: Validation of p_i_another_port" in content
        assert "retired_port" not in content
        assert "100%" not in content
        assert "Given:" in content
        assert "When." in content
        assert "Then" in content
        assert "Verify port p_i_temp_status with function Read_Temp_Status_Func." in content
        print("[TEST 6] File Generation (Scope: Current): PASSED")

        # Test Idempotency (smart overwrite)
        controller.txt_project_title.setText("[TC. ID]: UPDATED TITLE")
        with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
            controller.generate_test_cases(scope="current")

        files_after = os.listdir(output_dir)
        assert "Architecture_1_Test_Case_Design.md" in files_after, "Expected output file not found!"

        with open(os.path.join(output_dir, "Architecture_1_Test_Case_Design.md"), "r", encoding="utf-8") as f:
            updated_content = f.read()
        assert "TC-001: UPDATED TITLE" in updated_content
        assert "NO_ID: UPDATED TITLE" in updated_content
        print("[TEST 7] Smart Overwrite / Idempotency: PASSED")

    print("\nALL TEST CASE DESIGN FEATURE TESTS PASSED ✓")


if __name__ == "__main__":
    test_test_case_design_flow()
