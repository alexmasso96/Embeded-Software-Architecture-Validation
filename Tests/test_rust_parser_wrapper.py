import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath("src"))

from core import elf_parser

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "parser_v2_doorcontrol.json"

def test_map_native_json():
    """Verify that JSON returned by the native parser is correctly mapped to Python properties."""
    with open(FIXTURE_PATH, "r") as f:
        fixture_data = json.load(f)
        
    parser = elf_parser.ELFParser()
    parser._map_native_json(fixture_data)
    
    assert parser.md5_hash == "2ff42460e126b090c5b23945affbd9f0"
    
    # Check symbols
    assert len(parser.symbols) == 3
    assert parser.symbols[0].name == "DoorControl_Init"
    assert parser.symbols[0].address == 1000
    assert parser.symbols[0].symbol_type == "STT_FUNC"
    
    # Check functions
    assert len(parser.functions) == 2
    assert parser.functions[1].name == "DoorControl_Process"
    assert parser.functions[1].parameters == [{"name": "request", "type": "int"}]
    
    # Check structures
    assert "DoorConfig" in parser.structures
    assert parser.structures["DoorConfig"] == [{"name": "timeout", "type": "int"}, {"name": "flags", "type": "unsigned char"}]
    
    # Check global variables
    assert parser.global_vars_dwarf == {"g_door_state": "int"}
    
    # Check func address map
    assert parser._func_addr_map[1000].name == "DoorControl_Init"
    assert parser._func_addr_map[1050].name == "DoorControl_Process"


def test_try_native_extract_success():
    """Verify _try_native_extract calls native parser, maps JSON, and returns True on success."""
    with open(FIXTURE_PATH, "r") as f:
        fixture_data_str = f.read()

    # Mock rust_elf_parser module
    mock_rust = MagicMock()
    mock_rust.parse_elf.return_value = fixture_data_str
    
    with patch("core.elf_parser.RUST_PARSER_AVAILABLE", True), \
         patch("core.elf_parser.rust_elf_parser", mock_rust, create=True):
         
        parser = elf_parser.ELFParser(elf_path="dummy.elf")
        parser.parser_backend = "rust_elf_parser"
        
        result = parser._try_native_extract()
        
        assert result is True
        mock_rust.parse_elf.assert_called_once_with("dummy.elf")
        assert parser.md5_hash == "2ff42460e126b090c5b23945affbd9f0"
        assert len(parser.symbols) == 3


def test_try_native_extract_failure_fallback():
    """Verify _try_native_extract falls back to pyelftools and loads stream on native error."""
    mock_rust = MagicMock()
    mock_rust.parse_elf.side_effect = RuntimeError("Crash in native code")
    
    dummy_file = Path("dummy.elf")
    
    with patch("core.elf_parser.RUST_PARSER_AVAILABLE", True), \
         patch("core.elf_parser.rust_elf_parser", mock_rust, create=True), \
         patch("builtins.open") as mock_open, \
         patch("core.elf_parser.ELFParser._load_elf_file") as mock_load_elf:
         
        parser = elf_parser.ELFParser(elf_path=str(dummy_file))
        parser.parser_backend = "rust_elf_parser"
        
        # We need mock_open to return some fake bytes
        mock_file = MagicMock()
        mock_file.read.return_value = b"ELF HEADER BYTES"
        mock_open.return_value.__enter__.return_value = mock_file
        
        result = parser._try_native_extract()
        
        assert result is False
        assert parser.parser_backend == "pyelftools"
        mock_load_elf.assert_called_once()


def test_extract_all_streaming_to_db_native_success():
    """Verify native streaming to db inserts all parsed data directly and bypasses DWARF walk."""
    with open(FIXTURE_PATH, "r") as f:
        fixture_data_str = f.read()

    mock_rust = MagicMock()
    mock_rust.parse_elf.return_value = fixture_data_str
    
    mock_db = MagicMock()
    mock_db.has_elf.return_value = False
    
    with patch("core.elf_parser.RUST_PARSER_AVAILABLE", True), \
         patch("core.elf_parser.rust_elf_parser", mock_rust, create=True):
         
        parser = elf_parser.ELFParser(elf_path="dummy.elf")
        parser.md5_hash = "2ff42460e126b090c5b23945affbd9f0"
        parser.parser_backend = "rust_elf_parser"
        
        parser.extract_all_streaming_to_db(mock_db)
        
        mock_db.register_elf.assert_called_once_with("2ff42460e126b090c5b23945affbd9f0", "dummy.elf", "rust_elf_parser")
        mock_db.bulk_insert_symbols.assert_called_once()
        mock_db.bulk_insert_functions.assert_called_once()
        mock_db.bulk_insert_structures.assert_called_once()
        mock_db.bulk_insert_global_vars.assert_called_once()
        mock_db.commit.assert_called_once()


def test_load_elf_native_md5():
    """Verify load_elf uses native compute_md5 directly and trusts it."""
    mock_rust = MagicMock()
    mock_rust.compute_md5.return_value = "2ff42460e126b090c5b23945affbd9f0"
    
    dummy_file = Path("dummy.elf")
    
    with patch("core.elf_parser.RUST_PARSER_AVAILABLE", True), \
         patch("core.elf_parser.rust_elf_parser", mock_rust, create=True), \
         patch.object(Path, "exists", return_value=True):
         
        parser = elf_parser.ELFParser()
        parser.load_elf(str(dummy_file))
        
        assert parser.md5_hash == "2ff42460e126b090c5b23945affbd9f0"
        assert parser.parser_backend == "rust_elf_parser"
        mock_rust.compute_md5.assert_called_once_with(str(dummy_file))
        # Ensure we didn't open the file in Python (which happens in fallback path)
        assert parser.stream is None


def test_interrupted_import_recovery():
    """Verify that when parsing an ELF, delete_elf is called first to clean up partial records,
    and register_elf is only called after all data blocks are inserted."""
    with open(FIXTURE_PATH, "r") as f:
        fixture_data_str = f.read()

    mock_rust = MagicMock()
    mock_rust.parse_elf.return_value = fixture_data_str
    
    mock_db = MagicMock()
    mock_db.has_elf.return_value = False
    
    call_order = []
    
    # Track the call order of database operations
    mock_db.delete_elf.side_effect = lambda h: call_order.append(("delete", h))
    mock_db.bulk_insert_symbols.side_effect = lambda h, s: call_order.append(("symbols", h))
    mock_db.bulk_insert_functions.side_effect = lambda h, f: call_order.append(("functions", h))
    mock_db.register_elf.side_effect = lambda h, p, b=None: call_order.append(("register", h))
    
    with patch("core.elf_parser.RUST_PARSER_AVAILABLE", True), \
         patch("core.elf_parser.rust_elf_parser", mock_rust, create=True):
         
        parser = elf_parser.ELFParser(elf_path="dummy.elf")
        parser.md5_hash = "2ff42460e126b090c5b23945affbd9f0"
        parser.parser_backend = "rust_elf_parser"
        
        parser.extract_all_streaming_to_db(mock_db)
        
        # Verify call order
        assert len(call_order) >= 4
        assert call_order[0] == ("delete", "2ff42460e126b090c5b23945affbd9f0")
        
        # Verify register is after bulk insertions
        reg_idx = [i for i, x in enumerate(call_order) if x[0] == "register"][0]
        sym_idx = [i for i, x in enumerate(call_order) if x[0] == "symbols"][0]
        func_idx = [i for i, x in enumerate(call_order) if x[0] == "functions"][0]
        
        assert reg_idx > sym_idx
        assert reg_idx > func_idx
