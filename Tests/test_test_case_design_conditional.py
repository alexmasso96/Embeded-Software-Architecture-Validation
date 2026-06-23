"""
Logic-layer tests for Test Case Design condition syntax: tokenizers,
autocomplete suggestions, condition evaluation, the ``[port] multiple``
operation-count predicate, and conditional-block processing.

These exercise the pure functions in ``Logic_TestCase_Design`` directly — no Qt.
(The former Qt-widget integration tests — live preview rendering, row selection,
Previous/Next navigation — were dropped with the PyQt UI; that path is now the
React frontend over the backend ``/api/testdesign/preview`` endpoint.)
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_TestCase_Design import (
    tokenize_partial_condition,
    tokenize_condition,
    get_condition_suggestions_and_prefix,
    normalize_value,
    evaluate_single_condition,
    evaluate_condition,
    process_conditional_blocks,
)


def test_tokenizers():
    # tokenize_partial_condition — condition_part begins after #if
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

    # Stray brackets/braces that previously caused infinite loops
    tokens_stray_cond = tokenize_condition("]")
    assert len(tokens_stray_cond) == 1
    assert tokens_stray_cond[0] == ('VALUE', ']')

    tokens_stray_part = tokenize_partial_condition("}")
    assert len(tokens_stray_part) == 1
    assert tokens_stray_part[0] == ('WORD', '}')


def test_suggestions():
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


def test_condition_evaluation():
    row_data = {
        "Input Port": "p_i_temp_status (100%)",
        "Mapped Func": "Read_Temp_Status_Func (95%)",
        "ColVal": "cyclic",
        "Numeric": "42",
    }

    # normalize_value
    assert normalize_value("p_i_temp_status (100%)") == "p_i_temp_status"
    assert normalize_value("' cyclic '") == "cyclic"
    assert normalize_value('"CYCLIC"') == "cyclic"

    # evaluate_single_condition
    assert evaluate_single_condition("[Input Port]", "contains", "temp", row_data) is True
    assert evaluate_single_condition("[Input Port]", "does not contain", "cyclic", row_data) is True
    assert evaluate_single_condition("[Input Port]", "is equal", "'p_i_temp_status'", row_data) is True
    assert evaluate_single_condition("[Input Port]", "is not equal", "'other'", row_data) is True

    # Missing columns default gracefully without crashing
    assert evaluate_single_condition("[NonExistent]", "is equal", "'something'", row_data) is False
    assert evaluate_single_condition("[NonExistent]", "does not contain", "'something'", row_data) is True

    # evaluate_condition — basic AND
    assert evaluate_condition("[Input Port] contains 'temp' AND [ColVal] is equal 'cyclic'", row_data) is True
    assert evaluate_condition("[Input Port] contains 'temp' AND [ColVal] is equal 'other'", row_data) is False

    # basic OR
    assert evaluate_condition("[Input Port] contains 'other' OR [ColVal] is equal 'cyclic'", row_data) is True
    assert evaluate_condition("[Input Port] contains 'other' OR [ColVal] is equal 'other'", row_data) is False

    # precedence: AND before OR (must be True)
    expr = "[Input Port] contains 'temp' OR [ColVal] is equal 'other' AND [Numeric] is equal '0'"
    assert evaluate_condition(expr, row_data) is True

    # False AND False OR True -> True
    expr2 = "[Input Port] contains 'other' AND [ColVal] is equal 'other' OR [Numeric] is equal '42'"
    assert evaluate_condition(expr2, row_data) is True

    # False OR True AND True -> True
    expr3 = "[Input Port] contains 'other' OR [ColVal] is equal 'cyclic' AND [Numeric] is equal '42'"
    assert evaluate_condition(expr3, row_data) is True


def test_conditional_blocks_processing():
    row_data = {
        "Input Port": "p_i_temp",
        "Mapped Func": "Read_Temp",
        "State": "Init",
    }

    # 1. Simple block — True condition
    template_true = (
        "Before\n"
        "#if [Input Port] is equal 'p_i_temp' {\n"
        "    Inside block!\n"
        "}\n"
        "After"
    )
    res = process_conditional_blocks(template_true, row_data)
    assert "Inside block!" in res
    assert "#if" not in res
    assert "{" not in res
    assert "}" not in res

    # 2. Simple block — False condition
    template_false = (
        "Before\n"
        "#if [Input Port] is equal 'other' {\n"
        "    Inside block!\n"
        "}\n"
        "After"
    )
    res = process_conditional_blocks(template_false, row_data)
    assert "Inside block!" not in res
    assert "#if" not in res
    # the deleted block must not leave multiple consecutive newlines
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
    res = process_conditional_blocks(template_nested, row_data)
    assert "Outer True" in res
    assert "Inner True" in res
    assert "Inner False" not in res
    assert "#if" not in res


def test_multiple_predicate():
    """The '[port] multiple' operation-count predicate (powered by __ops_count__)."""
    def rb(count, **extra):
        d = {"__ops_count__": count, "Port Name": "p_x", "Review Status": "Reviewed"}
        d.update(extra)
        return d

    # Bare predicate: true when more than one operation
    assert evaluate_condition("[port] multiple", rb(1)) is False
    assert evaluate_condition("[port] multiple", rb(2)) is True
    # Missing count defaults to 1 -> never "multiple"
    assert evaluate_condition("[port] multiple", {"Port Name": "p"}) is False

    # Comparators
    assert evaluate_condition("[Port Name] multiple > 5", rb(6)) is True
    assert evaluate_condition("[Port Name] multiple > 5", rb(5)) is False
    assert evaluate_condition("[port] multiple < 5", rb(3)) is True
    assert evaluate_condition("[port] multiple < 5", rb(5)) is False
    assert evaluate_condition("[port] multiple >= 3", rb(3)) is True
    assert evaluate_condition("[port] multiple <= 1", rb(1)) is True
    assert evaluate_condition("[port] multiple == 4", rb(4)) is True

    # Combines with AND/OR
    assert evaluate_condition("[port] multiple AND [Review Status] is equal 'Reviewed'", rb(3)) is True
    assert evaluate_condition("[port] multiple AND [Review Status] is equal 'Reviewed'", rb(1)) is False

    # process_conditional_blocks routes few vs many operations
    template = (
        "#if [port] multiple > 5 {\nANNEX\n}\n"
        "#if [port] multiple < 6 {\nINLINE\n}\n"
    )
    many = process_conditional_blocks(template, rb(40))
    few = process_conditional_blocks(template, rb(2))
    assert "ANNEX" in many and "INLINE" not in many
    assert "INLINE" in few and "ANNEX" not in few

    # Autocomplete offers 'multiple' after a column, and comparators after it
    sugg, _ = get_condition_suggestions_and_prefix("#if [Port Name] ", ["Port Name"], lambda c: [])
    assert "multiple" in sugg
    sugg2, _ = get_condition_suggestions_and_prefix("#if [Port Name] multiple ", ["Port Name"], lambda c: [])
    assert ">" in sugg2 and "<" in sugg2
