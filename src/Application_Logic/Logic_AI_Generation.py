"""
AI Test Case Generation — tab controller.

Owns the third main-window tab: a 2-column layout (config left / output right),
runs generation on a worker thread, streams progress, writes <Model>_LowLevel.md,
supports write-back into the original HLT file, and a follow-up chat.

UI is manual-tested (per project testing strategy); the pure logic it relies on
lives in Logic_AI_Context / Logic_AI_Providers (unit-tested).
"""
from PyQt6 import QtWidgets, QtCore

from Application_Logic import Logic_AI_Providers as providers
from Application_Logic import Logic_AI_Context as ctx
from Application_Logic.Logic_AI_ProviderPanel import ProviderPanelMixin

# DB meta keys for non-secret preferences (secrets live in the credential store).
_META_PROVIDER = "ai_sel_provider"
_META_MODEL = "ai_sel_model"
_META_SOURCE = "ai_source_path"


class _GenWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(str)
    case_done = QtCore.pyqtSignal(str, str)   # tc_id, generated markdown
    finished_ok = QtCore.pyqtSignal(str)      # output file path
    failed = QtCore.pyqtSignal(str)

    def __init__(self, provider_id, model, rules, prompt, source_path,
                 output_dir, model_name, hlt_title, test_cases, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.model = model
        self.rules = rules
        self.prompt = prompt
        self.source_path = source_path
        self.output_dir = output_dir
        self.model_name = model_name
        self.hlt_title = hlt_title
        self.test_cases = test_cases   # selected, parsed dicts
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self.progress.emit("Analyzing source code for relevant context…")
            combined = "\n".join(tc["raw"] for tc in self.test_cases)
            source_ctx = ctx.build_source_context(self.source_path, [combined]) if self.source_path else ""
            if source_ctx:
                self.progress.emit(f"Source context: {len(source_ctx)} chars.")
            else:
                self.progress.emit("No source context (path empty or no match).")

            generated = {}
            for i, tc in enumerate(self.test_cases, 1):
                if self._stop:
                    raise providers.AIStopped("Stopped by user.")
                self.progress.emit(f"[{i}/{len(self.test_cases)}] Generating: {tc['title']}")
                messages = ctx.build_messages(self.rules, self.prompt, tc["raw"], source_ctx)
                text = providers.generate(
                    self.provider_id, self.model, messages,
                    stream_cb=None, stop_check=lambda: self._stop,
                )
                generated[tc["id"]] = text
                self.case_done.emit(tc["id"], text)

            path = ctx.write_lowlevel_output(
                self.output_dir, self.model_name, self.hlt_title,
                self.test_cases, generated)
            self.finished_ok.emit(path)
        except providers.AIStopped:
            self.failed.emit("Generation stopped.")
        except Exception as e:  # noqa: BLE001 — report any failure to the UI
            self.failed.emit(str(e))


class AIGenerationController(ProviderPanelMixin, QtCore.QObject):
    # Per-tab meta keys for the shared provider/model panel (Phase 10.5).
    _provider_meta_key = _META_PROVIDER
    _model_meta_key = _META_MODEL

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ui = main_window.ui
        self._worker = None
        self._discover = None         # model-discovery thread (mixin-owned)
        self._parsed = None           # current parsed HLT file
        self._generated = {}          # tc_id -> markdown
        self._chat = []               # conversation messages
        self._chat_gen_token = 0      # invalidates stale completion callbacks
        self._active_model_name = None  # last HLT model; chat wipes on change

        self.tab_widget = QtWidgets.QWidget()
        self.ui.tabWidget.addTab(self.tab_widget, "AI Test Generation")
        self._build_ui()
        self._load_prefs()

        # Make sure background threads are stopped before the app tears down,
        # otherwise a QThread destroyed mid-run aborts the process.
        appins = QtWidgets.QApplication.instance()
        if appins is not None:
            appins.aboutToQuit.connect(self._cleanup_threads)

    def _cleanup_threads(self):
        for t in (self._worker, self._discover):
            if t is not None and t.isRunning():
                if hasattr(t, "stop"):
                    t.stop()
                t.requestInterruption()
                t.wait(3000)

    # ------------------------------------------------------------------
    def _db(self):
        return getattr(self.main_window, "project_db", None)

    def _project_path(self):
        return getattr(self.main_window, "current_project_file", None)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self.tab_widget)
        outer.setContentsMargins(12, 12, 12, 12)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)
        outer.addWidget(splitter)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 900])

    def _build_left(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        # Provider + model + status pill + Configure/Help (shared mixin panel)
        lay.addWidget(self._build_provider_group())

        lay.addWidget(self._hline())

        # Source — #2E: chosen by RELEASE; source is read from the DB for that release.
        lay.addWidget(QtWidgets.QLabel("Source release:"))
        self.cmb_source_release = QtWidgets.QComboBox()
        self.cmb_source_release.currentIndexChanged.connect(self._on_source_release_changed)
        lay.addWidget(self.cmb_source_release)

        # HLT file
        hrow = QtWidgets.QHBoxLayout()
        self.cmb_hlt = QtWidgets.QComboBox()
        self.cmb_hlt.currentIndexChanged.connect(self._on_hlt_changed)
        btn_refresh = QtWidgets.QPushButton("↻")
        btn_refresh.setFixedWidth(32)
        btn_refresh.clicked.connect(self.refresh_hlt_files)
        hrow.addWidget(QtWidgets.QLabel("Test case design:"))
        hrow.addWidget(self.cmb_hlt, 1)
        hrow.addWidget(btn_refresh)
        lay.addLayout(hrow)

        # Test case tree
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        lay.addWidget(self.tree, 1)
        trow = QtWidgets.QHBoxLayout()
        btn_all = QtWidgets.QPushButton("Select All")
        btn_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_none = QtWidgets.QPushButton("None")
        btn_none.clicked.connect(lambda: self._set_all_checked(False))
        trow.addWidget(btn_all)
        trow.addWidget(btn_none)
        trow.addStretch()
        lay.addLayout(trow)

        # Prompt & rules
        grp = QtWidgets.QGroupBox("Prompt && Rules")
        grp.setCheckable(True)
        grp.setChecked(False)
        gl = QtWidgets.QVBoxLayout(grp)
        sub = QtWidgets.QTabWidget()
        self.txt_prompt = QtWidgets.QPlainTextEdit()
        self.txt_rules = QtWidgets.QPlainTextEdit()
        sub.addTab(self.txt_prompt, "Prompt")
        sub.addTab(self.txt_rules, "Rules")
        gl.addWidget(sub)
        rrow = QtWidgets.QHBoxLayout()
        btn_save_pr = QtWidgets.QPushButton("Save")
        btn_save_pr.clicked.connect(self._save_prompt_rules)
        self.btn_save_pr = btn_save_pr
        btn_reset_pr = QtWidgets.QPushButton("Reset to default")
        btn_reset_pr.clicked.connect(self._reset_prompt_rules)
        rrow.addWidget(btn_save_pr)
        rrow.addWidget(btn_reset_pr)
        rrow.addStretch()
        gl.addLayout(rrow)
        lay.addWidget(grp)

        # Generate / Stop
        grow = QtWidgets.QHBoxLayout()
        self.btn_generate = QtWidgets.QPushButton("▶ Generate")
        self.btn_generate.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_stop = QtWidgets.QPushButton("■ Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)
        grow.addWidget(self.btn_generate, 1)
        grow.addWidget(self.btn_stop)
        lay.addLayout(grow)
        return w

    def _build_right(self) -> QtWidgets.QWidget:
        self.right_tabs = QtWidgets.QTabWidget()

        self.out_design = QtWidgets.QTextBrowser()
        self.out_design.setOpenExternalLinks(True)
        design_w = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(design_w)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.out_design, 1)
        drow = QtWidgets.QVBoxLayout()
        self.btn_writeback = QtWidgets.QPushButton("Write Back to High-Level Test Design")
        self.btn_writeback.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_writeback.clicked.connect(self._write_back)
        self.btn_writeback.setEnabled(False)
        self.lbl_outfile = QtWidgets.QLabel("")
        self.lbl_outfile.setStyleSheet("color:#888; font-size:11px;")
        
        self.lbl_writeback_desc = QtWidgets.QLabel(
            "Updates the High-Level Test (HLT) design columns in the main architecture table "
            "with the generated low-level test design details."
        )
        self.lbl_writeback_desc.setStyleSheet("color: #666; font-size: 11px; margin-top: 2px;")
        self.lbl_writeback_desc.setWordWrap(True)
        
        drow.addWidget(self.btn_writeback)
        drow.addWidget(self.lbl_outfile)
        drow.addWidget(self.lbl_writeback_desc)
        dl.addLayout(drow)
        self.right_tabs.addTab(design_w, "Low-Level Design")

        # Unified "Output" tab: progress/thought-process (top) over chat (bottom),
        # split so a long agent loop shows life and the conversation shares context.
        out_w = QtWidgets.QWidget()
        ol = QtWidgets.QVBoxLayout(out_w)
        ol.setContentsMargins(0, 0, 0, 0)
        vsplit = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.out_thoughts = QtWidgets.QPlainTextEdit()
        self.out_thoughts.setReadOnly(True)
        vsplit.addWidget(self.out_thoughts)

        chat_w = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(chat_w)
        cl.setContentsMargins(0, 0, 0, 0)
        self.chat_view = QtWidgets.QTextBrowser()
        cl.addWidget(self.chat_view, 1)
        crow = QtWidgets.QHBoxLayout()
        self.chat_input = QtWidgets.QLineEdit()
        self.chat_input.setPlaceholderText("Ask a follow-up…")
        self.chat_input.returnPressed.connect(self._on_send_chat)
        self.btn_send = QtWidgets.QPushButton("Send")
        self.btn_send.clicked.connect(self._on_send_chat)
        self.btn_clear_ctx = QtWidgets.QPushButton("Clear Context")
        self.btn_clear_ctx.clicked.connect(self._clear_chat_context)
        crow.addWidget(self.chat_input, 1)
        crow.addWidget(self.btn_send)
        crow.addWidget(self.btn_clear_ctx)
        cl.addLayout(crow)
        vsplit.addWidget(chat_w)
        vsplit.setSizes([200, 360])
        ol.addWidget(vsplit)
        self.right_tabs.addTab(out_w, "Output")
        return self.right_tabs

    def _clear_chat_context(self):
        """Reset the conversation and invalidate any in-flight completion."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.stop()
        self._chat = []
        self._chat_gen_token += 1
        if hasattr(self, "chat_view"):
            self.chat_view.clear()
        if hasattr(self, "out_thoughts"):
            self.out_thoughts.clear()

    @staticmethod
    def _hline():
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        return line

    # ------------------------------------------------------------------
    # Tab activation
    # ------------------------------------------------------------------
    def on_tab_changed(self, index):
        if self.ui.tabWidget.widget(index) is self.tab_widget:
            self._refresh_providers()
            self.refresh_hlt_files()
            self._load_prompt_rules()
            self._refresh_source_releases()

    def apply_edit_mode(self, enabled: bool):
        """View-Only: disable generation, write-back, and prompt/rules save (they
        write low-level design files into the project and edit the HLT design)."""
        tip = "" if enabled else "Disabled in View-Only mode — acquire the edit lock to use this."
        for btn in (getattr(self, "btn_generate", None), getattr(self, "btn_save_pr", None)):
            if btn is not None:
                btn.setEnabled(enabled)
                btn.setToolTip(tip)
        # Write-back has its own state (only after a generation produced output);
        # never force it on — just keep it off in View-Only.
        if getattr(self, "btn_writeback", None) is not None:
            self.btn_writeback.setEnabled(enabled and bool(self._generated))
            self.btn_writeback.setToolTip(tip)

    # ------------------------------------------------------------------
    # Source / HLT files
    # ------------------------------------------------------------------
    def _refresh_source_releases(self):
        """#2E: populate the source-release dropdown (shared 'current release' meta
        with the AI Chat tab; defaults to the active/latest release)."""
        from Application_Logic.Logic_Release_Source_Picker import populate_release_combo
        db = self._db()
        arch = getattr(self.main_window, "arch_controller", None)
        rm = getattr(arch, "release_manager", None) if arch else None
        if rm is None:
            return
        source_ids = db.get_release_ids_with_source() if db else set()
        prefer = None
        if db is not None and getattr(db, "is_open", False):
            saved = db.get_meta(ctx.META_CURRENT_RELEASE)
            try:
                prefer = int(saved) if saved not in (None, "") else db.get_active_release_id()
            except (ValueError, TypeError):
                prefer = db.get_active_release_id()
        populate_release_combo(self.cmb_source_release, rm,
                               prefer_id=prefer, source_ids=source_ids)

    def _on_source_release_changed(self, _idx=0):
        db = self._db()
        if db is None or not getattr(db, "is_open", False):
            return
        rid = self.cmb_source_release.currentData()
        try:
            db.set_meta(ctx.META_CURRENT_RELEASE, "" if rid is None else str(rid))
        except Exception:
            pass

    def _source_provider(self):
        from Application_Logic.Logic_Source_Store import release_source_provider
        return release_source_provider(self._db(), self.cmb_source_release.currentData())

    def refresh_hlt_files(self):
        proj = self._project_path()
        self.cmb_hlt.blockSignals(True)
        self.cmb_hlt.clear()
        files = []
        if proj:
            files = ctx.find_hlt_files(ctx.hlt_output_dir(proj))
        if not files:
            self.cmb_hlt.addItem("(no generated test case designs found)", None)
            self.tree.clear()
        else:
            import os
            for f in files:
                self.cmb_hlt.addItem(os.path.basename(f), f)
        self.cmb_hlt.blockSignals(False)
        self._on_hlt_changed()

    def _on_hlt_changed(self):
        path = self.cmb_hlt.currentData()
        self.tree.clear()
        self._parsed = None
        if not path:
            return
        try:
            self._parsed = ctx.parse_hlt_file(path)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self.main_window, "Parse Error", str(e))
            return
        # Wipe chat context only when the architecture MODEL changes (not on every
        # HLT-file switch within the same model) to avoid cross-model hallucination.
        new_model = self._parsed.get("model_name")
        if new_model != self._active_model_name:
            self._clear_chat_context()
            self._active_model_name = new_model
        root = QtWidgets.QTreeWidgetItem([self._parsed["model_name"]])
        root.setFlags(root.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        self.tree.addTopLevelItem(root)
        for tc in self._parsed["test_cases"]:
            it = QtWidgets.QTreeWidgetItem([tc["title"]])
            it.setFlags(it.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, QtCore.Qt.CheckState.Checked)
            it.setData(0, QtCore.Qt.ItemDataRole.UserRole, tc)
            root.addChild(it)
        root.setExpanded(True)

    def _set_all_checked(self, checked):
        state = QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                root.child(j).setCheckState(0, state)

    def _selected_cases(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            for j in range(root.childCount()):
                child = root.child(j)
                if child.checkState(0) == QtCore.Qt.CheckState.Checked:
                    out.append(child.data(0, QtCore.Qt.ItemDataRole.UserRole))
        return out

    # ------------------------------------------------------------------
    # Prompt / rules
    # ------------------------------------------------------------------
    def _load_prompt_rules(self):
        db = self._db()
        self.txt_prompt.setPlainText(ctx.get_prompt(db))
        self.txt_rules.setPlainText(ctx.get_rules(db))

    def _save_prompt_rules(self):
        db = self._db()
        ctx.set_prompt(db, self.txt_prompt.toPlainText())
        ctx.set_rules(db, self.txt_rules.toPlainText())
        QtWidgets.QMessageBox.information(self.main_window, "Saved",
                                          "Prompt and rules saved to the project.")

    def _reset_prompt_rules(self):
        self.txt_prompt.setPlainText(ctx.DEFAULT_PROMPT)
        self.txt_rules.setPlainText(ctx.DEFAULT_RULES)

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------
    def _load_prefs(self):
        # #2E: the source is now a release selection — populate that dropdown.
        self._refresh_source_releases()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def _on_generate(self):
        pid = self.cmb_provider.currentData()
        model = self.cmb_model.currentData()
        if not pid or not model:
            QtWidgets.QMessageBox.warning(self.main_window, "AI", "Select a provider and model.")
            return
        if not providers.get_provider(pid).is_configured():
            QtWidgets.QMessageBox.warning(
                self.main_window, "AI",
                "This provider is not configured. Open 'Configure Providers'.")
            return
        if not self._parsed:
            QtWidgets.QMessageBox.warning(
                self.main_window, "AI",
                "No test case design selected. Generate the high-level design in the "
                "'Test Case Design' tab first, then refresh.")
            return
        cases = self._selected_cases()
        if not cases:
            QtWidgets.QMessageBox.warning(self.main_window, "AI", "Select at least one test case.")
            return

        db = self._db()
        # Persist any prompt/rules edits before using them.
        ctx.set_prompt(db, self.txt_prompt.toPlainText())
        ctx.set_rules(db, self.txt_rules.toPlainText())

        self._generated = {}
        self.out_thoughts.clear()
        self.out_design.setMarkdown("")
        self.lbl_outfile.setText("")
        self.btn_writeback.setEnabled(False)
        self.btn_generate.setEnabled(False)
        self.btn_stop.setEnabled(True)
        if db is not None and getattr(db, "is_open", False):
            db.set_activity("aigen", "in_progress", self._parsed.get("model_name", ""))

        self._worker = _GenWorker(
            pid, model,
            self.txt_rules.toPlainText(), self.txt_prompt.toPlainText(),
            self._source_provider(),
            ctx.hlt_output_dir(self._project_path()),
            self._parsed["model_name"], self._parsed["title"], cases,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.case_done.connect(self._on_case_done)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
        self.btn_stop.setEnabled(False)

    def _on_progress(self, msg):
        self.out_thoughts.appendPlainText(msg)

    def _on_case_done(self, tc_id, text):
        self._generated[tc_id] = text
        # Live-render accumulated output.
        parts = []
        for tc in (self._parsed["test_cases"] if self._parsed else []):
            if tc["id"] in self._generated:
                parts.append(f"## {tc['title']}\n\n{self._generated[tc['id']]}\n")
        self.out_design.setMarkdown("\n".join(parts))

    def _on_finished(self, path):
        self.btn_generate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_writeback.setEnabled(True)
        self.lbl_outfile.setText(f"Written: {path}")
        self.out_thoughts.appendPlainText(f"Done. Wrote {path}")
        self._clear_activity()
        # Seed the chat conversation with the generated context.
        self._chat = [{"role": "assistant", "content": "Low-level test cases generated."}]

    def _on_failed(self, msg):
        self.btn_generate.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.out_thoughts.appendPlainText(f"⚠ {msg}")
        self._clear_activity()

    def _clear_activity(self):
        db = self._db()
        if db is not None and getattr(db, "is_open", False):
            db.set_activity("", "idle")

    # ------------------------------------------------------------------
    # Write back
    # ------------------------------------------------------------------
    def _write_back(self):
        if not self._parsed or not self._generated:
            return
        path = self._parsed["path"]
        try:
            updated = ctx.apply_lowlevel_to_hlt(path, self._generated)
            if updated:
                QtWidgets.QMessageBox.information(
                    self.main_window, "Write Back",
                    f"Filled {updated} test case(s) in:\n{path}")
            else:
                QtWidgets.QMessageBox.information(
                    self.main_window, "Write Back",
                    "Nothing to write back (placeholders already filled, or no "
                    "matching test cases).")
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self.main_window, "Write Back", str(e))

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def _on_send_chat(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        pid = self.cmb_provider.currentData()
        model = self.cmb_model.currentData()
        if not pid or not model or not providers.get_provider(pid).is_configured():
            QtWidgets.QMessageBox.warning(self.main_window, "Chat", "Configure a provider first.")
            return
        self.chat_input.clear()
        self._append_chat("You", text)
        self._chat.append({"role": "user", "content": text})
        try:
            reply = providers.generate(pid, model, list(self._chat))
            self._chat.append({"role": "assistant", "content": reply})
            self._append_chat("AI", reply)
        except Exception as e:  # noqa: BLE001
            self._append_chat("Error", str(e))

    def _append_chat(self, who, text):
        # QTextBrowser.append treats input as HTML; escape the body and keep the
        # role label bold.
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("\n", "<br>")
        self.chat_view.append(f"<b>{who}:</b> {safe}<br>")
