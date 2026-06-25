"""
Logic-layer tests for Test Case Design operation grouping and column resolution.

These exercise the pure functions in ``Logic_TestCase_Design`` (``resolve_ops_column``,
``resolve_port_column``, ``_build_grouped_rows``, ``process_conditional_blocks``) the
same way the backend ``/api/testdesign`` router does: from the stored column layout
(list of ``(name, type, visible, width)`` tuples) + DB meta strings — no Qt.

Regression covered: a project may store the *operations* in a Port-Search column
(so they get fuzzy-matched against ELF symbols) while the actual *port* lives in a
plain Static-Text column. Grouping must key on the port, never on the operations
column — otherwise every operation renders as its own test case.

(The former Qt preview-paging tests — ``_advance_preview_index`` — were dropped with
the PyQt UI; preview navigation is now handled by the React frontend.)
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_TestCase_Design import (
    resolve_ops_column,
    resolve_port_column,
    _build_grouped_rows,
    process_conditional_blocks,
)


def _resolve(layout, meta_ops=None, meta_port=None):
    """Mirror the backend's two-step resolution (ops first, then port)."""
    ops_col = resolve_ops_column(layout, meta_ops)
    port_col = resolve_port_column(layout, meta_port, ops_col)
    return ops_col, port_col


# --- the user's real layout: ops in "Input Port" (search), port in "Port Name" --
def _rhapsody_layout():
    return [
        ("TC. ID", "Static Text", True, 100),
        ("Input Port", "Port Search", True, 100),
        ("Input Port (Match)", "Static Text", True, 100),
        ("Mapped Func", "Function Search", True, 100),
        ("Mapped Func (Match)", "Static Text", True, 100),
        ("Mapped Parameter", "Variable Search", True, 100),
        ("Port State", "Static Text", True, 100),
        ("Port Name", "Static Text", True, 100),
        ("Required Interface", "Static Text", True, 100),
    ]


def _rhapsody_rows():
    """Three operations under PortA, one under PortB."""
    def row(port, op):
        return {
            "Input Port": {"text": op},
            "Input Port (Match)": {"text": "", "widget_text": op + "_sym (90%)"},
            "Port Name": {"text": port},
            "Port State": {"text": "In Work"},
        }
    return [
        row("PortA", "op_alpha"),
        row("PortA", "op_beta"),
        row("PortA", "op_gamma"),
        row("PortB", "op_solo"),
    ]


def test_port_col_avoids_operations_column():
    """The grouping key must be the Static-Text port, not the ops search column."""
    ops_col, port_col = _resolve(_rhapsody_layout(), meta_ops="Input Port")
    assert ops_col == "Input Port"
    assert port_col == "Port Name"


def test_port_col_legacy_excel_no_regression():
    """When the port itself is a Port-Search column and there are no operations,
    resolution still returns that search column (legacy Excel imports)."""
    layout = [
        ("Input Port", "Port Search", True, 100),
        ("Input Port (Match)", "Static Text", True, 100),
        ("Notes", "Static Text", True, 100),
    ]
    ops_col, port_col = _resolve(layout)  # no operations meta
    assert ops_col == ""
    assert port_col == "Input Port"


def test_port_col_skips_helper_columns():
    """Match/State columns are never chosen as the port key."""
    layout = [
        ("Input Port (Match)", "Static Text", True, 100),
        ("Port State", "Static Text", True, 100),
        ("Port Name", "Static Text", True, 100),
    ]
    _ops, port_col = _resolve(layout)
    assert port_col == "Port Name"


def test_build_grouped_rows_collapses_by_port():
    merged = _build_grouped_rows(_rhapsody_rows(), port_col="Port Name", ops_col="Input Port")
    # PortA (3 ops) + PortB (1 op) -> 2 grouped entries
    assert len(merged) == 2
    by_port = {m["Port Name"]: m for m in merged}
    assert by_port["PortA"]["__ops_count__"] == 3
    assert by_port["PortB"]["__ops_count__"] == 1
    # The operations column of the multi-op group becomes a markdown bullet list.
    ops_cell = by_port["PortA"]["Input Port"].lstrip()
    assert ops_cell.startswith("- ")
    for op in ("op_alpha", "op_beta", "op_gamma"):
        assert op in by_port["PortA"]["Input Port"]


def test_build_grouped_rows_empty_ports_stay_separate():
    """Rows without a port value must not all collapse into one bogus group."""
    rows = [
        {"Input Port": {"text": "op1"}, "Port Name": {"text": ""}},
        {"Input Port": {"text": "op2"}, "Port Name": {"text": ""}},
    ]
    merged = _build_grouped_rows(rows, port_col="Port Name", ops_col="Input Port")
    assert len(merged) == 2
    assert all(m["__ops_count__"] == 1 for m in merged)


def test_multiple_predicate_true_for_grouped_port():
    merged = _build_grouped_rows(_rhapsody_rows(), port_col="Port Name", ops_col="Input Port")
    by_port = {m["Port Name"]: m for m in merged}
    template = "Start #if [Port Name] multiple {MANY} End"
    multi = process_conditional_blocks(template, by_port["PortA"])
    single = process_conditional_blocks(template, by_port["PortB"])
    assert "MANY" in multi
    assert "MANY" not in single


def test_multiple_predicate_with_threshold():
    merged = _build_grouped_rows(_rhapsody_rows(), port_col="Port Name", ops_col="Input Port")
    by_port = {m["Port Name"]: m for m in merged}
    template = "#if [Port Name] multiple > 2 {BIG}"
    assert "BIG" in process_conditional_blocks(template, by_port["PortA"])  # 3 > 2
    template2 = "#if [Port Name] multiple > 5 {BIG}"
    assert "BIG" not in process_conditional_blocks(template2, by_port["PortA"])  # 3 > 5 false


def test_ops_col_name_falls_back_to_named_column():
    """With no DB meta, the operations column is detected by name ('operation'),
    and the name-based port fallback must skip that detected operations column."""
    layout = [("Port Name", "Static Text", True, 100), ("Operation", "Static Text", True, 100)]
    ops_col, port_col = _resolve(layout)
    assert ops_col == "Operation"
    assert port_col == "Port Name"


def test_non_ops_port_search_column_takes_precedence():
    """A Port-Search column that is NOT the operations column is chosen as the
    port key ahead of a same-named static column (legacy Excel precedence)."""
    layout = [
        ("Sig", "Port Search", True, 100),
        ("Operation", "Static Text", True, 100),
        ("Port Name", "Static Text", True, 100),
    ]
    ops_col, port_col = _resolve(layout)
    assert ops_col == "Operation"
    assert port_col == "Sig"


def test_ops_col_meta_takes_precedence_over_name():
    layout = [
        ("Operation", "Static Text", True, 100),
        ("Input Port", "Port Search", True, 100),
        ("Port Name", "Static Text", True, 100),
    ]
    # meta points ops at the search column even though a column is *named* Operation
    ops_col, _port = _resolve(layout, meta_ops="Input Port")
    assert ops_col == "Input Port"
