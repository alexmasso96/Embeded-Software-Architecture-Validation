"""
#2C — manual / source-based indexing fallback.

When the ELF carries no usable call tree (stripped binary, ET_REL relocatable,
unsupported arch, or Capstone missing), the code map must fall back to the
*source-derived* call graph (ast_func.calls) as the primary edges instead of
emitting an edgeless graph from failed disassembly.

These exercise the pure-logic chokepoints:
  * elf_has_call_tree() — the robustness probe.
  * build_code_map(prefer_source_calls=...) — the routing + edge selection.
"""
import os
import sys
from unittest.mock import MagicMock

sys.path.append(os.path.abspath("src"))

from Application_Logic import Logic_Code_Map as cm
from Application_Logic.Logic_Code_Index import FunctionInfo, CodeIndex


# ── helpers ──────────────────────────────────────────────────────────────────

def _mem_parser(funcs_subcalls):
    """Build an in-memory MagicMock parser whose extract_subcalls() is driven by
    the {name: [subcalls]} map. `funcs_subcalls` keys define parser.functions."""
    parser = MagicMock()
    parser._db = None
    parser._active_elf_hash = None
    fobjs = []
    for name in funcs_subcalls:
        f = MagicMock()
        f.name = name
        f.address = 0x1000
        f.size = 64
        f.parameters = []
        f.return_type = "void"
        fobjs.append(f)
    parser.functions = fobjs
    parser.extract_subcalls.side_effect = lambda n: list(funcs_subcalls.get(n, []))
    return parser


def _write_elf_header(path, e_type, *, little=True):
    """Write a minimal 18-byte ELF header (magic + e_type) to `path`."""
    head = bytearray(18)
    head[0:4] = b"\x7fELF"
    head[4] = 1                       # EI_CLASS = 32-bit
    head[5] = 1 if little else 2      # EI_DATA endianness
    head[6] = 1                       # EI_VERSION
    head[16:18] = e_type.to_bytes(2, "little" if little else "big")
    with open(path, "wb") as f:
        f.write(head)
    return str(path)


def _index(name, calls):
    idx = CodeIndex()
    idx.functions = {name: FunctionInfo(name=name, relpath="src/a.c",
                                        signature=f"void {name}(void)",
                                        calls=list(calls))}
    return idx


# ── elf_has_call_tree() probe ────────────────────────────────────────────────

def test_probe_none_parser():
    assert cm.elf_has_call_tree(None) is False


def test_probe_no_functions():
    parser = _mem_parser({})
    assert cm.elf_has_call_tree(parser) is False


def test_probe_real_edges_true():
    # A function whose disassembly recovers a real callee → usable call tree.
    parser = _mem_parser({"main": ["do_work"], "leaf": []})
    assert cm.elf_has_call_tree(parser) is True


def test_probe_raw_address_counts_as_edge():
    # A raw 0x target still proves disassembly worked (Capstone found a CALL).
    parser = _mem_parser({"main": ["0xdeadbeef"]})
    assert cm.elf_has_call_tree(parser) is True


def test_probe_leaf_only_sample_still_true():
    # Disassembly succeeds but every sampled function is a leaf (clean []).
    # The tree is still recoverable — must NOT be mistaken for a broken ELF.
    parser = _mem_parser({"a": [], "b": [], "c": []})
    assert cm.elf_has_call_tree(parser) is True


def test_probe_capstone_unavailable_false():
    parser = _mem_parser({"main": ["Capstone not installed"]})
    assert cm.elf_has_call_tree(parser) is False


def test_probe_et_rel_all_errors_false():
    # ET_REL / unsupported arch: every sample returns a disassembly status string.
    parser = _mem_parser({"a": ["Disassembly error: bad"],
                          "b": ["No instructions disassembled (check architecture/mode)"],
                          "c": ["Could not retrieve function code"],
                          "d": ["Function not found"]})
    assert cm.elf_has_call_tree(parser) is False


