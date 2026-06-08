"""
Advanced AI Chat — Tab 4 controller (Phases 11 + 12).

A 2-column tab: left = source paths (synced with Tab 3), requirements import,
mind-map generation/diffs, separate prompt/rules editors, and the shared
provider panel; right = an agentic chat grounded in the mind map + read-only
code tools (Phase 9). Token strategy (Phase 12): the compact mind map is the
default context injected per turn — raw C is reached only on demand via tools.

UI is manual-tested; the heavy logic lives in Logic_AI_Context / Logic_AI_Providers
/ Logic_AI_Tools (unit-tested).
"""
import datetime
import json
import logging
import os

from PyQt6 import QtWidgets, QtCore

from Application_Logic import Logic_AI_Providers as providers
from Application_Logic import Logic_AI_Context as ctx
from Application_Logic import Logic_AI_Tools as aitools
from Application_Logic.Logic_AI_ProviderPanel import ProviderPanelMixin

logger = logging.getLogger(__name__)

_META_LAST_DIFF = "ai_last_diff_hash"


class _MindMapWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(str)
    finished_ok = QtCore.pyqtSignal(int)     # number of maps built
    failed = QtCore.pyqtSignal(str)

    def __init__(self, jobs, current_source, previous_source, db, parent=None):
        super().__init__(parent)
        self.jobs = jobs        # [(model_id, model_name, ports, requirements)]
        self.current_source = current_source
        self.previous_source = previous_source
        self.db = db

    def run(self):
        try:
            diff_hash = ""
            diffs = None
            if self.previous_source and self.current_source:
                diff_hash = ctx.compute_diff_hash(self.current_source, self.previous_source)
                self.db.set_meta(_META_LAST_DIFF, diff_hash)
            now = datetime.datetime.now().isoformat(timespec="seconds")
            
            # Find if there is an active release with an ELF file
            active_elf_hash = None
            active_elf_path = None
            releases = self.db.get_all_releases()
            for r in releases:
                if r.get("is_active", 0) == 1 and not r.get("is_deleted", 0) and r.get("elf_hash"):
                    active_elf_hash = r["elf_hash"]
                    active_elf_path = r["elf_path"]
                    break
 
            for (mid, name, ports, reqs) in self.jobs:
                self.progress.emit(f"Indexing model '{name}' …")
                
                # Check if we should build the CodeMap
                code_map = None
                code_map_json = None
                if active_elf_hash:
                    # Check if CodeMap is already pregenerated in the DB
                    pregenerated_code_map = self.db.get_model_code_map(mid)
                    if pregenerated_code_map:
                        self.progress.emit("Using pregenerated CodeMap call-graph from database …")
                        code_map = pregenerated_code_map
                        code_map_json = json.dumps(code_map)
                    elif active_elf_path and os.path.exists(active_elf_path):
                        self.progress.emit(f"Building CodeMap call-graph join for '{name}' …")
                        try:
                            from core.elf_parser import ELFParser
                            from Application_Logic.Logic_Code_Index import build_index
                            from Application_Logic.Logic_Code_Map import build_code_map
                            
                            # Set up the parser backed by our DB
                            parser = ELFParser(active_elf_path)
                            parser.load_elf(active_elf_path)
                            parser.extract_all_streaming_to_db(self.db)
                            
                            # Re-open or use the parser in database-backed mode
                            parser = ELFParser(active_elf_path)
                            parser._db = self.db
                            parser._active_elf_hash = active_elf_hash
                            
                            # Build static C AST index
                            code_index = build_index(self.current_source) if self.current_source else None
                            
                            # Build Joined CodeMap
                            code_map = build_code_map(parser, code_index, source_root=self.current_source or "")
                            code_map_json = json.dumps(code_map)
                        except Exception as e:
                            self.progress.emit(f"Warning: Failed to build CodeMap: {e}")
                            logger.warning(f"Failed to build CodeMap: {e}")
                
                model_diffs = []
                if diff_hash:
                    # Check if DB has diffs for this model and hash
                    cur = self.db._conn.execute(
                        "SELECT 1 FROM ai_code_diffs WHERE model_id=? AND diff_hash=? LIMIT 1",
                        (mid, diff_hash)
                    )
                    if cur.fetchone():
                        self.progress.emit(f"Using pregenerated diffs for model '{name}' …")
                        model_diffs = self.db.get_code_diffs(mid, diff_hash)
                    else:
                        if diffs is None:
                            self.progress.emit("Computing file-by-file diffs (this reads changed files)…")
                            diffs = ctx.diff_source_folders(self.current_source, self.previous_source)
                        model_diffs = diffs

                mm = ctx.build_mind_map(self.current_source, name, mid, ports, reqs,
                                        generated_at=now, code_map=code_map)
                self.db.save_model_mindmap(
                    mid, json.dumps(mm), source_hash=mm.get("source_hash", ""),
                    diff_hash=diff_hash, builder_version=mm.get("builder_version", ""),
                    char_count=ctx.mind_map_char_count(mm), updated_at=now,
                    code_map_json=code_map_json)
                if diff_hash and model_diffs:
                    self.db.save_code_diffs(mid, diff_hash, model_diffs)
            self.db.commit()
            self.finished_ok.emit(len(self.jobs))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class _ChatWorker(QtCore.QThread):
    tool_call = QtCore.pyqtSignal(str, dict)
    finished_ok = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, provider_id, model, messages, tools, executor,
                 system_prompt, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.model = model
        self.messages = messages
        self.tools = tools
        self.executor = executor
        self.system_prompt = system_prompt
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            out = providers.generate_with_tools(
                self.provider_id, self.model, self.messages, self.tools,
                tool_executor=self.executor, system_prompt=self.system_prompt,
                on_tool_call=lambda n, a: self.tool_call.emit(n, a),
                stop_check=lambda: self._stop)
            self.finished_ok.emit(out)
        except providers.AIStopped:
            self.failed.emit("Stopped.")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class AIChatController(ProviderPanelMixin, QtCore.QObject):
    _provider_meta_key = "ai_chat_provider"
    _model_meta_key = "ai_chat_model"

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ui = main_window.ui
        self._discover = None
        self._chat = []
        self._chat_token = 0
        self._syncing = False
        self._mm_worker = None
        self._chat_worker = None

        self.tab_widget = QtWidgets.QWidget()
        self._tab_index = self.ui.tabWidget.addTab(self.tab_widget, "Advanced AI Chat")
        self._build_ui()

        appins = QtWidgets.QApplication.instance()
        if appins is not None:
            appins.aboutToQuit.connect(self._cleanup)

    # ------------------------------------------------------------------
    def _db(self):
        return getattr(self.main_window, "project_db", None)

    def _arch(self):
        return getattr(self.main_window, "arch_controller", None)

    def _cleanup(self):
        for t in (self._mm_worker, self._chat_worker):
            if t is not None and t.isRunning():
                if hasattr(t, "stop"):
                    t.stop()
                t.requestInterruption()
                t.wait(3000)
        self._cleanup_provider_threads()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self.tab_widget)
        outer.setContentsMargins(12, 12, 12, 12)
        split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        split.setHandleWidth(8)
        outer.addWidget(split)
        split.addWidget(self._build_left())
        split.addWidget(self._build_right())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([460, 940])

    def _build_left(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        # Source group
        sgrp = QtWidgets.QGroupBox("Source")
        sl = QtWidgets.QFormLayout(sgrp)
        self.edit_current_source = QtWidgets.QLineEdit()
        self.edit_current_source.editingFinished.connect(self._on_current_source_committed)
        cbtn = QtWidgets.QPushButton("Browse…")
        cbtn.clicked.connect(lambda: self._browse(self.edit_current_source, ctx.META_SOURCE))
        crow = QtWidgets.QHBoxLayout(); crow.addWidget(self.edit_current_source, 1); crow.addWidget(cbtn)
        sl.addRow("Current:", self._wrap(crow))
        self.edit_prev_source = QtWidgets.QLineEdit()
        self.edit_prev_source.editingFinished.connect(
            lambda: self._set_meta(ctx.META_PREVIOUS_SOURCE, self.edit_prev_source.text()))
        pbtn = QtWidgets.QPushButton("Browse…")
        pbtn.clicked.connect(lambda: self._browse(self.edit_prev_source, ctx.META_PREVIOUS_SOURCE))
        prow = QtWidgets.QHBoxLayout(); prow.addWidget(self.edit_prev_source, 1); prow.addWidget(pbtn)
        sl.addRow("Previous:", self._wrap(prow))
        lay.addWidget(sgrp)

        # Requirements
        rgrp = QtWidgets.QGroupBox("Requirements")
        rl = QtWidgets.QHBoxLayout(rgrp)
        btn_reqs = QtWidgets.QPushButton("Import Requirements…")
        btn_reqs.clicked.connect(self._import_requirements)
        self.lbl_reqs = QtWidgets.QLabel("(none)")
        rl.addWidget(btn_reqs); rl.addWidget(self.lbl_reqs, 1)
        lay.addWidget(rgrp)

        # Mind map
        mgrp = QtWidgets.QGroupBox("Mind Map")
        ml = QtWidgets.QVBoxLayout(mgrp)
        self.cmb_mindmap_model = QtWidgets.QComboBox()
        self.cmb_mindmap_model.currentIndexChanged.connect(self._refresh_mindmap_buttons)
        ml.addWidget(self.cmb_mindmap_model)
        mrow = QtWidgets.QHBoxLayout()
        self.btn_gen_mm = QtWidgets.QPushButton("Generate Mind Map")
        self.btn_gen_mm.clicked.connect(lambda: self._generate_mindmaps(all_models=False))
        self.btn_gen_mm_all = QtWidgets.QPushButton("Generate All")
        self.btn_gen_mm_all.clicked.connect(lambda: self._generate_mindmaps(all_models=True))
        mrow.addWidget(self.btn_gen_mm); mrow.addWidget(self.btn_gen_mm_all)
        ml.addLayout(mrow)
        self.btn_gen_diffs = QtWidgets.QPushButton("Generate Diffs (Current vs Previous)")
        self.btn_gen_diffs.clicked.connect(self._generate_diffs)
        ml.addWidget(self.btn_gen_diffs)
        self.lbl_mm_status = QtWidgets.QLabel("")
        self.lbl_mm_status.setStyleSheet("color:#888; font-size:11px;")
        self.lbl_mm_status.setWordWrap(True)
        ml.addWidget(self.lbl_mm_status)
        lay.addWidget(mgrp)

        # Prompt & rules (separate keys)
        prgrp = QtWidgets.QGroupBox("Prompt && Rules")
        prgrp.setCheckable(True); prgrp.setChecked(False)
        pl = QtWidgets.QVBoxLayout(prgrp)
        tabs = QtWidgets.QTabWidget()
        self.txt_mm_prompt = QtWidgets.QPlainTextEdit()
        self.txt_mm_rules = QtWidgets.QPlainTextEdit()
        self.txt_chat_rules = QtWidgets.QPlainTextEdit()
        tabs.addTab(self.txt_mm_prompt, "Mind Map Prompt")
        tabs.addTab(self.txt_mm_rules, "Mind Map Rules")
        tabs.addTab(self.txt_chat_rules, "Chat Rules")
        pl.addWidget(tabs)
        prrow = QtWidgets.QHBoxLayout()
        bsave = QtWidgets.QPushButton("Save"); bsave.clicked.connect(self._save_prompt_rules)
        breset = QtWidgets.QPushButton("Reset to default"); breset.clicked.connect(self._reset_prompt_rules)
        prrow.addWidget(bsave); prrow.addWidget(breset); prrow.addStretch()
        pl.addLayout(prrow)
        lay.addWidget(prgrp)

        # Provider panel (shared mixin)
        lay.addWidget(self._build_provider_group())
        lay.addStretch()
        return w

    def _build_right(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.chat_view = QtWidgets.QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        lay.addWidget(self.chat_view, 1)
        self.chat_input = QtWidgets.QPlainTextEdit()
        self.chat_input.setPlaceholderText("Ask about the source code… (Ctrl+Enter to send)")
        self.chat_input.setMaximumHeight(90)
        lay.addWidget(self.chat_input)
        row = QtWidgets.QHBoxLayout()
        self.btn_send = QtWidgets.QPushButton("Send")
        self.btn_send.clicked.connect(self._on_send)
        self.btn_stop = QtWidgets.QPushButton("Stop"); self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_clear = QtWidgets.QPushButton("Clear/Reset Context")
        self.btn_clear.clicked.connect(self._clear_context)
        row.addWidget(self.btn_send, 1); row.addWidget(self.btn_stop); row.addWidget(self.btn_clear)
        lay.addLayout(row)
        return w

    @staticmethod
    def _wrap(layout):
        c = QtWidgets.QWidget(); c.setLayout(layout); return c

    # ------------------------------------------------------------------
    # Tab activation
    # ------------------------------------------------------------------
    def on_tab_changed(self, index):
        if self.ui.tabWidget.widget(index) is not self.tab_widget:
            return
        # Sync the (single, shared) source key from whatever Tab 3 last wrote.
        self._set_source_silently(self.edit_current_source, self._meta(ctx.META_SOURCE) or "")
        self._set_source_silently(self.edit_prev_source, self._meta(ctx.META_PREVIOUS_SOURCE) or "")
        self._refresh_providers()
        self._refresh_models_dropdown()
        self._load_prompt_rules()
        self._refresh_reqs_status()
        self._refresh_mindmap_buttons()

    # ------------------------------------------------------------------
    # Source sync (anti-loop)
    # ------------------------------------------------------------------
    def _set_source_silently(self, line_edit, value):
        if line_edit.text() == value:
            return
        self._syncing = True
        line_edit.blockSignals(True)
        try:
            line_edit.setText(value)
        finally:
            line_edit.blockSignals(False)
            self._syncing = False

    def _on_current_source_committed(self):
        if self._syncing:
            return
        self._set_meta(ctx.META_SOURCE, self.edit_current_source.text())

    def _browse(self, line_edit, meta_key):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Source Folder", line_edit.text(),
            options=QtWidgets.QFileDialog.Option(0)
        )
        if path:
            line_edit.setText(path)
            self._set_meta(meta_key, path)

    def _set_meta(self, key, value):
        db = self._db()
        if db is not None and getattr(db, "is_open", False):
            try:
                db.set_meta(key, value)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------
    def _import_requirements(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.main_window, "Import Requirements", "",
            "Requirement sheets (*.csv *.xlsx *.xls)",
            options=QtWidgets.QFileDialog.Option(0)
        )
        if not path:
            return
        try:
            reqs = ctx.parse_requirements_file(path)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self.main_window, "Requirements", str(e))
            return
        self._set_meta(ctx.META_REQUIREMENTS, json.dumps(reqs))
        self._refresh_reqs_status()

    def _refresh_reqs_status(self):
        raw = self._meta(ctx.META_REQUIREMENTS)
        n = 0
        if raw:
            try:
                n = len([r for r in json.loads(raw) if r.get("id") != "..."])
            except (ValueError, TypeError):
                n = 0
        self.lbl_reqs.setText(f"{n} requirement(s) loaded" if n else "(none)")

    def _requirements(self):
        raw = self._meta(ctx.META_REQUIREMENTS)
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return []

    # ------------------------------------------------------------------
    # Models / mind map
    # ------------------------------------------------------------------
    def _refresh_models_dropdown(self):
        arch = self._arch()
        cur = self.cmb_mindmap_model.currentData()
        self.cmb_mindmap_model.blockSignals(True)
        self.cmb_mindmap_model.clear()
        if arch is not None:
            for m in arch.model_manager.models:
                if not getattr(m, "is_deleted", False):
                    self.cmb_mindmap_model.addItem(m.name, m.id)
        if cur is not None:
            i = self.cmb_mindmap_model.findData(cur)
            if i >= 0:
                self.cmb_mindmap_model.setCurrentIndex(i)
        self.cmb_mindmap_model.blockSignals(False)

    def _extract_ports(self, model):
        """Pull (port name, operation) pairs from a model's cached rows using the
        shared column schema. Keyword binding to functions happens in build_mind_map."""
        arch = self._arch()
        if arch is None:
            return []
        from Application_Logic.Logic_Column_Types import PortSearchColumn
        port_col = next((c.name for c in arch.active_columns
                         if isinstance(c, PortSearchColumn)), None)
        db = self._db()
        ops_col = db.get_meta("operations_column_name") if db else None
        if model.data_cache is None:
            arch.model_manager._load_model_data(model)
        rows = (model.data_cache or {}).get("rows", [])
        ports, seen = [], set()
        for r in rows:
            name = (r.get(port_col, {}) or {}).get("text", "").strip() if port_col else ""
            op = (r.get(ops_col, {}) or {}).get("text", "").strip() if ops_col else ""
            if not name:
                continue
            key = (name, op)
            if key in seen:
                continue
            seen.add(key)
            ports.append({"name": name, "operation": op})
        return ports

    def _generate_mindmaps(self, all_models):
        arch = self._arch()
        db = self._db()
        if arch is None or db is None or not getattr(db, "is_open", False):
            QtWidgets.QMessageBox.warning(self.main_window, "Mind Map", "Open a project first.")
            return
        current = self.edit_current_source.text().strip()
        if not current:
            QtWidgets.QMessageBox.warning(self.main_window, "Mind Map",
                                          "Set the Current source path first.")
            return
        if all_models:
            models = [m for m in arch.model_manager.models if not getattr(m, "is_deleted", False)]
        else:
            mid = self.cmb_mindmap_model.currentData()
            models = [m for m in arch.model_manager.models if m.id == mid]
        if not models:
            QtWidgets.QMessageBox.warning(self.main_window, "Mind Map", "No model selected.")
            return
        reqs = self._requirements()
        jobs = [(m.id, m.name, self._extract_ports(m), reqs) for m in models]
        self._run_mm_worker(jobs, current, self.edit_prev_source.text().strip())

    def _generate_diffs(self):
        current = self.edit_current_source.text().strip()
        previous = self.edit_prev_source.text().strip()
        if not current or not previous:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Diffs", "Set BOTH Current and Previous source paths.")
            return
        # Diffs alone: re-run mind maps would be heavier; here we only compute diffs
        # for the selected model so get_diff works in chat. (Regenerate updates maps.)
        arch = self._arch()
        mid = self.cmb_mindmap_model.currentData()
        model = next((m for m in arch.model_manager.models if m.id == mid), None) if arch else None
        if model is None:
            QtWidgets.QMessageBox.warning(self.main_window, "Diffs", "Select a model.")
            return
        reqs = self._requirements()
        # A diff-only run: skip rebuilding the map by passing the existing model but
        # the worker always (re)builds — acceptable and keeps one code path.
        self._run_mm_worker([(model.id, model.name, self._extract_ports(model), reqs)],
                            current, previous, diff_only_label=True)

    def _run_mm_worker(self, jobs, current, previous, diff_only_label=False):
        if self._mm_worker is not None and self._mm_worker.isRunning():
            return
        self._busy(True)
        from Application_Logic.Logic_Loading_Window import LoadingDialog
        # Non-modal (MEMORY: never app-modal show()/close()).
        self._mm_loading = LoadingDialog(self.main_window)
        self._mm_loading.ui.lbl_loading_text.setText("Building mind map…")
        self._mm_loading.show()
        self._mm_worker = _MindMapWorker(jobs, current, previous, self._db(), self)
        self._mm_worker.progress.connect(
            lambda m: self._mm_loading.append_log(m) if self._mm_loading else None)
        self._mm_worker.finished_ok.connect(self._on_mm_done)
        self._mm_worker.failed.connect(self._on_mm_failed)
        self._mm_worker.start()

    def _on_mm_done(self, n):
        if getattr(self, "_mm_loading", None):
            self._mm_loading.close(); self._mm_loading.deleteLater(); self._mm_loading = None
        self._busy(False)
        self.lbl_mm_status.setText(f"Built {n} mind map(s).")
        self._refresh_mindmap_buttons()

    def _on_mm_failed(self, msg):
        if getattr(self, "_mm_loading", None):
            self._mm_loading.close(); self._mm_loading.deleteLater(); self._mm_loading = None
        self._busy(False)
        QtWidgets.QMessageBox.critical(self.main_window, "Mind Map", msg)

    def _busy(self, busy):
        for b in (self.btn_gen_mm, self.btn_gen_mm_all, self.btn_gen_diffs):
            b.setEnabled(not busy)

    def _refresh_mindmap_buttons(self):
        """DB-driven Generate→Regenerate flip (locked decision #6 — no fs scan)."""
        db = self._db()
        mid = self.cmb_mindmap_model.currentData()
        has_diff = False
        if db is not None and getattr(db, "is_open", False) and mid is not None:
            last = db.get_meta(_META_LAST_DIFF)
            if last:
                has_diff = db.has_code_diff(mid, last)
        label = ctx.mindmap_button_label(has_diff)
        self.btn_gen_mm.setText(label)
        self.btn_gen_mm_all.setText(label.replace("Mind Map", "All"))

    # ------------------------------------------------------------------
    # Prompt / rules
    # ------------------------------------------------------------------
    def _load_prompt_rules(self):
        db = self._db()
        self.txt_mm_prompt.setPlainText(ctx.get_mindmap_prompt(db))
        self.txt_mm_rules.setPlainText(ctx.get_mindmap_rules(db))
        self.txt_chat_rules.setPlainText(ctx.get_chat_rules(db))

    def _save_prompt_rules(self):
        db = self._db()
        ctx.set_mindmap_prompt(db, self.txt_mm_prompt.toPlainText())
        ctx.set_mindmap_rules(db, self.txt_mm_rules.toPlainText())
        ctx.set_chat_rules(db, self.txt_chat_rules.toPlainText())
        QtWidgets.QMessageBox.information(self.main_window, "Saved", "Saved to the project.")

    def _reset_prompt_rules(self):
        self.txt_mm_prompt.setPlainText(ctx.DEFAULT_MINDMAP_PROMPT)
        self.txt_mm_rules.setPlainText(ctx.DEFAULT_MINDMAP_RULES)
        self.txt_chat_rules.setPlainText(ctx.DEFAULT_CHAT_RULES)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def _clear_context(self):
        if self._chat_worker is not None and self._chat_worker.isRunning():
            self._chat_worker.stop()
        self._chat = []
        self._chat_token += 1
        self.chat_view.clear()

    def _on_stop(self):
        if self._chat_worker is not None:
            self._chat_worker.stop()
        self.btn_stop.setEnabled(False)

    def _append(self, who, text):
        safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("\n", "<br>")
        self.chat_view.append(f"<b>{who}:</b> {safe}<br>")

    def _on_send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        pid = self.cmb_provider.currentData()
        model = self.cmb_model.currentData()
        if not pid or not model or not providers.get_provider(pid).is_configured():
            QtWidgets.QMessageBox.warning(self.main_window, "Chat", "Configure a provider first.")
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return

        db = self._db()
        mid = self.cmb_mindmap_model.currentData()
        # Phase 12: inject the compact mind map (NOT raw C) as the standing context.
        mm = db.get_model_mindmap(mid) if (db and mid is not None) else None
        mm_text = ctx.mind_map_to_text(mm)
        system = ctx.get_chat_rules(db) + "\n\n# CODE MIND MAP\n" + mm_text
        if not mm:
            self._append("System", "No mind map for this model yet — answers rely on live "
                                   "file reads. Generate a mind map for grounding.")

        diff_hash = db.get_meta(_META_LAST_DIFF) if db else ""
        executor = aitools.ToolExecutor(
            self.edit_current_source.text().strip() or None, db=db,
            model_id=mid if mid is not None else -1, diff_hash=diff_hash or "")

        self._append("You", text)
        self.chat_input.clear()
        self._chat.append({"role": "user", "content": text})

        token = self._chat_token
        self.btn_send.setEnabled(False); self.btn_stop.setEnabled(True)
        self._chat_worker = _ChatWorker(
            pid, model, list(self._chat), aitools.default_tools(), executor.execute,
            system, self)
        self._chat_worker.tool_call.connect(
            lambda n, a: self._append("→ tool", f"{n}({a})"))
        self._chat_worker.finished_ok.connect(lambda out: self._on_chat_done(token, out))
        self._chat_worker.failed.connect(lambda msg: self._on_chat_failed(token, msg))
        self._chat_worker.start()

    def _on_chat_done(self, token, out):
        self.btn_send.setEnabled(True); self.btn_stop.setEnabled(False)
        if token != self._chat_token:
            return   # context was cleared / model switched mid-flight — drop result
        self._chat.append({"role": "assistant", "content": out})
        self._append("AI", out)

    def _on_chat_failed(self, token, msg):
        self.btn_send.setEnabled(True); self.btn_stop.setEnabled(False)
        if token != self._chat_token:
            return
        self._append("Error", msg)
