import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath("src"))

from Application_Logic import Logic_Code_Map as cm
from Application_Logic.Logic_Code_Index import FunctionInfo, GlobalVarInfo, CodeIndex

def test_demangle_name():
    # Test valid demangling
    assert cm.demangle_name("_ZN6System16doSomethingEntryEv") == "System::doSomethingEntry()"
    # Test invalid demangling (should return original string)
    assert cm.demangle_name("not_mangled_function") == "not_mangled_function"

def test_normalize_cpp_name():
    assert cm.normalize_cpp_name("System::doSomethingEntry()") == "System::doSomethingEntry"
    assert cm.normalize_cpp_name("void System::doSomethingEntry(int)") == "System::doSomethingEntry"
    assert cm.normalize_cpp_name("char* get_name()") == "get_name"

def test_get_base_name():
    assert cm.get_base_name("System::doSomethingEntry") == "doSomethingEntry"
    assert cm.get_base_name("doSomethingEntry") == "doSomethingEntry"

def test_build_code_map_in_memory():
    # 1. Create a mock ELF parser
    mock_parser = MagicMock()
    mock_parser._db = None
    mock_parser._active_elf_hash = None
    
    # Mock symbols and functions inside parser
    mock_func1 = MagicMock()
    mock_func1.name = "DoorControl_Init"
    mock_func1.address = 0x1000
    mock_func1.size = 100
    mock_func1.parameters = []
    mock_func1.return_type = "void"

    mock_func2 = MagicMock()
    mock_func2.name = "_ZN11DoorControl12GetLockStateEv"  # mangled "DoorControl::GetLockState()"
    mock_func2.address = 0x1064
    mock_func2.size = 50
    mock_func2.parameters = []
    mock_func2.return_type = "int"

    mock_parser.functions = [mock_func1, mock_func2]
    mock_parser.global_vars_dwarf = {"g_door_state": "int"}
    
    # Mock extract_subcalls for the parser
    def mock_extract_subcalls(name):
        if name == "DoorControl_Init":
            return ["sub_func_a", "sub_func_b"]
        return []
    mock_parser.extract_subcalls.side_effect = mock_extract_subcalls

    # 2. Create mock C AST index
    code_index = CodeIndex()
    
    # C AST Function 1: exact match
    func_info1 = FunctionInfo(
        name="DoorControl_Init",
        relpath="src/door_control.c",
        return_type="void",
        signature="void DoorControl_Init(void)",
        params=[],
        line_start=10,
        calls=["sub_func_a"]
    )
    
    # C AST Function 2: demangled C++ namespace match
    func_info2 = FunctionInfo(
        name="DoorControl::GetLockState",
        relpath="src/door_control.cpp",
        return_type="int",
        signature="int DoorControl::GetLockState()",
        params=[],
        line_start=30,
        calls=[]
    )
    
    code_index.functions = {
        "DoorControl_Init": func_info1,
        "DoorControl::GetLockState": func_info2
    }
    
    # C AST Global
    var_info = GlobalVarInfo(
        name="g_door_state",
        var_type="int",
        relpath="src/door_control.c"
    )
    code_index.globals = {"g_door_state": var_info}

    # Run build_code_map
    code_map = cm.build_code_map(mock_parser, code_index, source_root="dummy")
    
    assert "functions" in code_map
    assert "global_variables" in code_map
    
    funcs = code_map["functions"]
    globals_dict = code_map["global_variables"]
    
    # Check exact matching function
    assert "DoorControl_Init" in funcs
    f1 = funcs["DoorControl_Init"]
    assert f1["address"] == 0x1000
    assert f1["size"] == 100
    assert f1["file"] == "src/door_control.c"
    # Merged calls: "sub_func_a" from AST and "sub_func_b" from DWARF
    assert "sub_func_a" in f1["calls"]
    assert "sub_func_b" in f1["calls"]
    
    # Check C++ demangled matching function
    assert "DoorControl::GetLockState" in funcs
    f2 = funcs["DoorControl::GetLockState"]
    assert f2["address"] == 0x1064
    assert f2["size"] == 50
    assert f2["file"] == "src/door_control.cpp"
    
    # Check global variables
    assert globals_dict["g_door_state"] == "int"
