import sys
import os
import shutil
import json
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import QtWidgets, QtCore

# Setup path
sys.path.append(os.path.abspath("src"))

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)

import UI
from Application_Logic.Logic_TestCase_Design import (
    TestCaseDesignController,
    tokenize_partial_condition,
    tokenize_condition,
    get_condition_suggestions_and_prefix
)
from main import ApplicationWindow

def test_tokenizers():
    print("Testing tokenizers...")
    
    # tokenize_partial_condition
    tokens = tokenize_partial_condition("#if [Input Port] contains 'init'")
    # Note: condition_part begins after #if
    tokens = tokenize_partial_condition(" [Input Port] contains 'init'")
    assert len(tokens) == 3
    assert tokens[0] == ('COLUMN', '[Input Port]')
    assert tokens[1] == ('OPERATOR', 'contains')
    assert tokens[2] == ('VALUE', "'init'")

    # Incomplete inputs
    tokens = tokenize_partial_condition(" [Input Port")
    assert len(tokens) == 1
    assert tokens[0] == ('INCOMPLETE_COLUMN', '[Input Port')

    tokens = tokenize_partial_condition(" [Input Port] contains 'in")
    assert len(tokens) == 3
    assert tokens[2] == ('INCOMPLETE_VALUE', "'in")

    # tokenize_condition
    tokens = tokenize_condition("[Col1] is equal '1' AND [Col2] contains '2'")
    assert len(tokens) == 7
    assert tokens[0] == ('COLUMN', '[Col1]')
    assert tokens[1] == ('OPERATOR', 'is equal')
    assert tokens[2] == ('VALUE', "'1'")
    assert tokens[3] == ('LOGICAL', 'AND')
    assert tokens[4] == ('COLUMN', '[Col2]')
    assert tokens[5] == ('OPERATOR', 'contains')
    assert tokens[6] == ('VALUE', "'2'")

    # Test stray brackets, braces, or special characters that previously caused infinite loops
    tokens_stray_cond = tokenize_condition("]")
    assert len(tokens_stray_cond) == 1
    assert tokens_stray_cond[0] == ('VALUE', ']')

    tokens_stray_part = tokenize_partial_condition("}")
    assert len(tokens_stray_part) == 1
    assert tokens_stray_part[0] == ('WORD', '}')

    print("-> Tokenizers: PASSED")

def test_suggestions():
    print("Testing autocomplete suggestions...")
    active_cols = ["ColA", "ColB"]
    get_uniq = lambda col: ["'val1'", "'val2'"] if col == "ColA" else []

    # 1. Start with '#'
    suggs, prefix = get_condition_suggestions_and_prefix("#", active_cols, get_uniq)
    assert suggs == ['#if']
    assert prefix == '#'

    # 2. Inside condition, nothing typed yet
    suggs, prefix = get_condition_suggestions_and_prefix("#if ", active_cols, get_uniq)
    assert '[ColA]' in suggs
    assert '[ColB]' in suggs
    assert prefix == ""

    # 3. Partial column typed
    suggs, prefix = get_condition_suggestions_and_prefix("#if [Col", active_cols, get_uniq)
    assert '[ColA]' in suggs
    assert prefix == '[Col'

    # 4. Column complete, expecting operator
    suggs, prefix = get_condition_suggestions_and_prefix("#if [ColA] ", active_cols, get_uniq)
    assert 'contains' in suggs
    assert 'is equal' in suggs
    assert prefix == ""

    # 5. Column complete, partial operator typed
    suggs, prefix = get_condition_suggestions_and_prefix("#if [ColA] con", active_cols, get_uniq)
    assert 'contains' in suggs
    assert prefix == 'con'

    # 6. Operator complete, expecting value
    suggs, prefix = get_condition_suggestions_and_prefix("#if [ColA] contains ", active_cols, get_uniq)
    assert "'val1'" in suggs
    assert "'cyclic'" in suggs
    assert prefix == ""

    # 7. Operator complete, partial value typed
    suggs, prefix = get_condition_suggestions_and_prefix("#if [ColA] contains 'val", active_cols, get_uniq)
    assert "'val1'" in suggs
    assert prefix == "'val"

    # 8. Value complete, expecting logical or brace
    suggs, prefix = get_condition_suggestions_and_prefix("#if [ColA] contains 'val1' ", active_cols, get_uniq)
    assert 'AND' in suggs
    assert 'OR' in suggs
    assert '{' in suggs
    assert prefix == ""

    # 9. Logical complete, expecting new column
    suggs, prefix = get_condition_suggestions_and_prefix("#if [ColA] contains 'val1' AND ", active_cols, get_uniq)
    assert '[ColB]' in suggs
    assert prefix == ""

    print("-> Suggestions: PASSED")

