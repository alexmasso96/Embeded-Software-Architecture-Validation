"""
Code Map tab controller (Qt) — moved out of Application_Logic/
Logic_Code_Map_Tab.py in Phase 0 of the pywebview migration. The build job,
graph traversal, and symbol lookup live there as pure functions; this
controller is widget glue and retires with the PyQt UI in Phase 4.
"""
import logging
import os

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QColor, QTextCursor, QTextCharFormat

from UI import widgets_code_map as wcm
from Application_Logic.Logic_Code_Map_Tab import (
    MAX_GRAPH_NODES,
    build_code_map_job,
    build_callers_map,
    compute_graph_levels,
    describe_symbol,
    extract_function_block_by_line,
    is_known_function,
)

logger = logging.getLogger(__name__)


class _CodeMapWorker(QtCore.QThread):
    """Thin Qt thread around the pure ``build_code_map_job`` — relays its
    progress callback as a queued signal onto the GUI thread."""
    progress = QtCore.pyqtSignal(str)
    finished_ok = QtCore.pyqtSignal(object)   # code_map dict
    failed = QtCore.pyqtSignal(str)

    def __init__(self, db_path, elf_hash, elf_path, source_dir, model_id,
                 release_id=None, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.elf_hash = elf_hash
        self.elf_path = elf_path
        self.source_dir = source_dir
        self.model_id = model_id
        self.release_id = release_id   # #2E: pin the release the map belongs to

    def run(self):
        try:
            code_map = build_code_map_job(
                self.db_path, self.elf_hash, self.elf_path, self.source_dir,
                self.model_id, self.release_id, progress_cb=self.progress.emit)
            self.finished_ok.emit(code_map)
        except Exception as e:  # noqa: BLE001 — surface any failure to the UI
            self.failed.emit(str(e))


class AICodeMapController(QtCore.QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ui = main_window.ui

        self.dataset = None
        self.callers_map = {}
        self.focused_func = None
        self.linked_source_dir = None
        self._cm_worker = None
        self._cm_active_model_id = None
        self.graph_overlay = None

        self.scene = QtWidgets.QGraphicsScene()
        # Disable BSP indexing to speed up scene modifications on large graphs
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)

        self.tab_widget = QtWidgets.QWidget()
        self._tab_index = self.ui.tabWidget.addTab(self.tab_widget, "Code Map")
        self._build_ui()

        appins = QtWidgets.QApplication.instance()
        if appins is not None:
            appins.aboutToQuit.connect(self._cleanup)

    def _cleanup(self):
        w = self._cm_worker
        if w is not None and w.isRunning():
            w.requestInterruption()
            w.wait(3000)

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

        # #2E: source is chosen by RELEASE (read from the DB). The local-folder link
        # below remains as a fallback for releases without imported source.
        folder_layout.addWidget(QtWidgets.QLabel("Source release:"))
        self.cmb_release = QtWidgets.QComboBox()
        self.cmb_release.currentIndexChanged.connect(self._on_release_changed)
        folder_layout.addWidget(self.cmb_release)

        self.btn_select_dir = QtWidgets.QPushButton("Link Local Folder (fallback)…")
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

        # #2D: IDE-style hover tooltips + Ctrl/Cmd-click navigation. Mouse tracking
        # lets us react to bare moves (no button held) so the link affordance can
        # follow the cursor; one event filter on the viewport drives all of it.
        self.code_viewer.setMouseTracking(True)
        self.code_viewer.viewport().setMouseTracking(True)
        self.code_viewer.viewport().installEventFilter(self)

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
        self._refresh_release_combo()
        self.load_data()

    # ------------------------------------------------------------------
    # #2E — source release selection
    # ------------------------------------------------------------------
    def _refresh_release_combo(self):
        from Application_Logic.Logic_Release_Source_Picker import populate_release_combo
        db = self._db()
        arch = self._arch()
        rm = getattr(arch, "release_manager", None) if arch else None
        if rm is None:
            return
        source_ids = db.get_release_ids_with_source() if db else set()
        prefer = db.get_active_release_id() if db else None
        populate_release_combo(self.cmb_release, rm, prefer_id=prefer,
                               source_ids=source_ids)

    def _selected_release_id(self):
        rid = self.cmb_release.currentData()
        if rid is not None:
            return rid
        db = self._db()
        return db.get_active_release_id() if db else None

    def _on_release_changed(self, _idx=0):
        # Show the selected release's code map + source.
        self.load_data()

    def apply_edit_mode(self, enabled: bool):
        """View-Only: disable the code-map rebuild (it writes to the DB). Linking a
        local source folder stays enabled — it only feeds the read-only source view
        and its meta write is skipped by the read-only guard."""
        if hasattr(self, "btn_rebuild_map"):
            self.btn_rebuild_map.setEnabled(enabled)
            self.btn_rebuild_map.setToolTip(
                "" if enabled else "Disabled in View-Only mode — acquire the edit lock to rebuild.")

    def load_data(self):
        db = self._db()
        arch = self._arch()
        if not db or not arch:
            self.code_viewer.setPlaceholderText("// Open a project database to load the Code Map.")
            return

        # Recovery: restore the linked source folder, and surface a hint if a prior
        # indexing run was interrupted (crash) so the user knows to rebuild.
        saved_dir = db.get_meta("code_map_source_dir", "")
        if isinstance(saved_dir, str) and saved_dir and not self.linked_source_dir:
            self.linked_source_dir = saved_dir
            self.lbl_status.setText(f"Linked: {saved_dir}")
        if db.get_meta("code_map_index_state", "") == "in_progress":
            self.lbl_status.setText(
                "⚠ Previous Code Map indexing was interrupted — click "
                "'Index & Rebuild Code Map' to finish it.")

        # Get active model
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if active_model_id is None:
            self.code_viewer.setPlaceholderText("// No active architecture model selected.")
            return

        code_map = db.get_model_code_map(active_model_id, release_id=self._selected_release_id())
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
        self.callers_map = build_callers_map(self.dataset["functions"])

        # Build the selector from real functions only. Defensive at display time so
        # even code maps saved before the parser-level filter (compiler internals,
        # data/type symbols) show a clean list without needing a rebuild.
        from core.elf_parser import keep_function_name
        data_names = set(self.dataset.get("global_variables", {})) | set(self.dataset.get("structures", {}))
        self.func_list.clear()
        fNames = [n for n in sorted(self.dataset["functions"].keys())
                  if keep_function_name(n) and n not in data_names]
        for name in fNames:
            self.func_list.addItem(name)

        if not fNames:
            self.lbl_name.setText("--")
            self.scene.clear()
            self.code_viewer.setPlainText("// No functions to display for this model.")
            return
        default_focus = "main" if "main" in fNames else fNames[0]
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

    # ------------------------------------------------------------------
    # #2D — IDE features: hover tooltips + Ctrl/Cmd-click navigation
    # ------------------------------------------------------------------
    def _word_at(self, pos):
        """Identifier under a viewport QPoint, or '' if none."""
        cursor = self.code_viewer.cursorForPosition(pos)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor.selectedText().strip()

    def _is_known_function(self, word):
        """True if `word` is a function in the loaded code map."""
        return is_known_function(self.dataset, word)

    def describe_symbol(self, word):
        """HTML tooltip for `word`, or None — delegates to the pure logic fn."""
        return describe_symbol(self.dataset, word)

    def eventFilter(self, obj, event):
        # An installed filter can still be invoked while the controller/widget is
        # being torn down (Qt delivers Leave/Hide events during destruction, after
        # Python has begun clearing this object). Guard against the missing attr and
        # an already-deleted C++ viewport so teardown never raises.
        viewer = getattr(self, "code_viewer", None)
        if viewer is None:
            return False
        try:
            is_viewport = obj is viewer.viewport()
        except RuntimeError:   # wrapped C++ object already deleted
            return False
        if is_viewport:
            etype = event.type()
            if etype == QEvent.Type.ToolTip:
                return self._handle_tooltip(event)
            if etype == QEvent.Type.MouseMove:
                self._handle_link_hover(event)
                return False
            if etype == QEvent.Type.MouseButtonPress:
                return self._handle_ctrl_click(event)
            if etype == QEvent.Type.Leave:
                self._clear_link_affordance()
                return False
        return super().eventFilter(obj, event)

    def _handle_tooltip(self, event):
        text = self.describe_symbol(self._word_at(event.pos()))
        if text:
            QtWidgets.QToolTip.showText(event.globalPos(), text, self.code_viewer)
            return True
        QtWidgets.QToolTip.hideText()
        return False

    def _handle_ctrl_click(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            word = self._word_at(event.position().toPoint())
            if self._is_known_function(word):
                self._clear_link_affordance()
                self.focus_function(word)
                return True   # consume — don't just move the caret
        return False

    def _handle_link_hover(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._clear_link_affordance()
            return
        pt = event.position().toPoint()
        if self._is_known_function(self._word_at(pt)):
            self.code_viewer.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self._underline_word_at(pt)
        else:
            self._clear_link_affordance()

    def _clear_link_affordance(self):
        self.code_viewer.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.code_viewer.setExtraSelections([])

    def _underline_word_at(self, pt):
        cursor = self.code_viewer.cursorForPosition(pt)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        sel = QtWidgets.QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(True)
        fmt.setForeground(QColor("#60A5FA"))
        sel.format = fmt
        sel.cursor = cursor
        self.code_viewer.setExtraSelections([sel])

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
        # Persist immediately so the link survives a crash/restart (recovery).
        db = self._db()
        if db:
            db.set_meta("code_map_source_dir", dir_path)
            db.commit()
        if self.focused_func:
            self.load_source_code(self.focused_func)

    # ------------------------------------------------------------------
    # In-pane "working" overlay over the graph view (non-modal — avoids the
    # LoadingDialog app-modal pitfall).
    # ------------------------------------------------------------------
    def _show_graph_overlay(self, text):
        if self.graph_overlay is None:
            self.graph_overlay = QtWidgets.QLabel(self.view)
            self.graph_overlay.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.graph_overlay.setWordWrap(True)
            self.graph_overlay.setStyleSheet(
                "background-color: rgba(20, 18, 33, 220); color: #E5E7EB;"
                " font-size: 15px; font-weight: bold; padding: 16px;")
        self.graph_overlay.setText(text)
        self.graph_overlay.setGeometry(self.view.rect())
        self.graph_overlay.show()
        self.graph_overlay.raise_()

    def _hide_graph_overlay(self):
        if self.graph_overlay is not None:
            self.graph_overlay.hide()

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

        if self._cm_worker is not None and self._cm_worker.isRunning():
            return

        parser = arch.parser
        elf_hash = getattr(parser, "_active_elf_hash", None) or getattr(parser, "md5_hash", None)
        elf_path = str(getattr(parser, "elf_path", "") or "")

        # Persist the source location + mark indexing in-progress BEFORE the worker
        # starts (still single-threaded here, so this main-connection write is safe).
        # If the app crashes mid-index, load_data() finds the folder linked and warns.
        if self.linked_source_dir:
            db.set_meta("code_map_source_dir", self.linked_source_dir)
        db.set_meta("code_map_index_state", "in_progress")
        db.set_activity("codemap", "in_progress")
        db.commit()

        # Light gate: pause auto-save so the main connection stays quiet during the
        # build (reduces lock contention). Crash-safety itself comes from the worker
        # using its OWN connection, so we don't need to freeze the whole UI.
        self.main_window._codemap_building = True

        self._cm_active_model_id = active_model_id
        self.btn_rebuild_map.setEnabled(False)
        self._show_graph_overlay("Generating Code Map…")

        # #2E: pin the map to the SELECTED release (captured here on the main thread
        # so a release switch mid-build can't mis-key the saved map). The worker
        # reads that release's DB source on its own connection, else the linked folder.
        release_id = self._selected_release_id()

        # Hand the worker raw values (path/hash), NOT the shared parser/connection.
        self._cm_worker = _CodeMapWorker(
            db.db_path, elf_hash, elf_path, self.linked_source_dir, active_model_id,
            release_id, self)
        self._cm_worker.progress.connect(self._show_graph_overlay)
        self._cm_worker.finished_ok.connect(self._on_codemap_done)
        self._cm_worker.failed.connect(self._on_codemap_failed)
        self._cm_worker.start()

    def _finish_codemap(self):
        """Common teardown after a build finishes (success or failure)."""
        self.main_window._codemap_building = False
        db = self._db()
        if db:
            try:
                db.set_activity("", "idle")
            except Exception:
                pass
        self._hide_graph_overlay()
        self.btn_rebuild_map.setEnabled(True)

    def _on_codemap_done(self, code_map):
        # The worker already saved + committed the map on its own connection
        # (durable already). Just present it — load_data() reads it back.
        self._finish_codemap()
        self.load_data()   # silently present the map

    def _on_codemap_failed(self, msg):
        db = self._db()
        if db:
            try:
                db.set_meta("code_map_index_state", "failed")
                db.commit()
            except Exception:
                pass
        self._finish_codemap()
        QtWidgets.QMessageBox.critical(self.main_window, "Error", f"Failed to rebuild Code Map:\n{msg}")

    def load_source_code(self, fName):
        fData = self.dataset["functions"].get(fName) if self.dataset else None
        if not fData or not fData.get("file"):
            self.code_viewer.setPlainText(f"// No source file metadata available for {fName}.")
            return

        rel_path = fData["file"]
        line_start = fData.get("line_start", 1)

        # #2E: prefer source stored in the DB for the active release (lazy single-file
        # read) — no filesystem dependency. Fall back to a linked local folder.
        db = self._db()
        rid = self._selected_release_id() if db else None
        if db and rid is not None and db.has_release_source(rid):
            norm = rel_path.replace(os.sep, "/")
            content = db.read_release_source_file(rid, norm)
            if content is None:
                base = os.path.basename(norm)
                for f in db.list_release_source_files(rid):
                    if os.path.basename(f["rel_path"]) == base:
                        content = db.read_release_source_file(rid, f["rel_path"])
                        break
            if content is not None:
                code_block = self.extract_function_block_by_line(content, line_start)
                header = f"// File: {os.path.basename(rel_path)} | Line: {line_start}\n\n"
                self.code_viewer.setPlainText(header + code_block)
                return

        if not self.linked_source_dir:
            self.code_viewer.setPlainText(
                f"// Source code of '{fName}' not found.\n"
                f"// Import source for this release (Release Selection → Map / Import "
                f"Source Code) or link a local source folder."
            )
            return

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
        return extract_function_block_by_line(content, line_start)

    def rebuild_graph(self):
        if not self.focused_func or not self.dataset:
            return

        self.scene.clear()

        level_nodes, node_levels, total_nodes = compute_graph_levels(
            self.dataset, self.callers_map, self.focused_func,
            self.back_spin.value(), self.forward_spin.value())

        if total_nodes > MAX_GRAPH_NODES:
            self.lbl_graph_warning.setText(
                f"Warning: Call graph contains {total_nodes} nodes (exceeds performance threshold). "
                f"Truncated display to first {MAX_GRAPH_NODES} nodes."
            )
            self.lbl_graph_warning.setVisible(True)
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
