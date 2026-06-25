"""Column-layout rules for the customizer (Qt-free; extracted from the Phase-0
``src/UI/column_customizer.py`` per its TODO so the API can enforce them and the
React customizer can reuse them).

The architecture table's column layout is project-global; row cells are keyed by
column name and stored per model. So renaming a column means migrating that cell
key across **every** model's rows, and deleting one means dropping the cell.

Column families:
  • ``TC. ID`` — pinned first; never renamed/deleted/moved.
  • Search columns (Port/Function/Variable Search) are *leaders*; each owns
    dependents ``"<name> (Match)"`` (+ ``(Init)``/``(Cyclic)`` for Port/Function).
  • ``Review Status`` is a leader owning ``Port State`` (PortStateColumn).
  • Dependents are never renamed/deleted/moved on their own — they follow the
    leader. Renaming/deleting a leader cascades to its dependents.
  • Locked columns (TC. ID, Port State, the Review column, and any column holding
    data in a *Reviewed* row) cannot be renamed or deleted.
"""
from __future__ import annotations

from typing import Iterable

# The default table layout a fresh project starts with — ported verbatim from
# the PyQt6 ``architecture_table.py`` ``active_config`` so new projects open with
# the same usable columns the old app provided. ``(name, type, visible, width)``.
# Init/Cyclic default to None = "Auto" visibility (shown only when some row has a
# meaningful value), matching the PyQt6 tristate default.
DEFAULT_COLUMN_LAYOUT = [
    ("TC. ID", "Static Text", True, 90),
    ("Input Port", "Port Search", True, 160),
    ("Input Port (Match)", "Static Text", True, 160),
    ("Input Port (Init)", "InitColumn", None, 90),
    ("Input Port (Cyclic)", "CyclicColumn", None, 90),
    ("Mapped Func", "Function Search", True, 160),
    ("Mapped Func (Match)", "Static Text", True, 160),
    ("Mapped Func (Init)", "InitColumn", None, 90),
    ("Mapped Func (Cyclic)", "CyclicColumn", None, 90),
    ("Mapped Parameter", "Variable Search", True, 160),
    ("Mapped Parameter (Match)", "Static Text", True, 160),
    ("Review Status", "Review Status", True, 120),
    ("Port State", "PortStateColumn", True, 110),
]

SEARCH_TYPES = ("Port Search", "Function Search", "Variable Search")
DEP_SUFFIXES = (" (Match)", " (Init)", " (Cyclic)")
# Types a user may pick when adding a column (mirrors architecture_table.py's
# filtered ``logic_options``: Init/Cyclic/Review/PortState/ReleaseResult/Last
# Result are managed automatically, not added directly).
ADDABLE_TYPES = ["Static Text", "Port Search", "Function Search", "Variable Search", "Link"]
SINGLETON_TYPES = ("Link", "Last Result")  # at most one per layout


def is_dependent(name: str) -> bool:
    return name == "Port State" or any(name.endswith(s) for s in DEP_SUFFIXES)


def leader_of(name: str) -> str | None:
    """The leader column a dependent belongs to (None if not a dependent)."""
    if name == "Port State":
        return None  # resolved by type (Review Status), not by name
    for s in DEP_SUFFIXES:
        if name.endswith(s):
            return name[: -len(s)]
    return None


def _cell_text(cell) -> str:
    if not isinstance(cell, dict):
        return ""
    return str(cell.get("widget_text") or cell.get("text") or "").strip()


def compute_locked_columns(layout: list, rows: Iterable[dict]) -> set[str]:
    """Columns that cannot be renamed/deleted: the always-locked set, the Review
    column itself, and any column holding data in a row whose status is Reviewed.
    """
    locked = {"TC. ID", "Port State"}
    review_col = next((c[0] for c in layout if c[1] == "Review Status"), None)
    if not review_col:
        return locked
    locked.add(review_col)
    names = [c[0] for c in layout]
    for row in rows:
        if _cell_text(row.get(review_col)) == "Reviewed":
            for name in names:
                if _cell_text(row.get(name)):
                    locked.add(name)
    return locked


def validate_layout(columns: list) -> None:
    """Raise ``ValueError`` if the proposed layout breaks a hard invariant.
    ``columns`` is a list of ``(name, type, visible, width)`` (extra items ok)."""
    names = [c[0] for c in columns]
    if not names:
        raise ValueError("Layout cannot be empty.")
    if names[0] != "TC. ID":
        raise ValueError("'TC. ID' must remain the first column.")
    if len(set(names)) != len(names):
        raise ValueError("Column names must be unique.")
    for n in names:
        if not n or not str(n).strip():
            raise ValueError("Column names cannot be blank.")
        if "|" in n:
            raise ValueError(f"Column name cannot contain '|': {n!r}")
    for t in SINGLETON_TYPES:
        if [c[1] for c in columns].count(t) > 1:
            raise ValueError(f"There can be only one '{t}' column.")


def migrate_rows(rows: list[dict], renames: dict[str, str], removed: Iterable[str]) -> list[dict]:
    """Apply column renames (move the cell to the new key) and drop removed
    columns' cells, in place, across one model's rows. Returns the same list."""
    removed = set(removed)
    for row in rows:
        for old, new in renames.items():
            if old != new and old in row:
                row[new] = row.pop(old)
        for name in removed:
            row.pop(name, None)
    return rows


def diff_layout(old_names: Iterable[str], new_names: Iterable[str],
                renames: dict[str, str]) -> set[str]:
    """Names present in the old layout but gone from the new one and not the
    source of a rename — i.e. genuinely removed columns whose cells should drop."""
    old, new = set(old_names), set(new_names)
    return old - new - set(renames.keys())