def test_condition_evaluation():
    print("Testing condition logic & operator rules...")
    # Headless setup
    window = ApplicationWindow()
    controller = window.test_case_controller

    row_data = {
        "Input Port": "p_i_temp_status (100%)",
        "Mapped Func": "Read_Temp_Status_Func (95%)",
        "ColVal": "cyclic",
        "Numeric": "42"
    }

    # test normalize_value
    assert controller.normalize_value("p_i_temp_status (100%)") == "p_i_temp_status"
    assert controller.normalize_value("' cyclic '") == "cyclic"
    assert controller.normalize_value('"CYCLIC"') == "cyclic"

    # test evaluate_single_condition
    assert controller.evaluate_single_condition("[Input Port]", "contains", "temp", row_data) is True
    assert controller.evaluate_single_condition("[Input Port]", "does not contain", "cyclic", row_data) is True
    assert controller.evaluate_single_condition("[Input Port]", "is equal", "'p_i_temp_status'", row_data) is True
    assert controller.evaluate_single_condition("[Input Port]", "is not equal", "'other'", row_data) is True

    # test non-existent/missing columns gracefully defaulting without crash
    assert controller.evaluate_single_condition("[NonExistent]", "is equal", "'something'", row_data) is False
    assert controller.evaluate_single_condition("[NonExistent]", "does not contain", "'something'", row_data) is True

    # test evaluate_condition (complex logic)
    # basic AND
    assert controller.evaluate_condition("[Input Port] contains 'temp' AND [ColVal] is equal 'cyclic'", row_data) is True
    assert controller.evaluate_condition("[Input Port] contains 'temp' AND [ColVal] is equal 'other'", row_data) is False

    # basic OR
    assert controller.evaluate_condition("[Input Port] contains 'other' OR [ColVal] is equal 'cyclic'", row_data) is True
    assert controller.evaluate_condition("[Input Port] contains 'other' OR [ColVal] is equal 'other'", row_data) is False

    # precedence: AND before OR
    # Let's test with real column checks
    # [Input Port] contains 'temp' (True) OR [ColVal] is equal 'other' (False) AND [Numeric] is equal '0' (False)
    # If AND evaluates first: False AND False -> False. Then True OR False -> True.
    # If left-to-right: True OR False -> True. Then True AND False -> False.
    # Precedence says AND-before-OR, so result must be True.
    expr = "[Input Port] contains 'temp' OR [ColVal] is equal 'other' AND [Numeric] is equal '0'"
    assert controller.evaluate_condition(expr, row_data) is True

    # False AND False OR True -> True
    expr2 = "[Input Port] contains 'other' AND [ColVal] is equal 'other' OR [Numeric] is equal '42'"
    assert controller.evaluate_condition(expr2, row_data) is True

    # False OR True AND True -> True
    expr3 = "[Input Port] contains 'other' OR [ColVal] is equal 'cyclic' AND [Numeric] is equal '42'"
    assert controller.evaluate_condition(expr3, row_data) is True

    print("-> Condition Evaluation: PASSED")

