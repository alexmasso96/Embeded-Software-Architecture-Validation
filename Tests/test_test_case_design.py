import sys
import os
import shutil
import json
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

    # Setup temp project path
    temp_proj = "test_tc_design_project.arch"
    if os.path.exists(temp_proj):
        shutil.rmtree(temp_proj)
    os.makedirs(temp_proj)

    # Instantiate ApplicationWindow (headless testing)
    window = ApplicationWindow()
    window.current_project_file = temp_proj

    # Grab controller
    controller = window.test_case_controller
    assert controller is not None, "TestCaseDesignController should be instantiated"

    # Rename check
    tab_index = window.ui.tabWidget.indexOf(controller.tab_widget)
    assert tab_index != -1
    assert window.ui.tabWidget.tabText(tab_index) == "Test Case Design"
    print("[TEST 1] Controller Initialization and UI setup: PASSED")

    # Mock architecture data
    # Let's populate row 0 of the architecture table
    arch_table = window.ui.Architecture_Table
    # Ensure columns are built
    arch_controller = window.arch_controller
    assert len(arch_controller.active_columns) > 0

    # Add a row and fill some values
    arch_table.setRowCount(1)
    # Row 0, TC ID (Col 0)
    item_id = QtWidgets.QTableWidgetItem("TC-001")
    arch_table.setItem(0, 0, item_id)
    
    # Row 0, Input Port (Col 1) - Search input
    item_port = QtWidgets.QTableWidgetItem("temp_status")
    arch_table.setItem(0, 1, item_port)
    # Row 0, Input Port (Match) (Col 2) - Match dropdown
    combo_port = QtWidgets.QComboBox()
    combo_port.addItem("p_i_temp_status (100%)")
    combo_port.setCurrentText("p_i_temp_status (100%)")
    arch_table.setCellWidget(0, 2, combo_port)

    # Row 0, Mapped Func (Col 5) - Search input
    item_func = QtWidgets.QTableWidgetItem("Read_Temp")
    arch_table.setItem(0, 5, item_func)
    # Row 0, Mapped Func (Match) (Col 6) - Match dropdown
    combo_func = QtWidgets.QComboBox()
    combo_func.addItem("Read_Temp_Status_Func (95%)")
    combo_func.setCurrentText("Read_Temp_Status_Func (95%)")
    arch_table.setCellWidget(0, 6, combo_func)

    # Row 1 - to test NO_ID fallback on non-empty rows
    # Leave TC. ID (Col 0) empty, set Input Port (Col 1) and Input Port (Match) (Col 2)
    arch_table.setRowCount(2)
    item_port_2 = QtWidgets.QTableWidgetItem("another_port")
    arch_table.setItem(1, 1, item_port_2)
    combo_port_2 = QtWidgets.QComboBox()
    combo_port_2.addItem("p_i_another_port (100%)")
    combo_port_2.setCurrentText("p_i_another_port (100%)")
    arch_table.setCellWidget(1, 2, combo_port_2)

    # Row 2 - to test Retired port state check (should be skipped)
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

    # Update columns in autocomplete completers
    controller.completer_title.update_columns()
    cols = controller.completer_title.string_model.stringList()
    assert "TC. ID" in cols
    assert "Input Port" in cols
    print("[TEST 2] Active Columns for Autocomplete: PASSED")

    # Set template text
    controller.txt_project_title.setText("[TC. ID]: Validation of [Input Port (Match)]")
    controller.txt_test_case_design.setPlainText(
        "Given:\n"
        "Verify port [Input Port (Match)] with function [Mapped Func (Match)].\n"
        "When.\n"
        "Some event happens.\n"
        "Then\n"
        "The state changes.\n"
    )

    # Force switch tab to "Test Case Design" to bypass performance guard
    window.ui.tabWidget.setCurrentWidget(controller.tab_widget)
    controller.update_preview()

    # Verify Preview rendering
    preview_markdown = controller.browser_preview.toMarkdown()
    print("Generated Live Preview Markdown:")
    print(preview_markdown)

    assert "TC-001" in preview_markdown, "Token [TC. ID] not replaced correctly"
    assert "p_i_temp_status" in preview_markdown, "Token [Input Port (Match)] not replaced correctly"
    assert "100%" not in preview_markdown, "Percentage not stripped correctly"
    assert "Read_Temp_Status_Func" in preview_markdown, "Token [Mapped Func (Match)] not replaced correctly"
    assert "95%" not in preview_markdown, "Percentage not stripped correctly"
    assert "Given" in preview_markdown, "Given not present"
    # Note: markdown output might add double asterisks for bolding. Depending on the Markdown library,
    # it might render as **Given** or in HTML as <strong>Given</strong> or similar. Let's make sure it's bolded.
    # In PyQt QTextBrowser.toMarkdown(), bold formatting is represented with ** or similar.
    # Let's assert it has bold formatting around Given, When, Then.
    assert "**Given**" in preview_markdown or "<b>Given</b>" in preview_markdown or "<strong>Given</strong>" in preview_markdown
    assert "**When**" in preview_markdown or "<b>When</b>" in preview_markdown or "<strong>When</strong>" in preview_markdown
    assert "**Then**" in preview_markdown or "<b>Then</b>" in preview_markdown or "<strong>Then</strong>" in preview_markdown
    print("[TEST 3] Real-time Dynamic Token Replacement & Formatting: PASSED")

    # Test Save/Load
    success, msg = ProjectSaver.save_project(window, window.current_project_file)
    assert success, f"Project save failed: {msg}"
    assert os.path.exists(os.path.join(temp_proj, "layout.json"))

    # Verify saving layout.json contains the template fields
    with open(os.path.join(temp_proj, "layout.json"), "r") as f:
        layout_data = json.load(f)
    assert "test_case_design" in layout_data
    assert layout_data["test_case_design"]["project_title"] == "[TC. ID]: Validation of [Input Port (Match)]"
    assert "Verify port [Input Port (Match)]" in layout_data["test_case_design"]["design_template"]
    print("[TEST 4] Template Save Persistence: PASSED")

    # Reset text fields, and load project to see if they get restored
    controller.txt_project_title.setText("")
    controller.txt_test_case_design.setPlainText("")
    controller.update_preview()
    assert controller.txt_project_title.text() == ""

    # Load project
    with patch('PyQt6.QtWidgets.QFileDialog.getExistingDirectory', return_value=temp_proj):
        window.load_project()
    
    assert controller.txt_project_title.text() == "[TC. ID]: Validation of [Input Port (Match)]"
    assert "Verify port [Input Port (Match)]" in controller.txt_test_case_design.toPlainText()
    print("[TEST 5] Template Load Restoration: PASSED")

    # Test Generation Menu and Output Files
    # Mock MessageBox to avoid blocking popups during generation
    with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
        controller.generate_test_cases(scope="current")
        assert mock_info.called

    output_dir = os.path.join(os.path.dirname(temp_proj), "Test Case Design")
    assert os.path.exists(output_dir), f"Directory {output_dir} does not exist!"
    
    files = os.listdir(output_dir)
    print("Files in Test Case Design output directory:", files)
    assert len(files) == 1
    assert files[0] == "Architecture_1_Test_Case_Design.md", "Filename must match model name (sanitized) followed by _Test_Case_Design.md"
    
    # Check the file name and contents
    gen_file_path = os.path.join(output_dir, files[0])
    with open(gen_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    print("Generated File Content:")
    print(content)
    assert "TC-001: Validation of p_i_temp_status" in content
    assert "NO_ID: Validation of p_i_another_port" in content, "Empty ID on non-empty row should fall back to 'NO_ID'"
    assert "retired_port" not in content, "Retired port should be skipped entirely"
    assert "100%" not in content
    assert "**Given**:" in content
    assert "**When**." in content
    assert "**Then**" in content
    assert "Verify port p_i_temp_status with function Read_Temp_Status_Func." in content
    print("[TEST 6] File Generation (Scope: Current): PASSED")

    # Test Idempotency (smart overwrite)
    # Modify template, generate again, verify it overwrites the existing file without duplicate
    controller.txt_project_title.setText("[TC. ID]: UPDATED TITLE")
    with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
        controller.generate_test_cases(scope="current")
    
    files_after = os.listdir(output_dir)
    print("Files after second generation:", files_after)
    assert len(files_after) == 1, "Duplicate file created instead of overwriting!"
    assert files_after[0] == "Architecture_1_Test_Case_Design.md", "Sanitized model name filename should be preserved"
    
    with open(os.path.join(output_dir, files_after[0]), "r", encoding="utf-8") as f:
        updated_content = f.read()
    assert "TC-001: UPDATED TITLE" in updated_content
    assert "NO_ID: UPDATED TITLE" in updated_content, "Empty ID should fall back to 'NO_ID' in updated template"
    print("[TEST 7] Smart Overwrite / Idempotency: PASSED")

    # Clean up
    shutil.rmtree(temp_proj)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    print("\nALL TEST CASE DESIGN FEATURE TESTS PASSED ✓")

if __name__ == "__main__":
    test_test_case_design_flow()
