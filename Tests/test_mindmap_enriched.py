import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath("src"))

from Application_Logic import Logic_AI_Context as ctx
from Application_Logic import Logic_AI_Tools as aitools

def test_mindmap_v2_builder_fields():
    """Verify that build_mind_map correctly embeds structure and global variable fields."""
    ports = [{"name": "P1", "operation": "O1"}]
    reqs = [{"id": "REQ-1", "text": "R1"}]
    
    code_map = {
        "structures": {
            "Config": [{"name": "val", "type": "int"}]
        },
        "global_variables": {
            "g_var": "float"
        }
    }
    
    mm = ctx.build_mind_map(None, "Model_Test", 42, ports, reqs, code_map=code_map)
    
    assert mm["builder_version"] == "2.0"
    assert mm["structures"] == {"Config": [{"name": "val", "type": "int"}]}
    assert mm["global_variables"] == {"g_var": "float"}


def test_render_mind_map_v2():
    """Verify _render_mind_map_v2 bottom-up truncation and section ordering."""
    mm = {
        "builder_version": "2.0",
        "model_name": "Model_Test",
        "ports": {
            "0:P1": {"name": "P1", "operation": "O1", "implementing_funcs": ["f1"]}
        },
        "requirements": {
            "REQ-1": {"text": "Req 1 text", "implementing_funcs": ["f1"]}
        },
        "structures": {
            "Config": [{"name": "val", "type": "int"}]
        },
        "global_variables": {
            "g_var": "float"
        },
        "functions": {
            "f1": {"signature": "void f1(void)", "file": "f1.c"}
        }
    }
    
    # Render with generous budget
    txt = ctx._render_mind_map_v2(mm, budget_chars=4000)
    assert "# MIND MAP v2.0 — Model_Test" in txt
    assert "## PORTS" in txt
    assert "## REQUIREMENTS" in txt
    assert "## STRUCTURES & CLASSES" in txt
    assert "struct Config { val: int }" in txt
    assert "## GLOBAL VARIABLES" in txt
    assert "- float g_var" in txt
    assert "## FUNCTION INDEX" in txt
    assert "void f1(void)  [f1.c]" in txt
    
    # Test bottom-up truncation: function index dropped first when budget is extremely tight
    txt_tight = ctx._render_mind_map_v2(mm, budget_chars=350)
    assert "## PORTS" in txt_tight
    assert "## REQUIREMENTS" in txt_tight
    # Function index should be omitted because of tight budget
    assert "more functions omitted" in txt_tight or "## FUNCTION INDEX" not in txt_tight


def test_mind_map_to_text_dispatch():
    """Verify mind_map_to_text dispatches to correct renderer based on version."""
    mm_v1 = {
        "builder_version": "1.0",
        "model_name": "Model1",
        "ports": {}, "requirements": {}, "functions": {}
    }
    
    mm_v2 = {
        "builder_version": "2.0",
        "model_name": "Model2",
        "ports": {}, "requirements": {}, "structures": {}, "global_variables": {}, "functions": {}
    }
    
    txt_v1 = ctx.mind_map_to_text(mm_v1)
    txt_v2 = ctx.mind_map_to_text(mm_v2)
    
    # V1 shouldn't contain Structures section
    assert "## STRUCTURES & CLASSES" not in txt_v1
    
    # V2 should contain Structures section
    assert "## STRUCTURES & CLASSES" in txt_v2


def test_agent_tools_get_function_and_call_graph():
    """Verify get_function and get_call_graph tools work against database code_map_json."""
    mock_db = MagicMock()
    
    code_map = {
        "functions": {
            "Door_Init": {
                "file": "door.c",
                "line_start": 5,
                "address": 0x1000,
                "size": 50,
                "signature": "void Door_Init(void)",
                "return_type": "void",
                "parameters": [],
                "calls": ["Door_Lock"],
                "reads_vars": ["g_status"],
                "writes_vars": [],
                "conditions": ["if (g_status == 0)"]
            },
            "Door_Lock": {
                "file": "door.c",
                "line_start": 20,
                "address": 0x1050,
                "size": 30,
                "signature": "void Door_Lock(void)",
                "return_type": "void",
                "parameters": [],
                "calls": [],
                "reads_vars": [],
                "writes_vars": ["g_lock_state"],
                "conditions": []
            }
        },
        "global_variables": {
            "g_status": "int",
            "g_lock_state": "int"
        }
    }
    
    mock_db.get_model_code_map.return_value = code_map
    
    executor = aitools.ToolExecutor(source_root="dummy", db=mock_db, model_id=1)
    
    # 1. Test get_function
    func_info = executor.get_function("Door_Init")
    assert "Function: Door_Init" in func_info
    assert "File: door.c" in func_info
    assert "Address: 0x1000" in func_info
    assert "Calls out to:" in func_info
    assert "- Door_Lock" in func_info
    assert "if (g_status == 0)" in func_info
    
    # Test get_function name autocomplete / fallback
    func_info_fuzzy = executor.get_function("init")
    assert "Function: Door_Init" in func_info_fuzzy
    
    # 2. Test get_call_graph forward
    graph_forward = executor.get_call_graph("Door_Init", depth=1, direction="forward")
    assert "Callee Graph for Door_Init" in graph_forward
    assert "-> Door_Lock" in graph_forward
    
    # Test get_call_graph backward
    graph_backward = executor.get_call_graph("Door_Lock", depth=1, direction="backward")
    assert "Caller Graph for Door_Lock" in graph_backward
    assert "<- Door_Init" in graph_backward
