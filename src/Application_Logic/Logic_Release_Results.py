"""
Release-result column logic (Qt-free, pure).

A release-result column records a per-port test verdict for one release. The
ASPICE-aligned state machine (SWE.6): a port is only "testable" once its work
product is released AND its test case is reviewed; otherwise the result is
blocked; retired/deleted/baselined items carry no result.

States
------
- ``Passed`` / ``Failed``  — recorded verdicts (user-set)
- ``Not Run``              — ready to test, not yet executed
- ``Block``                — preconditions not met (cannot be executed yet)
- ``No Result``            — not applicable (retired/deleted/baselined/new), read-only

Storage: values live as ordinary row cells under the column's name (one column
per release). ``Last Result`` mirrors the most-recently-created result column.
"""
from __future__ import annotations

# User-selectable verdicts (No Result is never user-selectable).
RESULT_OPTIONS = ["Not Run", "Block", "Failed", "Passed"]
NO_RESULT = "No Result"
ALL_RESULT_STATES = RESULT_OPTIONS + [NO_RESULT]

# Palette (mirrors the Qt ReleaseResultColumn.state_colors).
RESULT_COLORS = {
    "Passed": "#2e8b57",    # green
    "Failed": "#8b0000",    # red
    "Block": "#b8860b",     # goldenrod
    "Not Run": "#4a90e2",   # blue
    NO_RESULT: "#808080",   # grey
}

# Verdicts that are user-recorded and must never be auto-overwritten on
# re-initialization. Block / No Result / empty are derived and re-evaluated.
_PRESERVED = {"Passed", "Failed", "Not Run"}

_RELEASED = {"Released", "Accepted"}


def derive_result(model_status: str, port_state: str, review_status: str,
                  *, is_baselined: bool = False, existing: str = "") -> str:
    """Compute a port's release-result value from its context.

    ASPICE gate: ``Not Run`` requires the model to be Released/Accepted AND the
    port's Review Status to be ``Reviewed``; otherwise ``Block``. Retired/deleted
    ports, a retired model, or a baselined release column → ``No Result``.

    A previously recorded verdict (Passed/Failed/Not Run) is preserved; only
    empty / Block / No Result cells are (re-)derived.
    """
    if existing and existing in _PRESERVED:
        return existing
    if is_baselined:
        return NO_RESULT
    if (model_status or "") == "Retired":
        return NO_RESULT
    if (port_state or "") in ("Retired", "Deleted"):
        return NO_RESULT
    if (model_status or "") in _RELEASED and (review_status or "") == "Reviewed":
        return "Not Run"
    return "Block"


def is_result_editable(*, is_active_release: bool, is_baselined: bool,
                       value: str) -> bool:
    """A result cell is editable only when it belongs to the active release, that
    release is not baselined, and the cell carries an actual (non-"No Result")
    verdict slot."""
    return is_active_release and not is_baselined and value != NO_RESULT


def result_column_name(release_name: str) -> str:
    """Display name for a release's result column."""
    return f"Release_{release_name}_Result"
