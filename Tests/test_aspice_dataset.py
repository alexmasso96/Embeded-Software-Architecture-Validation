"""
Regression anchor for the ForTesting/AspiceAudit dataset (the "Window Lift
Controller" fixture built during the ASPICE audit, 2026-06-07).

Testing strategy (per project convention: automate the LOGIC layer only; the UI
is verified manually). This module pins the end-to-end logic-layer contracts the
audit exercised, all of which hold against the current code so the suite stays
green:

  * dataset integrity (the fixture files exist),
  * ELF parse contract — functions / parameters / structures / globals — on the
    committed (patched) ELFs, backend-agnostic (passes on both rust_elf_parser
    and the pyelftools fallback),
  * the intended v1 -> v2 deltas (added/removed function, added struct field),
  * the C code-index call graph (hub + static helpers),
  * mind-map build + render (signatures, no bodies, within budget),
  * source diff v1 <-> v2 (added file, modified file),
  * requirements parsing (CSV + XLSX),
  * architecture-operation -> ELF-symbol matching (exact, score 100).

Bug-specific regression tests (BUG-01 native-parser REL corruption, BUG-02
new-project crash, NC-1 match-column validation) intentionally land WITH their
fixes — adding failing tests here would break the green suite and contradict the
project's "regression tests when a bug reappears" rule. This module instead locks
the CORRECT behaviours so they cannot silently regress.

The dataset ships in Resources/ (committed), so this also runs in CI. If it is
somehow absent, the whole module skips.
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

import pytest

DATASET = os.path.join(os.path.dirname(__file__), "..", "Resources", "AI_Demo_WindowLift")
SRC_V1 = os.path.join(DATASET, "src_v1")
SRC_V2 = os.path.join(DATASET, "src_v2")
ELF_V1 = os.path.join(DATASET, "wlc_v1.elf")
ELF_V2 = os.path.join(DATASET, "wlc_v2.elf")

pytestmark = pytest.mark.skipif(
    not (os.path.isdir(SRC_V1) and os.path.isfile(ELF_V1)),
    reason="Resources/AI_Demo_WindowLift dataset not present.",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def parser_v1():
    from core import elf_parser
    p = elf_parser.ELFParser()
    p.load_elf(ELF_V1)
    p.extract_all()
    return p


@pytest.fixture(scope="module")
def parser_v2():
    from core import elf_parser
    p = elf_parser.ELFParser()
    p.load_elf(ELF_V2)
    p.extract_all()
    return p


@pytest.fixture(scope="module")
def index_v1():
    from Application_Logic.Logic_Code_Index import build_index
    return build_index(SRC_V1)


# ---------------------------------------------------------------------------
# Dataset integrity
# ---------------------------------------------------------------------------
def test_dataset_files_present():
    for f in ("requirements.csv", "requirements.xlsx",
              "architecture_ports.csv", "architecture_ports.xlsx",
              "wlc_v1.elf", "wlc_v2.elf", "README.md"):
        assert os.path.isfile(os.path.join(DATASET, f)), f"missing {f}"
    assert os.path.isfile(os.path.join(DATASET, "Test Case Design",
                                       "WindowLift_Test_Case_Design.md"))


# ---------------------------------------------------------------------------
# ELF parse contract (backend-agnostic — holds on rust_elf_parser AND pyelftools)
# ---------------------------------------------------------------------------
def test_elf_functions_and_params(parser_v1):
    funcs = {f.name: f for f in parser_v1.functions}
    for name in ("WLC_Init", "WLC_Cyclic", "WLC_MotorSetDuty", "WLC_DetectPinch",
                 "WLC_ReadHallPosition", "WLC_ReadCurrent", "WLC_GetState",
                 "WLC_ClampDuty", "WLC_Scale"):
        assert name in funcs, f"{name} missing from ELF functions"
    # distinct addresses (single-TU relocatable object lays functions sequentially)
    addrs = [f.address for f in parser_v1.functions]
    assert len(set(addrs)) == len(addrs)
    # parameters survive DWARF parsing (this is the field BUG-01 used to drop)
    assert funcs["WLC_MotorSetDuty"].parameters == [{"name": "duty", "type": "uint16_t"}]
    assert funcs["WLC_MotorInit"].parameters[0]["name"] == "cfg"
    assert "WLC_Config_t" in funcs["WLC_MotorInit"].parameters[0]["type"]


def test_elf_structures(parser_v1):
    structs = parser_v1.structures
    assert set(structs) >= {"WLC_Config_t", "WLC_State_t"}
    cfg_fields = {fld["name"] for fld in structs["WLC_Config_t"]}
    assert {"max_duty", "current_limit_ma", "pinch_enabled"} <= cfg_fields
    state_fields = {fld["name"] for fld in structs["WLC_State_t"]}
    assert {"phase", "position", "current_ma", "pinch_flag"} <= state_fields


def test_elf_globals(parser_v1):
    g = set(parser_v1.global_vars_dwarf)
    assert {"g_wlc_state", "g_wlc_cfg", "g_motor_duty"} <= g


# ---------------------------------------------------------------------------
# v1 -> v2 deltas (drive diffs / baselines / change-log scenarios)
# ---------------------------------------------------------------------------
def test_v1_to_v2_function_deltas(parser_v1, parser_v2):
    n1 = {f.name for f in parser_v1.functions}
    n2 = {f.name for f in parser_v2.functions}
    assert "WLC_LegacyInit" in n1 and "WLC_LegacyInit" not in n2   # deleted
    assert "WLC_AutoReverse" not in n1 and "WLC_AutoReverse" in n2  # added


def test_v2_struct_field_added(parser_v2):
    state_fields = {fld["name"] for fld in parser_v2.structures["WLC_State_t"]}
    assert "reverse_count" in state_fields   # modified struct


# ---------------------------------------------------------------------------
# C code index — call graph + static helpers
# ---------------------------------------------------------------------------
def test_code_index_call_graph(index_v1):
    funcs = index_v1.functions
    assert "WLC_UpdateStateMachine" in funcs       # the hub
    hub_calls = set(funcs["WLC_UpdateStateMachine"].calls)
    assert {"WLC_ReadHallPosition", "WLC_DetectPinch", "WLC_MotorSetDuty"} <= hub_calls
    # static (file-local) helper detected
    assert funcs["WLC_ClampDuty"].is_static is True
    # file mapping is on .relpath
    assert funcs["WLC_MotorSetDuty"].relpath.endswith("wlc_motor.c")


# ---------------------------------------------------------------------------
# Mind map build + render
# ---------------------------------------------------------------------------
def test_build_mind_map_and_render():
    from Application_Logic import Logic_AI_Context as ctx
    ports = [
        {"name": "p_pinch", "operation": "WLC_DetectPinch"},
        {"name": "p_cyclic", "operation": "WLC_Cyclic"},
    ]
    reqs = [{"id": "REQ-WLC-003", "text": "Anti-pinch shall trigger on over-current."}]
    mm = ctx.build_mind_map(SRC_V1, "WindowLift", 1, ports, reqs)
    assert "WLC_DetectPinch" in mm["functions"]
    # bodies must NOT be inlined into the mind map (token-budget rule)
    node = mm["functions"]["WLC_DetectPinch"]
    assert "body" not in node or not node.get("body")
    text = ctx.mind_map_to_text(mm, budget_chars=14000)
    assert len(text) <= 14000
    assert "WLC_DetectPinch" in text


# ---------------------------------------------------------------------------
# Source diff v1 <-> v2
# ---------------------------------------------------------------------------
def test_diff_v1_to_v2():
    from Application_Logic import Logic_AI_Context as ctx
    diffs = ctx.diff_source_folders(SRC_V2, SRC_V1)   # current=v2, previous=v1
    by_file = {d["file_path"]: d["status"] for d in diffs}
    # added file (only in v2)
    added = [f for f, s in by_file.items() if f.endswith("wlc_safety.c")]
    assert added and by_file[added[0]] == "added"
    # modified file (changed between versions)
    modified = [f for f, s in by_file.items()
                if f.endswith("wlc_main.c") and s == "modified"]
    assert modified


# ---------------------------------------------------------------------------
# Requirements parsing (CSV + XLSX)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fname", ["requirements.csv", "requirements.xlsx"])
def test_parse_requirements(fname):
    from Application_Logic import Logic_AI_Context as ctx
    reqs = ctx.parse_requirements_file(os.path.join(DATASET, fname))
    ids = {r["id"] for r in reqs}
    assert "REQ-WLC-001" in ids and "REQ-WLC-050" in ids
    by_id = {r["id"]: r["text"] for r in reqs}
    assert "clamp" in by_id["REQ-WLC-001"].lower()


# ---------------------------------------------------------------------------
# Architecture-operation -> ELF-symbol matching (the core traceability link)
# ---------------------------------------------------------------------------
def test_architecture_operations_match_elf_symbols(parser_v1):
    import csv
    from Application_Logic.Logic_Symbol_Matcher import SymbolMatcher
    matcher = SymbolMatcher(parser_v1)
    with open(os.path.join(DATASET, "architecture_ports.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    ops = [r["Operations"] for r in rows if r.get("Operations")]
    assert ops, "no operations in architecture_ports.csv"
    for op in ops:
        name, score = matcher.find_best_match(op)
        # every architecture operation is a real WLC function -> exact match
        assert name == op and score == 100, f"{op!r} -> {name!r} ({score})"
