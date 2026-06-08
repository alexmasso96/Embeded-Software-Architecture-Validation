"""
Phase 7.5 — contract pin for the ported code indexer (Logic_Code_Index).

This test FREEZES the public API the mind-map builder (Phase 8) depends on, run
against the real C fixture in Resources/AIGenTest/src. If a future change to the
ported indexer breaks any of these shapes, Phase 8 breaks — so this is the
authoritative record of the contract (and corrects two guesses the plan made).
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

import pytest
from Application_Logic.Logic_Code_Index import (
    build_index, CodeIndex, FunctionInfo, GlobalVarInfo, extract_keywords,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "Resources", "AIGenTest", "src")


@pytest.fixture(scope="module")
def idx():
    return build_index(FIXTURE)


def test_clean_import_no_external_dependency():
    # Importing must not pull in anything from the 'Test Case Generator/' tree.
    import Application_Logic.Logic_Code_Index as m
    assert "Test Case Generator" not in (m.__file__ or "")
    assert m.__file__.replace("\\", "/").endswith("src/Application_Logic/Logic_Code_Index.py")


def test_build_index_returns_codeindex(idx):
    assert isinstance(idx, CodeIndex)


def test_functions_contract(idx):
    # functions: Dict[name -> FunctionInfo]
    assert isinstance(idx.functions, dict)
    assert "DoorControl_Init" in idx.functions
    f = idx.functions["DoorControl_Init"]
    assert isinstance(f, FunctionInfo)
    # the file is on .relpath (NOT .file)
    assert f.relpath.endswith("door_control.c")
    assert "DoorControl_Init" in f.signature
    assert isinstance(f.reads_vars, list)
    assert isinstance(f.writes_vars, list)
    assert isinstance(f.calls, list)
    assert isinstance(f.body, str) and f.body
    # data-flow actually populated: the 10ms task reads the supply voltage and
    # calls the BSP hooks.
    t = idx.functions["DoorControl_10ms"]
    assert "Bsp_ReadSupplyVoltage" in t.calls
    assert "doorSupplyVoltage" in t.reads_vars


def test_globals_contract(idx):
    # the attribute is 'globals' (NOT 'global_vars')
    assert isinstance(idx.globals, dict)
    assert "doorLockState" in idx.globals
    assert isinstance(idx.globals["doorLockState"], GlobalVarInfo)


def test_graphs_and_file_index(idx):
    assert isinstance(idx.call_graph, dict)
    assert isinstance(idx.reverse_call_graph, dict)
    assert isinstance(idx.file_functions, dict)
    assert "door_control.c" in idx.file_functions
    assert set(idx.file_functions["door_control.c"]) == {
        "DoorControl_Init", "DoorControl_10ms", "DoorControl_GetLockState",
    }


def test_find_functions_by_keywords_shape(idx):
    # CONTRACT CORRECTION: returns list[(score: int, FunctionInfo)] sorted by
    # score desc — NOT (name, score) as an earlier plan draft assumed. Phase 8
    # must unpack (score, func).
    results = idx.find_functions_by_keywords(["lock"], max_results=5)
    assert isinstance(results, list) and results
    score, func = results[0]
    assert isinstance(score, int) and score > 0
    assert isinstance(func, FunctionInfo)
    # a lock-related function ranks (it reads/writes doorLockState or names Lock)
    names = {f.name for _s, f in results}
    assert names & {"DoorControl_10ms", "DoorControl_GetLockState"}


def test_extract_keywords_public_wrapper():
    # string input
    kws = extract_keywords("DoorControl reads the door lock state")
    assert "DoorControl" in kws and "lock" in kws
    assert "the" not in kws  # stopword filtered
    # iterable input, de-duplicated across items
    multi = extract_keywords(["lock state", "lock voltage"])
    assert multi.count("lock") == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
