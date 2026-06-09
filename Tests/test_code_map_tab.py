import sys
import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import QtWidgets, QtCore, QtGui

# Setup path
sys.path.append(os.path.abspath("src"))

# Ensure QApplication is initialized
app = QApplication.instance() or QApplication(sys.argv)

from main import ApplicationWindow
from Application_Logic.Logic_Code_Map_Tab import AICodeMapController, MAX_GRAPH_NODES
from UI import widgets_code_map as wcm

def test_code_map_tab_initialization():
    window = ApplicationWindow()
    controller = window.code_map_controller
    assert controller is not None
    
    # Check if tab was added
    tab_index = window.ui.tabWidget.indexOf(controller.tab_widget)
    assert tab_index != -1
    assert window.ui.tabWidget.tabText(tab_index) == "Code Map"
    
    # Check widgets structure
    assert hasattr(controller, "search_input")
    assert hasattr(controller, "func_list")
    assert hasattr(controller, "back_spin")
    assert hasattr(controller, "forward_spin")
    assert hasattr(controller, "code_viewer")
    assert hasattr(controller, "lbl_graph_warning")
    assert hasattr(controller, "scene")
    assert hasattr(controller, "view")
    
    # Check initial values
    assert controller.back_spin.value() == 1
    assert controller.forward_spin.value() == 1
    assert controller.lbl_graph_warning.isHidden() is True
    assert controller.scene.itemIndexMethod() == QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex

def test_code_map_tab_no_data():
    window = ApplicationWindow()
    controller = window.code_map_controller
    
    # 1. No database open
    with patch.object(controller, "_db", return_value=None):
        controller.load_data()
        assert "Open a project database" in controller.code_viewer.placeholderText()
        
    # 2. Database open but no active model
    mock_db = MagicMock()
    mock_arch = MagicMock()
    mock_arch.model_manager = MagicMock()
    mock_arch.model_manager.active_model_id = None
    
    with patch.object(controller, "_db", return_value=mock_db), \
         patch.object(controller, "_arch", return_value=mock_arch):
        controller.load_data()
        assert "No active architecture model selected" in controller.code_viewer.placeholderText()

    # 3. Database has active model but no code map exists
    mock_arch.model_manager.active_model_id = 42
    mock_db.get_model_code_map.return_value = None
    
    with patch.object(controller, "_db", return_value=mock_db), \
         patch.object(controller, "_arch", return_value=mock_arch):
        controller.load_data()
        assert "No Code Map has been generated" in controller.code_viewer.toPlainText()

def test_code_map_tab_load_and_bfs():
    window = ApplicationWindow()
    controller = window.code_map_controller
    
    # Setup mock code map data
    mock_code_map = {
        "functions": {
            "main": {
                "address": 0x1000,
                "size": 128,
                "file": "src/main.c",
                "line_start": 10,
                "calls": ["func_a", "func_b"]
            },
            "func_a": {
                "address": 0x1080,
                "size": 64,
                "file": "src/func_a.c",
                "line_start": 5,
                "calls": ["func_c"]
            },
            "func_b": {
                "address": 0x10C0,
                "size": 32,
                "file": "src/func_b.c",
                "line_start": 20,
                "calls": []
            },
            "func_c": {
                "address": 0x10E0,
                "size": 16,
                "file": "src/func_c.c",
                "line_start": 15,
                "calls": []
            }
        },
        "global_variables": {
            "main_status": "int",
            "func_a_counter": "uint32_t",
            "other_var": "float"
        }
    }
    
    mock_db = MagicMock()
    mock_db.get_model_code_map.return_value = mock_code_map
    mock_arch = MagicMock()
    mock_arch.model_manager.active_model_id = 1
    
    with patch.object(controller, "_db", return_value=mock_db), \
         patch.object(controller, "_arch", return_value=mock_arch):
        
        # Load the data
        controller.load_data()
        
        # Check function list count
        assert controller.func_list.count() == 4
        # Sorted order check
        assert controller.func_list.item(0).text() == "func_a"
        assert controller.func_list.item(3).text() == "main"
        
        # Verify focused function defaults to "main"
        assert controller.focused_func == "main"
        assert controller.lbl_name.text() == "main"
        assert controller.lbl_address.text() == "0x1000"
        assert controller.lbl_size.text() == "128 Bytes"
        
        # Globals filtering check (prefix matching)
        # "main" matches "main_status"
        assert controller.globals_list.count() > 0
        
        # BFS caller/callee scene checks
        # NodeItem + EdgeItem instances in the scene
        items = controller.scene.items()
        nodes = [i for i in items if isinstance(i, wcm.NodeItem)]
        edges = [i for i in items if isinstance(i, wcm.EdgeItem)]
        
        # Depth is 1/1, main -> func_a, func_b.
        # Total nodes: main, func_a, func_b. (func_c is depth 2 callee, shouldn't be included yet)
        assert len(nodes) == 3
        # Edges from main to func_a and func_b: 2 edges
        assert len(edges) == 2
        
        # Increase forward depth to 2
        controller.forward_spin.setValue(2)
        items = controller.scene.items()
        nodes = [i for i in items if isinstance(i, wcm.NodeItem)]
        edges = [i for i in items if isinstance(i, wcm.EdgeItem)]
        
        # Now func_c should be included! Total nodes: main, func_a, func_b, func_c (4 nodes)
        assert len(nodes) == 4
        assert len(edges) == 3 # main->func_a, main->func_b, func_a->func_c
        
        # Filter functions list test
        controller.search_input.setText("func")
        # should hide "main", show others
        assert controller.func_list.item(0).isHidden() is False # func_a
        assert controller.func_list.item(3).isHidden() is True # main
        
        # Clear filter
        controller.search_input.setText("")
        assert controller.func_list.item(3).isHidden() is False

