"""
Logic-layer tests for Test Case Design operation grouping and preview navigation.

These exercise the pure logic of TestCaseDesignController without standing up the
Qt UI: the grouping methods only need access to ``active_columns`` and a small DB
meta lookup, so we bind the unbound methods onto a lightweight stand-in object.

Regression covered: a project may store the *operations* in a Port-Search column
(so they get fuzzy-matched against ELF symbols) while the actual *port* lives in a
plain Static-Text column. Grouping must key on the port, never on the operations
column — otherwise every operation renders as its own test case.
"""
import sys
import os
import types

sys.path.append(os.path.abspath("src"))

from UI.test_case_design import TestCaseDesignController as TC
from UI.column_types import (
    PortSearchColumn, FunctionSearchColumn, VariableSearchColumn,
)

# Methods that make up the pure logic surface under test.
_BIND = [
    "_build_grouped_rows", "_get_port_col_name", "_get_ops_col_name",
    "get_row_bind_data", "strip_percentage_suffix", "process_conditional_blocks",
    "evaluate_condition", "evaluate_boolean_list", "evaluate_single_condition",
    "_get_ops_count", "_compare_count", "_is_int", "normalize_value",
    "_advance_preview_index",
]


class _StaticCol:
    """Stand-in for a non-search column (Static Text, Port State, etc.)."""
    def __init__(self, name):
        self.name = name


class _DB:
    is_open = True

    def __init__(self, meta=None):
        self._meta = meta or {}

    def get_meta(self, key):
        return self._meta.get(key)


def _make(active_cols, meta=None, grouping="grouped"):
    """Build a stand-in controller with the logic methods bound to it."""
    obj = types.SimpleNamespace()
    obj._operation_grouping = grouping
    obj.preview_row_index = -1
    obj._effective_row_count = 0
    obj.main_window = types.SimpleNamespace(
        arch_controller=types.SimpleNamespace(active_columns=active_cols),
        project_db=_DB(meta),
    )
    for name in _BIND:
        attr = getattr(TC, name)
        # staticmethods come back as plain functions — bind only real methods.
        if isinstance(TC.__dict__.get(name), staticmethod):
            setattr(obj, name, attr)
        else:
            setattr(obj, name, types.MethodType(attr, obj))
    return obj


# --- the user's real layout: ops in "Input Port" (search), port in "Port Name" --
def _rhapsody_cols():
    return [
        _StaticCol("TC. ID"),
        PortSearchColumn("Input Port"),
        _StaticCol("Input Port (Match)"),
        FunctionSearchColumn("Mapped Func"),
        _StaticCol("Mapped Func (Match)"),
        VariableSearchColumn("Mapped Parameter"),
        _StaticCol("Port State"),
        _StaticCol("Port Name"),
        _StaticCol("Required Interface"),
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
    tc = _make(_rhapsody_cols(), meta={"operations_column_name": "Input Port"})
    assert tc._get_ops_col_name() == "Input Port"
    assert tc._get_port_col_name() == "Port Name"


def test_port_col_legacy_excel_no_regression():
    """When the port itself is a Port-Search column and there are no operations,
    resolution still returns that search column (legacy Excel imports)."""
    cols = [PortSearchColumn("Input Port"), _StaticCol("Input Port (Match)"),
            _StaticCol("Notes")]
    tc = _make(cols, meta={})  # no operations_column_name
    assert tc._get_ops_col_name() == ""
    assert tc._get_port_col_name() == "Input Port"


def test_port_col_skips_helper_columns():
    """Match/Init/Cyclic/State columns are never chosen as the port key."""
    cols = [_StaticCol("Input Port (Match)"), _StaticCol("Port State"),
            _StaticCol("Port Name")]
    tc = _make(cols, meta={})
    assert tc._get_port_col_name() == "Port Name"


def test_build_grouped_rows_collapses_by_port():
    tc = _make(_rhapsody_cols(), meta={"operations_column_name": "Input Port"})
    merged = tc._build_grouped_rows(_rhapsody_rows())
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
    tc = _make(_rhapsody_cols(), meta={"operations_column_name": "Input Port"})
    rows = [
        {"Input Port": {"text": "op1"}, "Port Name": {"text": ""}},
        {"Input Port": {"text": "op2"}, "Port Name": {"text": ""}},
    ]
    merged = tc._build_grouped_rows(rows)
    assert len(merged) == 2
    assert all(m["__ops_count__"] == 1 for m in merged)


def test_multiple_predicate_true_for_grouped_port():
    tc = _make(_rhapsody_cols(), meta={"operations_column_name": "Input Port"})
    merged = tc._build_grouped_rows(_rhapsody_rows())
    by_port = {m["Port Name"]: m for m in merged}
    template = "Start #if [Port Name] multiple {MANY} End"
    multi = tc.process_conditional_blocks(template, by_port["PortA"])
    single = tc.process_conditional_blocks(template, by_port["PortB"])
    assert "MANY" in multi
    assert "MANY" not in single


def test_multiple_predicate_with_threshold():
    tc = _make(_rhapsody_cols(), meta={"operations_column_name": "Input Port"})
    merged = tc._build_grouped_rows(_rhapsody_rows())
    by_port = {m["Port Name"]: m for m in merged}
    template = "#if [Port Name] multiple > 2 {BIG}"
    assert "BIG" in tc.process_conditional_blocks(template, by_port["PortA"])  # 3 > 2
    template2 = "#if [Port Name] multiple > 5 {BIG}"
    assert "BIG" not in tc.process_conditional_blocks(template2, by_port["PortA"])  # 3 > 5 false


def test_advance_preview_index_bounds():
    tc = _make(_rhapsody_cols())
    tc._effective_row_count = 2  # two groups
    tc.preview_row_index = 0
    assert tc._advance_preview_index(1) is True
    assert tc.preview_row_index == 1
    # At the last group, Next must not advance past it (the old bug paged to raw rows).
    assert tc._advance_preview_index(1) is False
    assert tc.preview_row_index == 1
    # Previous works back to 0 and clamps there.
    assert tc._advance_preview_index(-1) is True
    assert tc.preview_row_index == 0
    assert tc._advance_preview_index(-1) is False
    assert tc.preview_row_index == 0


def test_advance_preview_index_empty():
    tc = _make(_rhapsody_cols())
    tc._effective_row_count = 0
    tc.preview_row_index = 0
    assert tc._advance_preview_index(1) is False
    assert tc.preview_row_index == 0


def test_ops_col_name_falls_back_to_named_column():
    """With no DB meta, the operations column is detected by name ('operation'),
    and the name-based port fallback must skip that detected operations column."""
    cols = [_StaticCol("Port Name"), _StaticCol("Operation")]
    tc = _make(cols, meta={})
    assert tc._get_ops_col_name() == "Operation"
    assert tc._get_port_col_name() == "Port Name"


def test_non_ops_port_search_column_takes_precedence():
    """A Port-Search column that is NOT the operations column is chosen as the
    port key ahead of a same-named static column (legacy Excel precedence)."""
    cols = [PortSearchColumn("Sig"), _StaticCol("Operation"), _StaticCol("Port Name")]
    tc = _make(cols, meta={})
    assert tc._get_ops_col_name() == "Operation"
    assert tc._get_port_col_name() == "Sig"


def test_ops_col_meta_takes_precedence_over_name():
    cols = [_StaticCol("Operation"), PortSearchColumn("Input Port"), _StaticCol("Port Name")]
    # meta points ops at the search column even though a column is *named* Operation
    tc = _make(cols, meta={"operations_column_name": "Input Port"})
    assert tc._get_ops_col_name() == "Input Port"