def test_conditional_blocks_processing():
    print("Testing conditional blocks processing & newlines cleanup...")
    window = ApplicationWindow()
    controller = window.test_case_controller

    row_data = {
        "Input Port": "p_i_temp",
        "Mapped Func": "Read_Temp",
        "State": "Init"
    }

    # 1. Simple block - True condition
    template_true = (
        "Before\n"
        "#if [Input Port] is equal 'p_i_temp' {\n"
        "    Inside block!\n"
        "}\n"
        "After"
    )
    res = controller.process_conditional_blocks(template_true, row_data)
    # Expect: "Before\n    Inside block!\nAfter"
    assert "Inside block!" in res
    assert "#if" not in res
    assert "{" not in res
    assert "}" not in res

    # 2. Simple block - False condition
    template_false = (
        "Before\n"
        "#if [Input Port] is equal 'other' {\n"
        "    Inside block!\n"
        "}\n"
        "After"
    )
    res = controller.process_conditional_blocks(template_false, row_data)
    # Expect: "Before\nAfter"
    assert "Inside block!" not in res
    assert "#if" not in res
    # verify we don't have multiple consecutive newlines replacing the deleted block
    assert "Before\nAfter" in res

    # 3. Nested conditional blocks
    template_nested = (
        "Start\n"
        "#if [Input Port] is equal 'p_i_temp' {\n"
        "    Outer True\n"
        "    #if [State] is equal 'Init' {\n"
        "        Inner True\n"
        "    }\n"
        "    #if [State] is equal 'Cyclic' {\n"
        "        Inner False\n"
        "    }\n"
        "}\n"
        "End"
    )
    res = controller.process_conditional_blocks(template_nested, row_data)
    assert "Outer True" in res
    assert "Inner True" in res
    assert "Inner False" not in res
    assert "#if" not in res

    print("-> Block Processing: PASSED")

def test_auto_numbering():
    print("Testing Given/When/Then auto-numbering and formatting...")
    window = ApplicationWindow()
    controller = window.test_case_controller

    input_text = (
        "Given:\n"
        "Verify initialization\n"
        "\n"
        "Verify parameters\n"
        "When:\n"
        "Some trigger occurs\n"
        "- A bullet point to skip\n"
        "Another trigger\n"
        "Then.\n"
        "Output is updated\n"
        "1. Existing number should be preserved\n"
        "Another output update"
    )

    res = controller.apply_auto_numbering(input_text)
    lines = res.splitlines()

    # check bolding helper first
    res_bold = controller.format_given_when_then(input_text)
    assert "**Given**:" in res_bold
    assert "**When**:" in res_bold
    assert "**Then**." in res_bold

    # check numbering output
    # Given section (starts after Given:)
    # "Verify initialization" -> "1. Verify initialization"
    # "" -> preserved as ""
    # "Verify parameters" -> "2. Verify parameters"
    # When section (starts after When:)
    # "Some trigger occurs" -> "1. Some trigger occurs"
    # "- A bullet point to skip" -> preserved
    # "Another trigger" -> "2. Another trigger"
    # Then section (starts after Then.)
    # "Output is updated" -> "1. Output is updated"
    # "1. Existing number..." -> preserved
    # "Another output update" -> "2. Another output update"
    
    assert "1. Verify initialization" in lines
    assert "2. Verify parameters" in lines
    assert "1. Some trigger occurs" in lines
    assert "- A bullet point to skip" in lines
    assert "2. Another trigger" in lines
    assert "1. Output is updated" in lines
    assert "1. Existing number should be preserved" in lines
    assert "2. Another output update" in lines

    # Test preserving indentation
    indented_input = (
        "Given:\n"
        "    Verify something\n"
    )
    res_ind = controller.apply_auto_numbering(indented_input)
    assert "    1. Verify something" in res_ind.splitlines()

    print("-> Auto Numbering: PASSED")