def test_code_map_tab_node_capping():
    window = ApplicationWindow()
    controller = window.code_map_controller
    
    # Setup large code map with 70 nodes
    funcs = {}
    funcs["main"] = {
        "address": 0x1000,
        "size": 10,
        "file": "main.c",
        "line_start": 1,
        "calls": [f"func_{i}" for i in range(70)]
    }
    for i in range(70):
        funcs[f"func_{i}"] = {
            "address": 0x1000 + i*16,
            "size": 5,
            "file": "other.c",
            "line_start": 1,
            "calls": []
        }
        
    mock_code_map = {
        "functions": funcs,
        "global_variables": {}
    }
    
    mock_db = MagicMock()
    mock_db.get_model_code_map.return_value = mock_code_map
    mock_arch = MagicMock()
    mock_arch.model_manager.active_model_id = 1
    
    with patch.object(controller, "_db", return_value=mock_db), \
         patch.object(controller, "_arch", return_value=mock_arch):
        
        # Load and focus main
        controller.load_data()
        
        # Depth is 1 forward, so it should include main + all 70 callees = 71 nodes total.
        # Limit is MAX_GRAPH_NODES (60).
        # Check warning label is visible (not hidden)
        assert controller.lbl_graph_warning.isHidden() is False
        assert f"Truncated display to first {MAX_GRAPH_NODES} nodes" in controller.lbl_graph_warning.text()
        
        # Check scene actually has MAX_GRAPH_NODES nodes
        items = controller.scene.items()
        nodes = [i for i in items if isinstance(i, wcm.NodeItem)]
        assert len(nodes) == MAX_GRAPH_NODES

def test_code_map_tab_source_extraction():
    controller = MagicMock()
    # Test brace matching on extract_function_block_by_line
    # 1. Standard braces
    c_source = """
#include <stdio.h>
void simple_func() {
    printf("hello");
}

void another_func() {
    int x = 1;
}
"""
    extracted = AICodeMapController.extract_function_block_by_line(controller, c_source, 3)
    assert "void simple_func() {" in extracted
    assert "printf(\"hello\");" in extracted
    assert "}" in extracted
    assert "another_func" not in extracted
    
    # 2. Nested braces
    c_source_nested = """
void complex_func() {
    if (1) {
        while (0) {
            do_something();
        }
    }
}
void dummy() {}
"""
    extracted_nested = AICodeMapController.extract_function_block_by_line(controller, c_source_nested, 2)
    assert "void complex_func() {" in extracted_nested
    assert "do_something();" in extracted_nested
    assert extracted_nested.strip().endswith("}")
    assert "dummy" not in extracted_nested
    
    # 3. Malformed braces fallback (extracts 100 lines max)
    c_source_malformed = """
void malformed_func() {
    printf("unclosed";
"""
    extracted_malformed = AICodeMapController.extract_function_block_by_line(controller, c_source_malformed, 2)
    assert "malformed_func" in extracted_malformed
    assert "unclosed" in extracted_malformed

def test_code_map_tab_folder_linking():
    window = ApplicationWindow()
    controller = window.code_map_controller
    
    mock_code_map = {
        "functions": {
            "main": {
                "address": 0x1000,
                "size": 128,
                "file": "src/main.c",
                "line_start": 3,
                "calls": []
            }
        },
        "global_variables": {}
    }
    
    mock_db = MagicMock()
    mock_db.get_model_code_map.return_value = mock_code_map
    mock_arch = MagicMock()
    mock_arch.model_manager.active_model_id = 1
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create a mock source directory structure
        src_dir = os.path.join(tmp_dir, "src")
        os.makedirs(src_dir)
        
        main_c_path = os.path.join(src_dir, "main.c")
        with open(main_c_path, "w") as f:
            f.write("\n\nvoid main() {\n    return;\n}\n")
            
        with patch.object(controller, "_db", return_value=mock_db), \
             patch.object(controller, "_arch", return_value=mock_arch):
            
            # Load data
            controller.load_data()
            
            # Check with no folder linked
            assert "Click 'Link Local Source Folder'" in controller.code_viewer.toPlainText()
            
            # Set folder programmatically
            controller.linked_source_dir = tmp_dir
            controller.lbl_status.setText(f"Linked: {tmp_dir}")
            
            # Load source code
            controller.load_source_code("main")
            
            # Verify code is extracted and displayed
            code_text = controller.code_viewer.toPlainText()
            assert "void main() {" in code_text
            assert "return;" in code_text
            
            # Double-click must DEFER focus_function (focus rebuilds the scene via
            # scene.clear(), which deletes this node mid-event → use-after-free crash)
            # and must NOT call super() afterwards on the navigation path.
            node = wcm.NodeItem(0, 0, 100, 50, "main", "center", controller)
            deferred = []
            fake_event = MagicMock()
            with patch.object(controller, "focus_function") as mock_focus, \
                 patch("PyQt6.QtCore.QTimer.singleShot",
                       side_effect=lambda ms, fn: deferred.append(fn)), \
                 patch("PyQt6.QtWidgets.QGraphicsRectItem.mouseDoubleClickEvent") as mock_super:
                node.mouseDoubleClickEvent(fake_event)
                # Focus is scheduled, not run inline.
                mock_focus.assert_not_called()
                assert len(deferred) == 1
                # Running the scheduled callback performs the focus.
                deferred[0]()
                mock_focus.assert_called_with("main")
                # Event consumed; super() is NOT invoked on the navigation path.
                fake_event.accept.assert_called_once()
                mock_super.assert_not_called()
