import json
import logging
import os
from collections import deque
from typing import Optional

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor

from UI import widgets_code_map as wcm

logger = logging.getLogger(__name__)

MAX_GRAPH_NODES = 60


class AICodeMapController(QtCore.QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ui = main_window.ui
        
        self.dataset = None
        self.callers_map = {}
        self.focused_func = None
        self.linked_source_dir = None
        
        self.scene = QtWidgets.QGraphicsScene()
        # Disable BSP indexing to speed up scene modifications on large graphs
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        
        self.tab_widget = QtWidgets.QWidget()
        self._tab_index = self.ui.tabWidget.addTab(self.tab_widget, "Code Map")
        self._build_ui()
        
    def _db(self):
        return getattr(self.main_window, "project_db", None)

    def _arch(self):
        return getattr(self.main_window, "arch_controller", None)

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self.tab_widget)
        outer.setContentsMargins(12, 12, 12, 12)
        
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        outer.addWidget(splitter)
        
        # 1. Left Panel (Sidebar)
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)
        
        # Search Box
        search_group = QtWidgets.QGroupBox("Search")
        search_layout = QtWidgets.QVBoxLayout(search_group)
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Type function name...")
        self.search_input.textChanged.connect(self.filter_functions)
        search_layout.addWidget(self.search_input)
        
        self.func_list = QtWidgets.QListWidget()
        self.func_list.itemClicked.connect(self.on_item_clicked)
        search_layout.addWidget(self.func_list)
        left_layout.addWidget(search_group)
        
        # Graph Depth Controls
        depth_group = QtWidgets.QGroupBox("Graph Depth")
        depth_layout = QtWidgets.QFormLayout(depth_group)
        self.back_spin = QtWidgets.QSpinBox()
        self.back_spin.setRange(1, 5)
        self.back_spin.setValue(1)
        self.back_spin.valueChanged.connect(self.rebuild_graph)
        
        self.forward_spin = QtWidgets.QSpinBox()
        self.forward_spin.setRange(1, 5)
        self.forward_spin.setValue(1)
        self.forward_spin.valueChanged.connect(self.rebuild_graph)
        
        depth_layout.addRow(QtWidgets.QLabel("Backward (Callers):"), self.back_spin)
        depth_layout.addRow(QtWidgets.QLabel("Forward (Callees):"), self.forward_spin)
        left_layout.addWidget(depth_group)
        
        # Details Panel
        details_group = QtWidgets.QGroupBox("Function Details")
        details_layout = QtWidgets.QFormLayout(details_group)
        self.lbl_name = QtWidgets.QLabel("--")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setStyleSheet("font-weight: bold; color: #FFFFFF;")
        self.lbl_address = QtWidgets.QLabel("--")
        self.lbl_size = QtWidgets.QLabel("--")
        self.lbl_callers = QtWidgets.QLabel("--")
        self.lbl_callees = QtWidgets.QLabel("--")
        
        details_layout.addRow(QtWidgets.QLabel("Name:"), self.lbl_name)
        details_layout.addRow(QtWidgets.QLabel("Address:"), self.lbl_address)
        details_layout.addRow(QtWidgets.QLabel("Size:"), self.lbl_size)
        details_layout.addRow(QtWidgets.QLabel("Called By:"), self.lbl_callers)
        details_layout.addRow(QtWidgets.QLabel("Calls Out:"), self.lbl_callees)
        left_layout.addWidget(details_group)
        
        # Globals
        globals_group = QtWidgets.QGroupBox("Matched Globals")
        globals_layout = QtWidgets.QVBoxLayout(globals_group)
        self.globals_list = QtWidgets.QListWidget()
        globals_layout.addWidget(self.globals_list)
        left_layout.addWidget(globals_group)
        
        # 2. Central Panel (Graph View + Warning Banner)
        center_widget = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        self.lbl_graph_warning = QtWidgets.QLabel("")
        self.lbl_graph_warning.setStyleSheet("background-color: #8C1D40; color: white; padding: 6px; font-weight: bold;")
        self.lbl_graph_warning.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_graph_warning.setVisible(False)
        center_layout.addWidget(self.lbl_graph_warning)
        
        self.view = wcm.GraphView(self.scene, center_widget)
        center_layout.addWidget(self.view)
        
        # 3. Right Panel (Code view & local search)
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)
        
        # Folder Mapping Group
        folder_group = QtWidgets.QGroupBox("C Source Code Mapping")
        folder_layout = QtWidgets.QVBoxLayout(folder_group)
        self.btn_select_dir = QtWidgets.QPushButton("Link Local Source Folder…")
        self.btn_select_dir.clicked.connect(self.select_source_directory)
        folder_layout.addWidget(self.btn_select_dir)

        self.btn_rebuild_map = QtWidgets.QPushButton("Index & Rebuild Code Map")
        self.btn_rebuild_map.clicked.connect(self.rebuild_code_map_from_linked_folder)
        folder_layout.addWidget(self.btn_rebuild_map)
        
        self.lbl_status = QtWidgets.QLabel("No source folder linked.")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        folder_layout.addWidget(self.lbl_status)
        right_layout.addWidget(folder_group)
        
        # Monospace Text Box
        self.code_viewer = QtWidgets.QPlainTextEdit()
        self.code_viewer.setReadOnly(True)
        self.code_viewer.setPlaceholderText("// Source code will appear here after linking a local source folder...")
        
        self.highlighter = wcm.CSyntaxHighlighter(self.code_viewer.document())
        right_layout.addWidget(self.code_viewer)
        
        # Add widgets to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(center_widget)
        splitter.addWidget(right_panel)
        
        splitter.setSizes([320, 600, 580])

    def on_tab_changed(self, index):
        if self.ui.tabWidget.widget(index) is not self.tab_widget:
            return
        self.load_data()

    def load_data(self):
        db = self._db()
        arch = self._arch()
        if not db or not arch:
            self.code_viewer.setPlaceholderText("// Open a project database to load the Code Map.")
            return
            
        # Get active model
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if active_model_id is None:
            self.code_viewer.setPlaceholderText("// No active architecture model selected.")
            return
            
        code_map = db.get_model_code_map(active_model_id)
        if not code_map or "functions" not in code_map:
            self.dataset = None
            self.func_list.clear()
            self.lbl_name.setText("--")
            self.scene.clear()
            self.code_viewer.setPlainText(
                "// No Code Map has been generated for this model.\n"
                "// Go to the 'Advanced AI Chat' tab and click 'Generate Mind Map' first."
            )
            return
            
        self.dataset = code_map
        
        # Build callers map
        self.callers_map = {fName: set() for fName in self.dataset["functions"]}
        for fName, fData in self.dataset["functions"].items():
            calls = fData.get("calls", [])
            for target in calls:
                if target not in self.callers_map:
                    self.callers_map[target] = set()
                self.callers_map[target].add(fName)
                
        self.func_list.clear()
        fNames = sorted(self.dataset["functions"].keys())
        for name in fNames:
            self.func_list.addItem(name)
            
        default_focus = "main" if "main" in self.dataset["functions"] else fNames[0]
        self.focus_function(default_focus)

    def filter_functions(self):
        query = self.search_input.text().lower().strip()
        for i in range(self.func_list.count()):
            item = self.func_list.item(i)
            item.setHidden(query not in item.text().lower())

    def on_item_clicked(self, item):
        self.focus_function(item.text())

    def focus_function(self, fName):
        if not self.dataset or fName not in self.dataset["functions"]:
            return
            
        self.focused_func = fName
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.filter_functions()
        self.search_input.blockSignals(False)
        
        items = self.func_list.findItems(fName, Qt.MatchFlag.MatchExactly)
        if items:
            self.func_list.setCurrentItem(items[0])
            
        fData = self.dataset["functions"][fName]
        callers = list(self.callers_map.get(fName, []))
        callees = fData.get("calls", [])
        
        self.lbl_name.setText(fName)
        addr = fData.get("address", 0)
        self.lbl_address.setText(hex(addr) if isinstance(addr, int) else str(addr))
        self.lbl_size.setText(f"{fData.get('size', 0)} Bytes")
        self.lbl_callers.setText(str(len(callers)))
        self.lbl_callees.setText(str(len(callees)))
        
        self.update_globals(fName)
        self.rebuild_graph()
        self.load_source_code(fName)

    def update_globals(self, fName):
        self.globals_list.clear()
        prefix = fName.split('_')[0] + '_' if '_' in fName else fName[:3]
        
        matched = []
        for var_name, var_type in self.dataset.get("global_variables", {}).items():
            if var_name.startswith(prefix):
                matched.append((var_name, var_type))
                
        for name, dtype in sorted(matched)[:50]:
            item = QtWidgets.QListWidgetItem(self.globals_list)
            widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(widget)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(2)
            
            lbl_name = QtWidgets.QLabel(name)
            lbl_name.setStyleSheet("font-family: monospace; font-weight: bold; color: #CBD5E1;")
            lbl_type = QtWidgets.QLabel(dtype)
            lbl_type.setStyleSheet("font-family: monospace; font-size: 11px; color: #6B7280;")
            
            layout.addWidget(lbl_name)
            layout.addWidget(lbl_type)
            
            item.setSizeHint(widget.sizeHint())
            self.globals_list.setItemWidget(item, widget)

    def select_source_directory(self):
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select C/C++ Source Code Directory", "",
            options=QtWidgets.QFileDialog.Option(0)
        )
        if not dir_path:
            return
        self.linked_source_dir = dir_path
        self.lbl_status.setText(f"Linked: {dir_path}")
        if self.focused_func:
            self.load_source_code(self.focused_func)

    def rebuild_code_map_from_linked_folder(self):
        db = self._db()
        arch = self._arch()
        if not db or not arch or not getattr(arch, 'parser', None):
            QtWidgets.QMessageBox.warning(self.main_window, "Rebuild Code Map", "No project database or symbols loaded.")
            return
            
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if active_model_id is None:
            QtWidgets.QMessageBox.warning(self.main_window, "Rebuild Code Map", "No active architecture model.")
            return

        # Build code index from the linked source folder if exists
        code_index = None
        if self.linked_source_dir and os.path.exists(self.linked_source_dir):
            from Application_Logic.Logic_Code_Index import build_index
            code_index = build_index(self.linked_source_dir)
            
        try:
            from Application_Logic.Logic_Code_Map import build_code_map
            code_map = build_code_map(arch.parser, code_index, source_root=self.linked_source_dir or "")
            db.save_model_code_map(active_model_id, json.dumps(code_map))
            self.load_data() # Reload visual explorer
            QtWidgets.QMessageBox.information(
                self.main_window, "Success",
                "Code Map successfully rebuilt and saved locally!"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.main_window, "Error", f"Failed to rebuild Code Map:\n{e}")

    def load_source_code(self, fName):
        if not self.linked_source_dir:
            self.code_viewer.setPlainText(
                f"// Source code of '{fName}' not found.\n"
                f"// Click 'Link Local Source Folder' to point to your C files."
            )
            return
            
        fData = self.dataset["functions"].get(fName)
        if not fData or not fData.get("file"):
            self.code_viewer.setPlainText(f"// No source file metadata available for {fName}.")
            return
            
        rel_path = fData["file"]
        full_path = os.path.join(self.linked_source_dir, rel_path)
        if not os.path.exists(full_path):
            base_name = os.path.basename(rel_path)
            found_path = None
            for root, _, files in os.walk(self.linked_source_dir):
                if base_name in files:
                    found_path = os.path.join(root, base_name)
                    break
            if found_path:
                full_path = found_path
            else:
                self.code_viewer.setPlainText(f"// Source file not found: {rel_path} under {self.linked_source_dir}")
                return
                
        line_start = fData.get("line_start", 1)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                
            code_block = self.extract_function_block_by_line(content, line_start)
            header = f"// File: {os.path.basename(full_path)} | Line: {line_start}\n\n"
            self.code_viewer.setPlainText(header + code_block)
        except Exception as e:
            self.code_viewer.setPlainText(f"// Error reading file:\n// {e}")

    def extract_function_block_by_line(self, content, line_start):
        lines = content.splitlines()
        start_line_idx = max(0, line_start - 1)
        sub_content = "\n".join(lines[start_line_idx:])
        
        brace_count = 0
        in_braces = False
        
        for idx, char in enumerate(sub_content):
            if char == '{':
                brace_count += 1
                in_braces = True
            elif char == '}':
                brace_count -= 1
                
            if in_braces and brace_count == 0:
                return sub_content[:idx+1]
                
        return "\n".join(lines[start_line_idx:start_line_idx+100])

    def rebuild_graph(self):
        if not self.focused_func or not self.dataset:
            return
            
        self.scene.clear()
        
        back_depth = self.back_spin.value()
        forward_depth = self.forward_spin.value()
        
        level_nodes = {0: [self.focused_func]}
        node_levels = {self.focused_func: 0}
        
        # Forward BFS (callees)
        queue = deque([(self.focused_func, 0)])
        while queue:
            node, d = queue.popleft()
            if d >= forward_depth:
                continue
            
            callees = self.dataset["functions"].get(node, {}).get("calls", [])
            for c in callees:
                if c not in node_levels:
                    node_levels[c] = d + 1
                    if (d + 1) not in level_nodes:
                        level_nodes[d + 1] = []
                    level_nodes[d + 1].append(c)
                    queue.append((c, d + 1))
                    
        # Backward BFS (callers)
        queue = deque([(self.focused_func, 0)])
        while queue:
            node, d = queue.popleft()
            if d >= back_depth:
                continue
                
            callers = self.callers_map.get(node, [])
            for c in callers:
                if c not in node_levels:
                    lvl = -(d + 1)
                    node_levels[c] = lvl
                    if lvl not in level_nodes:
                        level_nodes[lvl] = []
                    level_nodes[lvl].append(c)
                    queue.append((c, d + 1))
                    
        # Check node count limit and apply mitigation
        total_nodes = len(node_levels)
        if total_nodes > MAX_GRAPH_NODES:
            self.lbl_graph_warning.setText(
                f"Warning: Call graph contains {total_nodes} nodes (exceeds performance threshold). "
                f"Truncated display to first {MAX_GRAPH_NODES} nodes."
            )
            self.lbl_graph_warning.setVisible(True)
            
            # Prune node list to MAX_GRAPH_NODES
            nodes_kept = set()
            count = 0
            # Keep center first
            nodes_kept.add(self.focused_func)
            count += 1
            
            # Keep callers and callees proportionally
            all_other_nodes = [n for n in node_levels if n != self.focused_func]
            for n in all_other_nodes:
                if count >= MAX_GRAPH_NODES:
                    break
                nodes_kept.add(n)
                count += 1
                
            # Filter level_nodes
            for lvl in list(level_nodes.keys()):
                level_nodes[lvl] = [n for n in level_nodes[lvl] if n in nodes_kept]
                if not level_nodes[lvl]:
                    del level_nodes[lvl]
                    
            # Update node_levels
            node_levels = {n: lvl for n, lvl in node_levels.items() if n in nodes_kept}
        else:
            self.lbl_graph_warning.setVisible(False)

        # Layout configuration
        spacing_x = 350
        spacing_y = 65
        box_width = 240
        box_height = 42
        
        node_positions = {}
        
        for lvl, nodes in level_nodes.items():
            col_x = lvl * spacing_x
            n_count = len(nodes)
            for idx, node in enumerate(nodes):
                col_y = (idx - (n_count - 1) / 2.0) * spacing_y
                node_positions[node] = QPointF(col_x, col_y)
                
                if lvl == 0:
                    ntype = "center"
                elif lvl < 0:
                    ntype = "caller"
                else:
                    ntype = "callee"
                    
                rect_item = wcm.NodeItem(col_x, col_y, box_width, box_height, node, ntype, self)
                self.scene.addItem(rect_item)
                
        # Draw edges
        edge_color_caller = QColor("#0072FF")
        edge_color_callee = QColor("#D383FC")
        
        for u in node_positions:
            calls = self.dataset["functions"].get(u, {}).get("calls", [])
            for v in calls:
                if v in node_positions:
                    start_pos = QPointF(node_positions[u].x() + box_width/2, node_positions[u].y())
                    end_pos = QPointF(node_positions[v].x() - box_width/2, node_positions[v].y())
                    
                    lvl_v = node_levels[v]
                    color = edge_color_callee if lvl_v >= 0 else edge_color_caller
                    
                    edge_item = wcm.EdgeItem(start_pos, end_pos, color)
                    self.scene.addItem(edge_item)
                    
        self.view.centerOn(0, 0)