def test_rendering_integration():
    print("Testing rendering integration (Live Preview)...")
    temp_proj = "test_tc_design_conditional_project.arch"
    if os.path.exists(temp_proj):
        shutil.rmtree(temp_proj)
    os.makedirs(temp_proj)

    window = ApplicationWindow()
    window.current_project_file = temp_proj
    controller = window.test_case_controller

    # Populate architecture table
    arch_table = window.ui.Architecture_Table
    arch_table.setRowCount(1)
    
    # Col 0: TC. ID
    arch_table.setItem(0, 0, QtWidgets.QTableWidgetItem("TC-COND-001"))
    # Col 1: Input Port (Search)
    arch_table.setItem(0, 1, QtWidgets.QTableWidgetItem("temp"))
    # Col 2: Input Port (Match)
    combo_port = QtWidgets.QComboBox()
    combo_port.addItem("p_i_temp (100%)")
    combo_port.setCurrentText("p_i_temp (100%)")
    arch_table.setCellWidget(0, 2, combo_port)
    # Col 12: Port State
    combo_state = QtWidgets.QComboBox()
    combo_state.addItem("Released")
    combo_state.setCurrentText("Released")
    arch_table.setCellWidget(0, 12, combo_state)

    # Set template containing conditions and Given/When/Then sections
    controller.txt_project_title.setText("[TC. ID]: Validation")
    controller.txt_test_case_design.setPlainText(
        "## Description\n"
        "Port name is [Input Port (Match)].\n"
        "\n"
        "#if [Input Port (Match)] contains 'temp' {\n"
        "Given:\n"
        "Temp reading is validated\n"
        "When:\n"
        "Temp changes rapidly\n"
        "Then:\n"
        "Error is flagged\n"
        "}\n"
        "\n"
        "#if [Input Port (Match)] contains 'speed' {\n"
        "Given:\n"
        "Speed reading is validated\n"
        "}\n"
    )

    window.ui.tabWidget.setCurrentWidget(controller.tab_widget)
    controller.update_preview()

    preview = controller.browser_preview.toMarkdown()
    print("Integration Preview Markdown:")
    print(preview)

    # Since Input Port is 'p_i_temp':
    # 'temp' condition should be True -> Given/When/Then for temp should be present and numbered.
    # 'speed' condition should be False -> Given/When/Then for speed should be omitted.
    assert "Temp reading is validated" in preview
    assert "1. Temp reading is validated" in preview or "1.  Temp reading is validated" in preview
    assert "Speed reading is validated" not in preview

    # Verify generate_test_cases file output uses the correct pipeline
    with patch('PyQt6.QtWidgets.QMessageBox.information') as mock_info:
        controller.generate_test_cases(scope="current")
        assert mock_info.called

    output_dir = os.path.join(os.path.dirname(temp_proj), "Test Case Design")
    files = os.listdir(output_dir)
    assert len(files) == 1
    
    with open(os.path.join(output_dir, files[0]), "r", encoding="utf-8") as f:
        file_content = f.read()

    print("Integration Generated File Content:")
    print(file_content)
    assert "Temp reading is validated" in file_content
    assert "1. Temp reading is validated" in file_content
    assert "Speed reading is validated" not in file_content

    # Clean up
    shutil.rmtree(temp_proj)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    print("-> Rendering Integration: PASSED")

