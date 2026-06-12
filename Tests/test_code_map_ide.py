"""
#2D — IDE features for the Code Map source viewer.

Logic-layer coverage (the event-filter wiring itself is UI, verified manually per
the testing strategy):
  * build_code_map() persists the #define map into the code map.
  * describe_symbol() classifies a word (function / global / macro / unknown) and
    formats the hover tooltip — it's pure (Qt-free), so we call it unbound with a
    lightweight stub instead of constructing the Qt controller.
  * _is_known_function() gates Ctrl-click navigation + the link affordance.
"""
import os
import sys
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

sys.path.append(os.path.abspath("src"))

# A QApplication may be needed for the widgets module import side effects.
app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic import Logic_Code_Map as cm
from Application_Logic.Logic_Code_Index import CodeIndex
from Application_Logic.Logic_Code_Map_Tab import AICodeMapController


# ── 1. defines persisted into the code map ───────────────────────────────────

def _bare_parser():
    p = MagicMock()
    p._db = None
    p._active_elf_hash = None
    p.functions = []
    p.global_vars_dwarf = {}
    return p


def test_build_code_map_includes_defines():
    idx = CodeIndex()
    idx.defines = {"MAX_LEN": "256", "DEBUG": ""}
    cmap = cm.build_code_map(_bare_parser(), idx, source_root="x",
                             prefer_source_calls=True)
    assert cmap["defines"] == {"MAX_LEN": "256", "DEBUG": ""}


def test_build_code_map_defines_empty_without_index():
    cmap = cm.build_code_map(_bare_parser(), None, source_root="x",
                             prefer_source_calls=True)
    assert cmap["defines"] == {}


# ── 2. describe_symbol() classification + formatting ─────────────────────────

DATASET = {
    "functions": {
        "compute_crc": {
            "signature": "uint32_t compute_crc(const uint8_t* d, size_t n)",
            "return_type": "uint32_t",
            "file": "src/crc.c",
            "line_start": 42,
            "calls": [],
        }
    },
    "global_variables": {"g_state": "int"},
    "defines": {"MAX_LEN": "256", "ENABLE": ""},
}


def _ctrl(dataset):
    stub = MagicMock()
    stub.dataset = dataset
    return stub


def test_describe_function():
    t = AICodeMapController.describe_symbol(_ctrl(DATASET), "compute_crc")
    assert "compute_crc" in t and "uint32_t" in t
    assert "src/crc.c:42" in t and "function" in t


def test_describe_global():
    t = AICodeMapController.describe_symbol(_ctrl(DATASET), "g_state")
    assert "g_state" in t and "global variable" in t and "int" in t


def test_describe_macro_with_value():
    t = AICodeMapController.describe_symbol(_ctrl(DATASET), "MAX_LEN")
    assert "#define MAX_LEN 256" in t


def test_describe_macro_no_value():
    t = AICodeMapController.describe_symbol(_ctrl(DATASET), "ENABLE")
    assert t == "<code>#define ENABLE</code>"


def test_describe_unknown_returns_none():
    assert AICodeMapController.describe_symbol(_ctrl(DATASET), "nope") is None


def test_describe_empty_word_returns_none():
    assert AICodeMapController.describe_symbol(_ctrl(DATASET), "") is None


def test_describe_no_dataset_returns_none():
    assert AICodeMapController.describe_symbol(_ctrl(None), "compute_crc") is None


def test_describe_missing_defines_key_is_safe():
    # Older saved maps have no "defines" key — must not raise.
    legacy = {"functions": {}, "global_variables": {}}
    assert AICodeMapController.describe_symbol(_ctrl(legacy), "MAX_LEN") is None


def test_describe_html_escaped():
    ds = {"functions": {}, "global_variables": {"v": "std::vector<int>"}, "defines": {}}
    t = AICodeMapController.describe_symbol(_ctrl(ds), "v")
    assert "&lt;int&gt;" in t and "<int>" not in t


# ── 3. _is_known_function() gating ───────────────────────────────────────────

def test_is_known_function_true_for_function():
    assert AICodeMapController._is_known_function(_ctrl(DATASET), "compute_crc") is True


def test_is_known_function_false_for_global():
    assert AICodeMapController._is_known_function(_ctrl(DATASET), "g_state") is False


def test_is_known_function_false_for_unknown_or_empty():
    assert AICodeMapController._is_known_function(_ctrl(DATASET), "nope") is False
    assert AICodeMapController._is_known_function(_ctrl(DATASET), "") is False


def test_is_known_function_false_without_dataset():
    assert AICodeMapController._is_known_function(_ctrl(None), "compute_crc") is False