def test_probe_et_rel_header_short_circuits(tmp_path):
    # ET_REL relocatable object → reject from the header, never disassemble.
    parser = _mem_parser({"main": ["do_work"]})
    parser.elf_path = _write_elf_header(tmp_path / "obj.o", 1)   # ET_REL
    assert cm.elf_has_call_tree(parser) is False
    parser.extract_subcalls.assert_not_called()


def test_probe_et_exec_header_does_not_short_circuit(tmp_path):
    # ET_EXEC linked executable → header is fine, fall through to disassembly.
    parser = _mem_parser({"main": ["do_work"]})
    parser.elf_path = _write_elf_header(tmp_path / "app.elf", 2)   # ET_EXEC
    assert cm.elf_has_call_tree(parser) is True


def test_probe_et_rel_big_endian(tmp_path):
    parser = _mem_parser({"main": ["do_work"]})
    parser.elf_path = _write_elf_header(tmp_path / "be.o", 1, little=False)
    assert cm.elf_has_call_tree(parser) is False


def test_relocatable_helper_ignores_bad_path():
    # Non-existent / non-ELF path must not raise and must not claim relocatable.
    parser = _mem_parser({"main": []})
    parser.elf_path = "/no/such/file.o"
    assert cm._elf_is_relocatable(parser) is False


def test_probe_db_backed_query():
    # DB-backed parser: names come from elf_functions, ordered by size.
    parser = MagicMock()
    parser._db = MagicMock()
    parser._active_elf_hash = "abc"
    parser._db.execute.return_value.fetchall.return_value = [{"name": "main"}]
    parser.extract_subcalls.side_effect = lambda n: ["callee"] if n == "main" else []
    assert cm.elf_has_call_tree(parser) is True
    # The probe filters on size>0 so leaf-only stubs aren't sampled to death.
    sql = parser._db.execute.call_args[0][0]
    assert "size>0" in sql and "elf_functions" in sql


# ── build_code_map routing ───────────────────────────────────────────────────

def test_prefer_source_skips_disassembly():
    # No usable call tree → use source edges, never call extract_subcalls.
    parser = _mem_parser({"main": ["should_not_appear"]})
    idx = _index("main", ["src_callee"])
    cmap = cm.build_code_map(parser, idx, source_root="x",
                             prefer_source_calls=True)
    main = cmap["functions"]["main"]
    assert main["calls"] == ["src_callee"]
    assert "should_not_appear" not in main["calls"]
    parser.extract_subcalls.assert_not_called()


def test_combine_when_tree_present():
    # Usable call tree → merge source + disassembly edges.
    parser = _mem_parser({"main": ["dwarf_callee"]})
    idx = _index("main", ["src_callee"])
    cmap = cm.build_code_map(parser, idx, source_root="x",
                             prefer_source_calls=False)
    main = cmap["functions"]["main"]
    assert main["calls"] == ["dwarf_callee", "src_callee"]


def test_autodetect_falls_back_to_source():
    # prefer_source_calls=None → auto-probe. All-error parser ⇒ source primary,
    # and the failed disassembly strings never pollute the graph.
    parser = _mem_parser({"main": ["Disassembly error: x"]})
    idx = _index("main", ["src_callee"])
    cmap = cm.build_code_map(parser, idx, source_root="x")
    assert cmap["functions"]["main"]["calls"] == ["src_callee"]


def test_autodetect_uses_disasm_when_tree_present():
    parser = _mem_parser({"main": ["dwarf_callee"]})
    idx = _index("main", ["src_callee"])
    cmap = cm.build_code_map(parser, idx, source_root="x")
    assert set(cmap["functions"]["main"]["calls"]) == {"dwarf_callee", "src_callee"}


def test_noise_strings_filtered_from_edges():
    parser = _mem_parser({"main": ["real_callee", "Function not found",
                                   "Capstone init failed", "0x40"]})
    idx = _index("main", [])
    cmap = cm.build_code_map(parser, idx, source_root="x",
                             prefer_source_calls=False)
    calls = cmap["functions"]["main"]["calls"]
    assert "real_callee" in calls and "0x40" in calls
    assert "Function not found" not in calls
    assert "Capstone init failed" not in calls