def test_live_preview_row_selection():
    print("Testing live preview row selection logic...")
    temp_proj = "test_tc_design_row_selection_project.arch"
    if os.path.exists(temp_proj):
        shutil.rmtree(temp_proj)
    os.makedirs(temp_proj)

    window = ApplicationWindow()
    window.current_project_file = temp_proj
    controller = window.test_case_controller
    arch_table = window.ui.Architecture_Table

    # Set row count to 3
    arch_table.setRowCount(3)

    # Row 0: Empty row
    for col_idx in range(arch_table.columnCount()):
        arch_table.setItem(0, col_idx, QtWidgets.QTableWidgetItem(""))
    
    # Row 1: Retired row
    arch_table.setItem(1, 0, QtWidgets.QTableWidgetItem("TC-RETIRED"))
    combo_port_1 = QtWidgets.QComboBox()
    combo_port_1.addItem("p_i_speed (100%)")
    combo_port_1.setCurrentText("p_i_speed (100%)")
    arch_table.setCellWidget(1, 2, combo_port_1)
    combo_state_1 = QtWidgets.QComboBox()
    combo_state_1.addItem("Retired")
    combo_state_1.setCurrentText("Retired")
    arch_table.setCellWidget(1, 12, combo_state_1)

    # Row 2: Valid row
    arch_table.setItem(2, 0, QtWidgets.QTableWidgetItem("TC-VALID"))
    combo_port_2 = QtWidgets.QComboBox()
    combo_port_2.addItem("p_i_valid (100%)")
    combo_port_2.setCurrentText("p_i_valid (100%)")
    arch_table.setCellWidget(2, 2, combo_port_2)
    combo_state_2 = QtWidgets.QComboBox()
    combo_state_2.addItem("Released")
    combo_state_2.setCurrentText("Released")
    arch_table.setCellWidget(2, 12, combo_state_2)

    # Set template
    controller.txt_project_title.setText("[TC. ID]: Validation")
    controller.txt_test_case_design.setPlainText("Port name: [Input Port (Match)]")

    window.ui.tabWidget.setCurrentWidget(controller.tab_widget)
    controller.update_preview()

    # The preview should skip Row 0 (empty) and Row 1 (retired) and bind Row 2 (valid)
    preview = controller.browser_preview.toMarkdown()
    assert "TC-VALID: Validation" in preview
    assert "Port name: p_i_valid" in preview
    
    # Now let's test fallback warning for empty table (only empty rows)
    arch_table.setRowCount(1)
    for col_idx in range(arch_table.columnCount()):
        arch_table.setItem(0, col_idx, QtWidgets.QTableWidgetItem(""))
    
    controller.update_preview()
    # It should display the empty warning
    preview_html = controller.browser_preview.toHtml()
    assert "Row 1 is empty" in preview_html

    # Now let's test fallback warning for retired table (only retired rows)
    arch_table.setRowCount(1)
    arch_table.setItem(0, 0, QtWidgets.QTableWidgetItem("TC-RETIRED-ONLY"))
    combo_port_r = QtWidgets.QComboBox()
    combo_port_r.addItem("p_r (100%)")
    combo_port_r.setCurrentText("p_r (100%)")
    arch_table.setCellWidget(0, 2, combo_port_r)
    combo_state_r = QtWidgets.QComboBox()
    combo_state_r.addItem("Retired")
    combo_state_r.setCurrentText("Retired")
    arch_table.setCellWidget(0, 12, combo_state_r)

    controller.update_preview()
    preview_html = controller.browser_preview.toHtml()
    assert "Retired" in preview_html

    # Clean up
    shutil.rmtree(temp_proj)
    print("-> Live Preview Row Selection: PASSED")

