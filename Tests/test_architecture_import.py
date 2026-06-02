"""
Tests for the pure word-similarity helper in ArchitectureImportMixin
(Logic_Architecture_Import). The method does not use instance state, so it is
exercised as an unbound function.
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from Application_Logic.Logic_Architecture_Import import ArchitectureImportMixin

# Unbound — calculate_word_similarity never touches `self`.
sim = lambda a, b: ArchitectureImportMixin.calculate_word_similarity(None, a, b)


def test_identical_names_score_100():
    assert sim("Read_Temp", "Read_Temp") == 100.0


def test_camelcase_and_underscore_equivalent():
    # "ReadTemp" splits to [read, temp]; "Read_Temp" also [read, temp]
    assert sim("ReadTemp", "Read_Temp") == 100.0


def test_empty_inputs_score_zero():
    assert sim("", "anything") == 0.0
    assert sim("anything", "") == 0.0
    assert sim("!!!", "@@@") == 0.0  # no word characters


def test_partial_overlap_between_0_and_100():
    score = sim("Read_Temp_Status", "Read_Temp")
    assert 0.0 < score < 100.0


def test_fuzzy_long_word_match():
    # Long words within fuzzy threshold count as a match
    assert sim("Temperature", "Temperatur") == 100.0


def test_short_words_need_exact_match():
    # 2-char words must match exactly; "ab" vs "ac" should not count
    assert sim("ab", "ac") == 0.0
    assert sim("ab", "ab") == 100.0


def test_unrelated_names_low_score():
    assert sim("Throttle_Position", "Brake_Pressure") == 0.0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
