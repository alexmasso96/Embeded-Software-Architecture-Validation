"""
Deep coverage for core/elf_parser.py using the bundled ELF fixture
(Tests/Resources/sample.elf, built from sample_elf_source.c).

Covers: full extraction, DWARF parameters/structures/globals, symbol &
address lookups, function-byte reads, capstone subcall extraction, JSON
cache round-trip, and the DB-backed flush/load/streaming/export paths.
"""
import os
import sys
import logging
import tempfile
from pathlib import Path

logging.disable(logging.CRITICAL)
sys.path.append(os.path.abspath("src"))

from core.elf_parser import ELFParser
from Application_Logic.Logic_Database import ProjectDatabase

ELF = str(Path(__file__).parent / "Resources" / "sample.elf")


def _loaded_parser():
    p = ELFParser()
    p.load_elf(ELF)
    p.extract_all()
    return p


# --------------------------------------------------------------------------
# In-memory extraction
# --------------------------------------------------------------------------

def test_extract_all_populates_everything():
    p = _loaded_parser()
    names = {f.name for f in p.functions}
    assert {"add", "sub", "compute", "dist"} <= names
    assert len(p.symbols) > 0
    assert p.md5_hash and len(p.md5_hash) == 32


def test_dwarf_function_parameters():
    p = _loaded_parser()
    by_name = {f.name: f for f in p.functions}
    add_params = by_name["add"].parameters
    assert [pp["name"] for pp in add_params] == ["a", "b"]
    assert all(pp["type"] == "int" for pp in add_params)
    # pointer + const type formatting
    dist_param = by_name["dist"].parameters[0]
    assert dist_param["name"] == "p"
    assert "*" in dist_param["type"]


def test_dwarf_structures_and_globals():
    p = _loaded_parser()
    assert "Point" in p.structures
    field_names = {f["name"] for f in p.structures["Point"]}
    assert {"x", "y"} <= field_names
    assert p.global_vars_dwarf.get("global_counter") == "int"


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------

def test_search_function_exact_fuzzy_and_missing():
    p = _loaded_parser()
    assert [f.name for f in p.search_function("add", exact=True)] == ["add"]
    assert "compute" in [f.name for f in p.search_function("comp")]
    assert p.search_function("does_not_exist", exact=True) == []


def test_get_symbol_by_address():
    p = _loaded_parser()
    sub = p.search_function("sub", exact=True)[0]
    sym = p.get_symbol_by_address(sub.address)
    assert sym is not None
    assert sym.name == "sub"
    # An address with no symbol returns None
    assert p.get_symbol_by_address(0xDEADBEEF) is None


def test_get_function_containing_address():
    p = _loaded_parser()
    add = p.search_function("add", exact=True)[0]
    # An address inside add's body resolves to add
    inside = add.address + max(1, add.size // 2)
    assert p.get_function_containing_address(inside).name == "add"
    # An address far beyond all functions resolves to nothing
    assert p.get_function_containing_address(0x7FFFFFFF) is None


# --------------------------------------------------------------------------
# Disassembly
# --------------------------------------------------------------------------

def test_get_function_bytes():
    p = _loaded_parser()
    add = p.search_function("add", exact=True)[0]
    code = p.get_function_bytes(add)
    assert isinstance(code, (bytes, bytearray))
    assert len(code) > 0


def test_extract_subcalls():
    p = _loaded_parser()
    # Leaf function: no calls
    assert p.extract_subcalls("add") == []
    # Missing function
    assert p.extract_subcalls("nope") == ["Function not found"]
    # A function with a call disassembles without a capstone detail error
    result = p.extract_subcalls("compute")
    assert isinstance(result, list)
    assert not any("error" in str(r).lower() for r in result)


def test_get_statistics_in_memory():
    p = _loaded_parser()
    stats = p.get_statistics()
    assert stats["functions"] >= 4
    assert stats["total_symbols"] >= len(p.functions)


# --------------------------------------------------------------------------
# JSON cache round-trip
# --------------------------------------------------------------------------

def test_save_and_load_cache_roundtrip():
    p = _loaded_parser()
    with tempfile.TemporaryDirectory() as tmp:
        cache = os.path.join(tmp, "cache.json")
        p.save_cache(cache)
        assert os.path.exists(cache)

        p2 = ELFParser()
        assert p2.load_cache(cache) is True
        assert p2.md5_hash == p.md5_hash
        assert {f.name for f in p2.functions} == {f.name for f in p.functions}
        assert "Point" in p2.structures


# --------------------------------------------------------------------------
# DB-backed paths
# --------------------------------------------------------------------------

def test_flush_to_db_and_load_from_db():
    with tempfile.TemporaryDirectory() as tmp:
        db = ProjectDatabase()
        db.open(os.path.join(tmp, "p.arch"))

        p = _loaded_parser()
        h = p.md5_hash
        p.flush_to_db(db)
        assert db.has_elf(h)
        assert "add" in db.get_function_names(h)

        # A fresh parser wired to the DB serves stats without loading RAM lists
        p2 = ELFParser()
        p2.load_from_db(db, h)
        assert p2.symbols == []
        stats = p2.get_statistics()
        assert stats["functions"] >= 4
        # DB-backed subcall path rebuilds the address map from the DB
        assert isinstance(p2.extract_subcalls("add"), list)
        db.close()


def test_extract_all_streaming_to_db():
    with tempfile.TemporaryDirectory() as tmp:
        db = ProjectDatabase()
        db.open(os.path.join(tmp, "p.arch"))

        p = ELFParser()
        p.load_elf(ELF)
        h = p.md5_hash
        p.extract_all_streaming_to_db(db)

        assert db.has_elf(h)
        names = db.get_function_names(h)
        assert {"add", "sub", "compute", "dist"} <= set(names)
        db.close()


def test_export_elf_cache():
    with tempfile.TemporaryDirectory() as tmp:
        db = ProjectDatabase()
        db.open(os.path.join(tmp, "p.arch"))

        p = _loaded_parser()
        h = p.md5_hash
        p.flush_to_db(db)

        out = p.export_elf_cache(tmp)
        assert out is not None
        assert os.path.exists(out)

        # The exported file is loadable by load_cache()
        reloaded = ELFParser()
        assert reloaded.load_cache(out) is True
        assert reloaded.md5_hash == h
        db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
