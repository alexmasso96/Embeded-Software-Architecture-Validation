import json
import logging
import datetime
import os
from PyQt6 import QtCore, QtWidgets

logger = logging.getLogger(__name__)

def parse_and_align_diff(diff_text: str):
    """Parses a unified diff string and aligns the old and new code side-by-side.
    
    Returns lists of tuples (line_content, line_type) for the old and new views.
    """
    if not diff_text or diff_text.strip().startswith("(diff omitted") or diff_text.strip().startswith("(diff truncated"):
        return [(diff_text, "header")], [(diff_text, "header")]

    lines = diff_text.splitlines()
    old_aligned = []
    new_aligned = []
    
    i = 0
    n = len(lines)
    
    deletes = []
    adds = []
    
    def flush_deletes_adds():
        m = max(len(deletes), len(adds))
        for idx in range(m):
            del_line = deletes[idx] if idx < len(deletes) else None
            add_line = adds[idx] if idx < len(adds) else None
            
            if del_line is not None and add_line is not None:
                old_aligned.append((del_line, "deleted"))
                new_aligned.append((add_line, "added"))
            elif del_line is not None:
                old_aligned.append((del_line, "deleted"))
                new_aligned.append(("", "empty"))
            elif add_line is not None:
                old_aligned.append(("", "empty"))
                new_aligned.append((add_line, "added"))
        deletes.clear()
        adds.clear()

    while i < n:
        line = lines[i]
        if line.startswith('---') or line.startswith('+++') or line.startswith('index '):
            flush_deletes_adds()
            old_aligned.append((line, "header"))
            new_aligned.append((line, "header"))
            i += 1
        elif line.startswith('@@'):
            flush_deletes_adds()
            old_aligned.append((line, "header"))
            new_aligned.append((line, "header"))
            i += 1
        elif line.startswith('-'):
            deletes.append(line[1:])
            i += 1
        elif line.startswith('+'):
            adds.append(line[1:])
            i += 1
        elif line.startswith(' '):
            flush_deletes_adds()
            old_aligned.append((line[1:], "unchanged"))
            new_aligned.append((line[1:], "unchanged"))
            i += 1
        else:
            flush_deletes_adds()
            old_aligned.append((line, "unchanged"))
            new_aligned.append((line, "unchanged"))
            i += 1
            
    flush_deletes_adds()
    return old_aligned, new_aligned


class AIChangeLogWorker(QtCore.QThread):
    finished_ok = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)
    
    def __init__(self, provider_id, model, prompt, parent=None):
        super().__init__(parent)
        self.provider_id = provider_id
        self.model = model
        self.prompt = prompt
        
    def run(self):
        try:
            from Application_Logic import Logic_AI_Providers as providers

            # NB: providers' `Message` is a type alias (Dict[str, str]), NOT a class —
            # calling Message(...) raised "Type Dict cannot be instantiated". Messages
            # are plain dicts.
            messages = [
                {"role": "system", "content": "You are a senior software engineer and ASPICE auditor."},
                {"role": "user", "content": self.prompt},
            ]
            response = providers.generate(self.provider_id, self.model, messages)
            self.finished_ok.emit(response)
        except Exception as e:
            self.failed.emit(str(e))