def test_preview_navigation_buttons():
    print("Testing preview navigation buttons (Previous/Next) and status...")
    temp_proj = "test_tc_design_nav_project.arch"
    if os.path.exists(temp_proj):
        shutil.rmtree(temp_proj)
    os.makedirs(temp_proj)

    window = ApplicationWindow()
    window.current_project_file = temp_proj
    controller = window.test_case_controller
    arch_table = window.ui.Architecture_Table

    # Test Case 1: Empty Table (0 rows)
    arch_table.setRowCount(0)
    window.ui.tabWidget.setCurrentWidget(controller.tab_widget)
    controller.update_preview()
    
    assert controller.preview_row_index == -1
    assert not controller.btn_prev_preview.isEnabled()
    assert not controller.btn_next_preview.isEnabled()
    assert controller.lbl_preview_status.text() == "No rows"

    # Test Case 2: Multi-row navigation (3 rows)
    arch_table.blockSignals(True)
    arch_table.setRowCount(3)
    
    # Setup row 0: TC-001, port 0, Released
    arch_table.setItem(0, 0, QtWidgets.QTableWidgetItem("TC-001"))
    combo_port_0 = QtWidgets.QComboBox()
    combo_port_0.addItem("p_i_0 (100%)")
    combo_port_0.setCurrentText("p_i_0 (100%)")
    arch_table.setCellWidget(0, 2, combo_port_0)
    combo_state_0 = QtWidgets.QComboBox()
    combo_state_0.addItem("Released")
    combo_state_0.setCurrentText("Released")
    arch_table.setCellWidget(0, 12, combo_state_0)

    # Setup row 1: TC-002, port 1, Released
    arch_table.setItem(1, 0, QtWidgets.QTableWidgetItem("TC-002"))
    combo_port_1 = QtWidgets.QComboBox()
    combo_port_1.addItem("p_i_1 (100%)")
    combo_port_1.setCurrentText("p_i_1 (100%)")
    arch_table.setCellWidget(1, 2, combo_port_1)
    combo_state_1 = QtWidgets.QComboBox()
    combo_state_1.addItem("Released")
    combo_state_1.setCurrentText("Released")
    arch_table.setCellWidget(1, 12, combo_state_1)

    # Setup row 2: TC-003, port 2, Released
    arch_table.setItem(2, 0, QtWidgets.QTableWidgetItem("TC-003"))
    combo_port_2 = QtWidgets.QComboBox()
    combo_port_2.addItem("p_i_2 (100%)")
    combo_port_2.setCurrentText("p_i_2 (100%)")
    arch_table.setCellWidget(2, 2, combo_port_2)
    combo_state_2 = QtWidgets.QComboBox()
    combo_state_2.addItem("Released")
    combo_state_2.setCurrentText("Released")
    arch_table.setCellWidget(2, 12, combo_state_2)
    arch_table.blockSignals(False)

    controller.txt_project_title.setText("[TC. ID]: Validation")
    controller.txt_test_case_design.setPlainText("Port name: [Input Port (Match)]")

    # Update preview - should default to first valid row (row 0)
    controller.update_preview()
    assert controller.preview_row_index == 0
    assert not controller.btn_prev_preview.isEnabled()  # Boundary: disabled on first row
    assert controller.btn_next_preview.isEnabled()
    assert controller.lbl_preview_status.text() == "Row 1 of 3"
    
    preview = controller.browser_preview.toMarkdown()
    assert "TC-001: Validation" in preview
    assert "Port name: p_i_0" in preview

    # Click Next
    controller.btn_next_preview.click()
    assert controller.preview_row_index == 1
    assert controller.btn_prev_preview.isEnabled()
    assert controller.btn_next_preview.isEnabled()
    assert controller.lbl_preview_status.text() == "Row 2 of 3"
    
    preview = controller.browser_preview.toMarkdown()
    assert "TC-002: Validation" in preview
    assert "Port name: p_i_1" in preview

    # Click Next again
    controller.btn_next_preview.click()
    assert controller.preview_row_index == 2
    assert controller.btn_prev_preview.isEnabled()
    assert not controller.btn_next_preview.isEnabled()  # Boundary: disabled on last row
    assert controller.lbl_preview_status.text() == "Row 3 of 3"
    
    preview = controller.browser_preview.toMarkdown()
    assert "TC-003: Validation" in preview
    assert "Port name: p_i_2" in preview

    # Click Previous
    controller.btn_prev_preview.click()
    assert controller.preview_row_index == 1
    assert controller.btn_prev_preview.isEnabled()
    assert controller.btn_next_preview.isEnabled()
    assert controller.lbl_preview_status.text() == "Row 2 of 3"
    
    preview = controller.browser_preview.toMarkdown()
    assert "TC-002: Validation" in preview
    assert "Port name: p_i_1" in preview

    # Test active model switch resets preview index
    controller.last_previewed_model = "dummy_model"
    controller.update_preview()
    assert controller.preview_row_index == 0
    assert controller.lbl_preview_status.text() == "Row 1 of 3"

    # Clean up
    shutil.rmtree(temp_proj)
    print("-> Preview Navigation Buttons: PASSED")

def run_all_tests():
    print("=" * 70)
    print("RUNNING CONDITIONAL SYNTAX & AUTO-NUMBERING TESTS")
    print("=" * 70)
    test_tokenizers()
    test_suggestions()
    test_condition_evaluation()
    test_conditional_blocks_processing()
    test_auto_numbering()
    test_rendering_integration()
    test_live_preview_row_selection()
    test_preview_navigation_buttons()
    print("=" * 70)
    print("ALL CONDITIONAL TESTS PASSED ✓")
    print("=" * 70)

if __name__ == "__main__":
    run_all_tests()
