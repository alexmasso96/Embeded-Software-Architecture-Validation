"""Release-result derivation rules (ASPICE SWE.6 gate). Pure logic — no Qt, no DB."""
import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from Application_Logic.Logic_Release_Results import (
    derive_result, is_result_editable, NO_RESULT, result_column_name,
)


def test_released_and_reviewed_is_not_run():
    assert derive_result("Released", "Released", "Reviewed") == "Not Run"
    assert derive_result("Accepted", "In Work", "Reviewed") == "Not Run"


def test_blocked_when_model_not_released():
    assert derive_result("In Work", "Released", "Reviewed") == "Block"


def test_blocked_when_not_reviewed():
    # ASPICE: a reviewed test case is required to leave Block.
    assert derive_result("Released", "Released", "Not Reviewed") == "Block"
    assert derive_result("Released", "Released", "In Review") == "Block"


def test_no_result_for_retired_or_deleted():
    assert derive_result("Released", "Retired", "Reviewed") == NO_RESULT
    assert derive_result("Released", "Deleted", "Reviewed") == NO_RESULT
    assert derive_result("Retired", "Released", "Reviewed") == NO_RESULT


def test_no_result_when_baselined():
    assert derive_result("Released", "Released", "Reviewed", is_baselined=True) == NO_RESULT


def test_recorded_verdicts_preserved():
    # Passed/Failed/Not Run survive re-derivation even if conditions regress.
    assert derive_result("In Work", "In Work", "Not Reviewed", existing="Passed") == "Passed"
    assert derive_result("In Work", "In Work", "Not Reviewed", existing="Failed") == "Failed"
    assert derive_result("In Work", "In Work", "Not Reviewed", existing="Not Run") == "Not Run"


def test_block_and_no_result_are_reevaluated():
    # A stale Block becomes Not Run once preconditions are met.
    assert derive_result("Released", "Released", "Reviewed", existing="Block") == "Not Run"
    assert derive_result("Released", "Released", "Reviewed", existing=NO_RESULT) == "Not Run"


def test_editability():
    assert is_result_editable(is_active_release=True, is_baselined=False, value="Not Run") is True
    assert is_result_editable(is_active_release=False, is_baselined=False, value="Not Run") is False
    assert is_result_editable(is_active_release=True, is_baselined=True, value="Not Run") is False
    assert is_result_editable(is_active_release=True, is_baselined=False, value=NO_RESULT) is False


def test_column_name():
    assert result_column_name("R1.0") == "Release_R1.0_Result"