class AIChangeLogController(QtCore.QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.ui = main_window.ui
        
        # Add Tab 6 Change Log Widget dynamically to main tab widget
        from UI.widgets_change_log import ChangeLogWidget
        self.tab_widget = ChangeLogWidget(self.main_window)
        
        # Add Generate AI Log button dynamically to Sub-tab 2
        self.btn_gen_ai_log = QtWidgets.QPushButton("Generate AI Change Log (requires AI Token)")
        self.btn_gen_ai_log.setStyleSheet("font-weight: bold; padding: 6px;")
        self.btn_gen_ai_log.clicked.connect(self.on_generate_ai_changelog)
        
        # Add to Sub-tab 2 layout above text browser
        ai_layout = self.tab_widget.tab_ai.layout()
        ai_layout.insertWidget(0, self.btn_gen_ai_log)
        
        self._tab_index = self.ui.tabWidget.addTab(self.tab_widget, "Change Log")
        
        # Connect signals
        self.tab_widget.cmb_compare_release.currentIndexChanged.connect(self.on_compare_release_changed)
        self.tab_widget.btn_compute_diffs.clicked.connect(self.on_compute_diffs)
        self.tab_widget.file_list.currentRowChanged.connect(self.on_file_selected)
        
        self.current_diffs = []
        self.compare_releases = []
        self.ai_worker = None

    def _db(self):
        return getattr(self.main_window, "project_db", None)

    def _arch(self):
        return getattr(self.main_window, "arch_controller", None)

    def on_tab_changed(self, index):
        if self.ui.tabWidget.widget(index) is not self.tab_widget:
            return
        self.load_data()

    def apply_edit_mode(self, enabled: bool):
        """View-Only: disable diff computation and AI change-log generation (both
        write to the DB). The side-by-side diff viewer itself stays usable."""
        tip = "" if enabled else "Disabled in View-Only mode — acquire the edit lock to use this."
        for btn in (getattr(self.tab_widget, "btn_compute_diffs", None),
                    getattr(self, "btn_gen_ai_log", None)):
            if btn is not None:
                btn.setEnabled(enabled)
                btn.setToolTip(tip)

    def load_data(self):
        db = self._db()
        arch = self._arch()
        if not db or not arch:
            self.tab_widget.txt_old.setPlaceholderText("// Open a project database to load the Change Log.")
            self.tab_widget.txt_new.setPlaceholderText("// Open a project database to load the Change Log.")
            return

        # 1. Populate the comparison release dropdown
        self.tab_widget.cmb_compare_release.blockSignals(True)
        self.tab_widget.cmb_compare_release.clear()
        self.compare_releases = []
        
        active_rel = arch.release_manager.get_active_release()
        source_ids = db.get_release_ids_with_source()
        for r in arch.release_manager.selectable_releases():   # #2E: real releases only
            if active_rel and r.id == active_rel.id:
                continue
            mark = " 📄" if r.id in source_ids else ""
            self.tab_widget.cmb_compare_release.addItem(f"{r.name}{mark}", r.id)
            self.compare_releases.append(r)
        self.tab_widget.cmb_compare_release.blockSignals(False)

        # 2. Get active model and load diff files
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if active_model_id is None:
            self.tab_widget.file_list.clear()
            self.tab_widget.txt_old.setPlaceholderText("// No active architecture model selected.")
            self.tab_widget.txt_new.setPlaceholderText("// No active architecture model selected.")
            self.tab_widget.lbl_diff_info.setText("Select an active architecture model.")
            return

        # #2E: fetch the active diff hash from the per-release map (active release).
        meta = db.get_model_mindmap_meta(active_model_id)
        diff_hash = meta.get("diff_hash") if meta else None

        if not diff_hash:
            self.tab_widget.file_list.clear()
            self.tab_widget.txt_old.clear()
            self.tab_widget.txt_new.clear()
            self.tab_widget.txt_old.setPlaceholderText("// No source differences computed for active model.")
            self.tab_widget.txt_new.setPlaceholderText("// No source differences computed for active model.")
            self.tab_widget.lbl_diff_info.setText("No code differences computed. Click 'Compute Release Diffs'.")
            self.tab_widget.txt_ai_changelog.setHtml("<h3>No AI Change Log Generated</h3>")
            return

        self.tab_widget.lbl_diff_info.setText(f"Active Diff Hash: {diff_hash[:12]}...")

        # Load file list from db
        self.current_diffs = db.get_code_diffs(active_model_id, diff_hash)
        
        self.tab_widget.file_list.blockSignals(True)
        self.tab_widget.file_list.clear()
        for d in self.current_diffs:
            status_char = "[M]" if d["status"] == "modified" else "[A]" if d["status"] == "added" else "[D]"
            item = QtWidgets.QListWidgetItem(f"{status_char} {d['file_path']}")
            self.tab_widget.file_list.addItem(item)
        self.tab_widget.file_list.blockSignals(False)

        if self.current_diffs:
            self.tab_widget.file_list.setCurrentRow(0)
        else:
            self.tab_widget.txt_old.clear()
            self.tab_widget.txt_new.clear()

        # Load AI Change Log from model metadata if present
        meta = db.get_model_metadata(active_model_id)
        ai_changelog = meta.get("ai_change_log", "")
        if ai_changelog:
            self.tab_widget.txt_ai_changelog.setMarkdown(ai_changelog)
        else:
            self.tab_widget.txt_ai_changelog.setHtml(
                "<h3>No AI Change Log Generated</h3>"
                "<p>Click the <b>Generate AI Change Log</b> button above to build an AI summary of differences.</p>"
            )

    def on_file_selected(self, row):
        if row < 0 or row >= len(self.current_diffs):
            return
        diff_data = self.current_diffs[row]
        aligned_old, aligned_new = parse_and_align_diff(diff_data["unified_diff"])
        self.tab_widget.set_diff_view(aligned_old, aligned_new)

    def on_compare_release_changed(self, idx):
        pass # Optional hook if user wants to change comparison, but diffing relies on folders

    def on_compute_diffs(self):
        arch = self._arch()
        db = self._db()
        if not arch or not db:
            return
            
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if active_model_id is None:
            QtWidgets.QMessageBox.warning(self.main_window, "Compute Diffs", "No active architecture model selected.")
            return

        # #2E: diff the CURRENT (active) release against the SELECTED comparison
        # release — both read from the DB source store. No folder pickers.
        current_rid = db.get_active_release_id()
        idx = self.tab_widget.cmb_compare_release.currentIndex()
        previous_rid = self.tab_widget.cmb_compare_release.itemData(idx) if idx >= 0 else None
        if current_rid is None or previous_rid is None:
            QtWidgets.QMessageBox.warning(
                self.main_window, "Compute Diffs",
                "Select a comparison release. The active release is compared against it.")
            return
        if not db.has_release_source(current_rid) or not db.has_release_source(previous_rid):
            QtWidgets.QMessageBox.warning(
                self.main_window, "Compute Diffs",
                "Both the active release and the selected comparison release must have "
                "source imported (Release Selection → Map / Import Source Code).")
            return

        from Application_Logic.Logic_Loading_Window import LoadingDialog
        loader = LoadingDialog(self.main_window)
        loader.ui.lbl_loading_text.setText("Computing file-by-file differences from the database...")

        def run_diff_task(db_path, cur_rid, prev_rid):
            # Worker-owned connection (WAL-independent) + DB release providers.
            from Application_Logic.Logic_Database import ProjectDatabase
            from Application_Logic.Logic_Source_Store import DbReleaseSourceProvider
            from Application_Logic.Logic_AI_Context import diff_source_folders, compute_diff_hash
            wdb = ProjectDatabase()
            try:
                wdb.open(db_path, create_schema=False, apply_journal=False)
                cur_p = DbReleaseSourceProvider(wdb, cur_rid)
                prev_p = DbReleaseSourceProvider(wdb, prev_rid)
                diff_hash = compute_diff_hash(cur_p, prev_p)
                diffs = diff_source_folders(cur_p, prev_p)
                return diff_hash, diffs
            finally:
                try:
                    wdb.close()
                except Exception:
                    pass

        # Pause auto-save so the main connection stays idle during the worker build.
        if self.main_window is not None:
            self.main_window._codemap_building = True
        db.set_activity("diff", "in_progress", "release comparison")
        db.commit()
        ran = loader.run_task(run_diff_task, db.db_path, current_rid, previous_rid)
        if self.main_window is not None:
            self.main_window._codemap_building = False
        db.set_activity("", "idle")
        db.commit()
        if ran:
            diff_hash, diffs = loader.result
            db.save_code_diffs(active_model_id, diff_hash, diffs)
            # Record the diff hash on the per-release map + the shared "last diff"
            # meta so the AI Chat marker and chat get_diff see it.
            db.set_model_diff_hash(active_model_id, diff_hash, release_id=current_rid)
            db.set_meta("ai_last_diff_hash", diff_hash)
            db.commit()
            self.load_data()
            QtWidgets.QMessageBox.information(self.main_window, "Success", "Release differences computed successfully!")
        else:
            QtWidgets.QMessageBox.critical(self.main_window, "Error", f"Failed to compute differences:\n{loader.error_msg}")

    def on_generate_ai_changelog(self):
        arch = self._arch()
        db = self._db()
        if not arch or not db:
            return
            
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if active_model_id is None:
            return

        chat_ctrl = getattr(self.main_window, "ai_chat_controller", None)
        if not chat_ctrl:
            QtWidgets.QMessageBox.warning(self.main_window, "AI Change Log", "AI Chat module is not loaded.")
            return

        pid = chat_ctrl.cmb_provider.currentData()
        # currentData() is the model id the providers expect; currentText() is the
        # human display name and produced "unknown model" failures.
        model = chat_ctrl.cmb_model.currentData()
        from Application_Logic import Logic_AI_Providers as providers
        if not pid or not model or not providers.get_provider(pid).is_configured():
            QtWidgets.QMessageBox.warning(
                self.main_window, "AI Change Log", 
                "Please configure an AI Provider and select a model in the 'Advanced AI Chat' tab first."
            )
            return

        if not self.current_diffs:
            QtWidgets.QMessageBox.warning(self.main_window, "AI Change Log", "Please compute release diffs first.")
            return

        # Prepare diff content for LLM prompt
        diff_texts = []
        total_len = 0
        MAX_PROMPT_DIFF_LEN = 15000
        
        for d in self.current_diffs:
            header = f"\n--- File: {d['file_path']} ({d['status']}) ---\n"
            content = d["unified_diff"]
            if total_len + len(header) + len(content) > MAX_PROMPT_DIFF_LEN:
                diff_texts.append(header + "(unified diff content truncated for token limits...)")
                break
            diff_texts.append(header + content)
            total_len += len(header) + len(content)

        diffs_combined = "".join(diff_texts)
        active_model_name = next((m.name for m in arch.model_manager.models if m.id == active_model_id), "Active Model")

        prompt = (
            f"Analyze the following software source code differences for the architecture model '{active_model_name}'.\n"
            f"Generate a professional, structured software change log suited for automotive/embedded standards (e.g. ASPICE, ISO 26262).\n"
            f"Summarize what was added, modified, or deleted, highlighting potential side-effects, safety-critical function changes, "
            f"and interface impacts.\n\n"
            f"--- Code Differences ---\n"
            f"{diffs_combined}"
        )

        self.btn_gen_ai_log.setEnabled(False)
        self.btn_gen_ai_log.setText("Generating Change Log via AI...")
        if db:
            db.set_activity("ailog", "in_progress", active_model_name)

        self.ai_worker = AIChangeLogWorker(pid, model, prompt, self)
        self.ai_worker.finished_ok.connect(self.on_ai_finished)
        self.ai_worker.failed.connect(self.on_ai_failed)
        self.ai_worker.start()

    def on_ai_finished(self, text):
        self.btn_gen_ai_log.setEnabled(True)
        self.btn_gen_ai_log.setText("Generate AI Change Log (requires AI Token)")
        _db0 = self._db()
        if _db0:
            _db0.set_activity("", "idle")

        self.tab_widget.txt_ai_changelog.setMarkdown(text)
        
        # Save to DB
        db = self._db()
        arch = self._arch()
        active_model_id = getattr(arch.model_manager, "active_model_id", None)
        if db and active_model_id is not None:
            meta = db.get_model_metadata(active_model_id)
            meta["ai_change_log"] = text
            db.save_model_metadata(active_model_id, meta)
            db.commit()

        QtWidgets.QMessageBox.information(self.main_window, "Success", "AI Change Log generated and saved successfully!")

    def on_ai_failed(self, err_msg):
        self.btn_gen_ai_log.setEnabled(True)
        self.btn_gen_ai_log.setText("Generate AI Change Log (requires AI Token)")
        _db0 = self._db()
        if _db0:
            _db0.set_activity("", "idle")
        QtWidgets.QMessageBox.critical(self.main_window, "AI Error", f"Failed to generate AI change log:\n{err_msg}")
