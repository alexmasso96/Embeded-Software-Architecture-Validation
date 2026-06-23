"""
Test Case Design token binding — case-insensitive substitution + [Model] token.

A user who types `[model]` (or `[MODEL]`) by hand should get the same result as
the canonical `[Model]` the autocomplete inserts; column tokens are likewise
case-insensitive. Pure logic-layer tests (no Qt / no DB).
"""
import os
import sys

sys.path.insert(0, os.path.abspath("src"))

from Application_Logic.Logic_TestCase_Design import bind_data, render_template


def test_model_token_case_insensitive():
    title, body = render_template(
        "[model] | [MODEL] | [Model]",
        "active: [model]",
        {"Input Port": "p_speed"},
        model_name="Arch_A",
    )
    assert title == "Arch_A | Arch_A | Arch_A"
    assert body == "active: Arch_A"


def test_column_token_case_insensitive():
    assert bind_data("[input port] / [Input Port]", {"Input Port": "p_speed"}) == "p_speed / p_speed"


def test_value_with_regex_chars_is_literal():
    # A bound value containing backslashes / group-like text must not be treated
    # as a regex replacement template.
    assert bind_data("x=[Col]", {"Col": r"a\1b$2"}) == r"x=a\1b$2"


def test_unknown_token_left_untouched():
    assert bind_data("[Nope]", {"Model": "Arch_A"}) == "[Nope]"
