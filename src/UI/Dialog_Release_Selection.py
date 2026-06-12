from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QLabel, QInputDialog, QAbstractItemView, QFileDialog)
from UI.StyledMessageBox import StyledMessageBox as QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from Application_Logic.Logic_Release_Manager import ReleaseManager
import os

class ReleaseSelectionDialog(QDialog):
    def __init__(self, release_manager: ReleaseManager, architecture_controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Release Selection")
        self.resize(700, 500)
        self.manager = release_manager
        self.controller =  architecture_controller
        self.active_releases = []
        
        self.init_ui()
        self.refresh_list()
        
    def init_ui(self):
        layout = QHBoxLayout()
        
        # Left: List View
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Available Software Releases:"))
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self.on_load_release)
        
        # Drag and drop for reordering
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.model().rowsMoved.connect(self.on_reorder)
        
        left_layout.addWidget(self.list_widget)

        layout.addLayout(left_layout, stretch=2)
        
        # Right: Actions
        right_layout = QVBoxLayout()
        
        self.btn_select = QPushButton("Select / Load")
        self.btn_select.clicked.connect(self.on_load_release)
        self.btn_select.setStyleSheet("font-weight: bold; background-color: #2a82da; color: white; padding: 10px;")
        
        self.btn_rename = QPushButton("Rename")
        self.btn_rename.clicked.connect(self.on_rename)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.on_delete)
        
        self.btn_create_result = QPushButton("Create Result Column")
        self.btn_create_result.clicked.connect(self.on_create_result)

        self.btn_link_result = QPushButton("Link Last Result")
        self.btn_link_result.clicked.connect(self.on_link_result)
        
        self.btn_baseline = QPushButton("Create Baseline")
        self.btn_baseline.clicked.connect(self.on_baseline)

        self.btn_toggle_lock = QPushButton("Lock/Unlock Release")
        self.btn_toggle_lock.clicked.connect(self.on_toggle_lock)
        
        # New Feature: Add Release (Import)
        self.btn_add_release = QPushButton("Add New Release")
        self.btn_add_release.clicked.connect(self.on_add_release)

        # #2E: the ONE real source-folder picker — imports source INTO the DB,
        # keyed by the selected release. Unload drops the blobs (keeps maps).
        self.btn_import_source = QPushButton("Map / Import Source Code")
        self.btn_import_source.clicked.connect(self.on_import_source)
        self.btn_unload_source = QPushButton("Unload Source")
        self.btn_unload_source.clicked.connect(self.on_unload_source)

        right_layout.addWidget(self.btn_select)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.btn_add_release) # Added here
        right_layout.addWidget(self.btn_rename)
        right_layout.addWidget(self.btn_delete)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.btn_import_source)
        right_layout.addWidget(self.btn_unload_source)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.btn_create_result)
        right_layout.addWidget(self.btn_link_result)
        right_layout.addWidget(self.btn_baseline)
        right_layout.addWidget(self.btn_toggle_lock)
        right_layout.addStretch()
        
        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self.reject)
        right_layout.addWidget(self.btn_close)
        
        layout.addLayout(right_layout, stretch=1)
        self.setLayout(layout)

    def refresh_list(self):
        # Remember selection
        selected_name = None
        curr_row = self.list_widget.currentRow()
        if curr_row >= 0 and curr_row < len(self.active_releases):
            selected_name = self.active_releases[curr_row].name

        self.list_widget.clear()
        self.active_releases = [r for r in self.manager.releases if not (r.is_baseline and r.is_deleted)]

        # #2E: which releases have source imported (cheap one-shot query → ✓/○).
        db = self._db()
        source_ids = db.get_release_ids_with_source() if db else set()

        # Manager list order is the order we display
        select_row = -1
        for i, release in enumerate(self.active_releases):
            add_text = ""
            if release.is_baseline:
                add_text = " [BASELINE]"

            src_mark = " 📄" if release.id in source_ids else ""
            item = QListWidgetItem(f"{release.name}{add_text}{src_mark}")
            
            # Highlight Active
            if self.manager.active_release_index != -1:
                active_rel = self.manager.releases[self.manager.active_release_index]
                if release is active_rel:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor("#2a82da"))

            if release.is_baseline:
                 item.setForeground(QColor("gray"))
            
            self.list_widget.addItem(item)
            if selected_name and release.name == selected_name:
                select_row = i
                
        if select_row >= 0:
            self.list_widget.setCurrentRow(select_row)
        else:
            self.update_buttons()

    def _db(self):
        return (getattr(self.controller, '_db', None)
                or getattr(getattr(self.controller, 'main_window', None), 'project_db', None))

    def on_selection_changed(self):
        self.update_buttons()

    def update_buttons(self):
        rows = self.list_widget.selectedIndexes()
        has_sel = len(rows) > 0

        self.btn_select.setEnabled(has_sel)
        self.btn_rename.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_create_result.setEnabled(has_sel)
        self.btn_link_result.setEnabled(has_sel)
        self.btn_baseline.setEnabled(has_sel)
        self.btn_toggle_lock.setEnabled(has_sel)
        self.btn_import_source.setEnabled(has_sel)
        self.btn_unload_source.setEnabled(has_sel)

        if has_sel:
            index = rows[0].row()
            release = self.active_releases[index]

            # #2E: source import/unload — baselines are frozen snapshots, never
            # re-sourced; unload only matters when source is actually stored.
            db = self._db()
            has_source = bool(db and release.id is not None
                              and db.has_release_source(release.id))
            self.btn_import_source.setEnabled(not release.is_baseline)
            self.btn_unload_source.setEnabled(has_source and not release.is_baseline)

            if release.is_baseline:
                self.btn_toggle_lock.setText("🔓 Unfreeze Baseline")
                self.btn_rename.setEnabled(False) # 14. User should not be able to modify baseline
                self.btn_delete.setEnabled(True) # Can execute? Req doesn't explicitly forbid deleting a baseline itself
                self.btn_create_result.setEnabled(False) # Modify baseline blocked
                self.btn_link_result.setEnabled(False)
                self.btn_baseline.setEnabled(False) # Baseline of baseline blocked
            else:
                self.btn_toggle_lock.setText("🔒 Freeze Release")
                
                # Check for existing baselines for this release
                has_child_baselines = any(r.is_baseline and not r.is_deleted and r.parent_release_name == release.name for r in self.manager.releases)
                if has_child_baselines:
                    self.btn_delete.setEnabled(False) # Block deletion if baselines exist (Req 3.1)
                    self.btn_rename.setEnabled(True) # Renaming might break the link? Probably safer to block or update link.
                                                     # Let's block for safety or allow if we update parent_release_name of children.
                                                     # Requirement doesn't explicitly block renaming parent, but 3.1 says "behavior inhibited".
                    self.btn_rename.setToolTip("Cannot rename release that has baselines")                                 # Assuming inhibit renaming too.
                self.btn_rename.setToolTip("Cannot rename release that has baselines")
            
    # ------------------------------------------------------------------
    # #2E — import / unload source code (keyed by release)
    # ------------------------------------------------------------------

    def _selected_release(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return None
        return self.active_releases[rows[0].row()]

    def on_import_source(self):
        release = self._selected_release()
        if release is None or release.is_baseline or release.id is None:
            return
        db = self._db()
        if not (db and db.is_open):
            QMessageBox.warning(self, "Import Source", "No open project database.")
            return

        folder = QFileDialog.getExistingDirectory(
            self, f"Select Source Folder for Release '{release.name}'", "",
            QFileDialog.Option(0))
        if not folder:
            return

        if db.has_release_source(release.id):
            box = QMessageBox(self)
            box.setWindowTitle("Replace Source")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(f"Release '{release.name}' already has source stored.\n"
                        f"Replace it with the contents of:\n{folder}?")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.exec()
            if box.result_button != QMessageBox.StandardButton.Yes:
                return

        # Gate the main thread the same way the Code Map build does: pause auto-save
        # so the main connection stays idle while the worker writes on its OWN
        # connection (WAL-independent — safe even in DELETE journal mode).
        main_window = getattr(self.controller, 'main_window', None)
        if main_window is not None:
            main_window._codemap_building = True
        try:
            db.set_activity("sourceimport", "in_progress", release.name)
            db.commit()
        except Exception:
            pass

        from UI.loading_window import LoadingDialog
        loader = LoadingDialog(self)
        loader.ui.lbl_loading_text.setText(f"Importing source for {release.name}…")
        ok = loader.run_task(self._import_source_task, db.db_path, release.id, folder)

        if main_window is not None:
            main_window._codemap_building = False
        try:
            db.set_activity("", "idle")
            db.commit()
        except Exception:
            pass

        if ok:
            self.refresh_list()
            QMessageBox.information(
                self, "Import Source",
                f"Imported {loader.result} source files into release '{release.name}'.")
        else:
            QMessageBox.critical(self, "Import Source",
                                 f"Failed to import source: {loader.error_msg}")

    def _import_source_task(self, db_path, release_id, folder):
        """Worker thread: walk the folder and store each file (gzip) on the worker's
        OWN DB connection, logging per file so the loading window stays responsive."""
        import logging
        from Application_Logic.Logic_Database import ProjectDatabase
        from Application_Logic.Logic_Source_Store import FilesystemSourceProvider
        log = logging.getLogger("Source Import")
        wdb = ProjectDatabase()
        try:
            wdb.open(db_path, create_schema=False, apply_journal=False)
            prov = FilesystemSourceProvider(folder)
            files = prov.list_files()
            total = len(files)
            if total == 0:
                log.info("No C/C++ source files found in the selected folder.")
                return 0
            log.info(f"Found {total} source files — importing…")

            def gen():
                for sf in files:
                    text = prov.read_file(sf.rel_path)
                    if text is not None:
                        yield sf.rel_path, text

            def progress(rel, idx, _t):
                log.info(f"Indexing {idx}/{total}: {rel}")

            n = wdb.save_release_source_files(release_id, gen(), progress=progress)
            log.info(f"Stored {n} source files in the project database.")
            return n
        finally:
            try:
                wdb.close()
            except Exception:
                pass

    def on_unload_source(self):
        release = self._selected_release()
        if release is None or release.id is None:
            return
        db = self._db()
        if not (db and db.is_open) or not db.has_release_source(release.id):
            return
        box = QMessageBox(self)
        box.setWindowTitle("Unload Source")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Remove the stored source code for release '{release.name}'?\n\n"
                    f"Mind maps and code maps for this release are kept — only the raw "
                    f"source files are dropped.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.exec()
        if box.result_button != QMessageBox.StandardButton.Yes:
            return
        db.delete_release_source(release.id)
        db.commit()
        self.refresh_list()
        QMessageBox.information(self, "Unload Source",
                               f"Source code unloaded for release '{release.name}'.")

    def on_rename(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        release = self.active_releases[index]
        actual_index = self.manager.releases.index(release)
        current_name = release.name
        
        new_name, ok = QInputDialog.getText(self, "Rename Release", "New Name:", text=current_name)
        if ok and new_name:
            success, msg = self.manager.rename_release(actual_index, new_name)
            if not success:
                QMessageBox.warning(self, "Rename Failed", msg)
            else:
                self.refresh_list()

    def on_delete(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        release = self.active_releases[index]
        actual_index = self.manager.releases.index(release)
        
        if release.is_baseline:
            # Prompt for comment
            comment, ok = QInputDialog.getMultiLineText(
                self, "Delete Baseline", 
                f"Enter deletion reason/comment for baseline '{release.name}':"
            )
            if not ok:
                return
            comment = comment.strip()
            
            success, msg = self.manager.delete_release(actual_index, deletion_comment=comment)
            if not success:
                QMessageBox.warning(self, "Delete Failed", msg)
            else:
                self.refresh_list()
                if hasattr(self, 'controller') and hasattr(self.controller, 'refresh_all_column_locking'):
                    self.controller.refresh_all_column_locking()
        else:
            msg = f"Are you sure you want to PERMANENTLY delete '{release.name}'?\nThis cannot be undone."
            reply = QMessageBox.question(self, "Confirm Delete", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                success, msg = self.manager.delete_release(actual_index)
                if not success:
                   QMessageBox.warning(self, "Delete Failed", msg)
                else:
                   self.refresh_list()
 
    def on_toggle_lock(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        release = self.active_releases[index]
        actual_index = self.manager.releases.index(release)

        if release.is_baseline:
            # Requires master password
            if not getattr(self.controller, "master_password_hash", None):
                QMessageBox.warning(self, "Unfreeze Baseline", "A master password must be configured on the project to unlock a baseline.")
                return

            from Application_Logic.Logic_Security import SecurityManager
            from UI.Dialog_Master_Password import MasterPasswordPromptDialog
            prompt = MasterPasswordPromptDialog(self, "Enter Master Password to Unfreeze Baseline:")
            if prompt.exec():
                entered = prompt.get_password()
                if SecurityManager.verify_password(entered, self.controller.master_password_hash):
                    release.is_baseline = False
                    if self.manager._db:
                        self.manager._db.update_release(release.id, is_baseline=0)
                        self.manager.log_baseline_event(release, frozen=False)  # NC-4
                        self.manager._db.commit()
                    self.refresh_list()
                    self.update_buttons()
                    
                    # Update active release UI edit triggers immediately if currently loaded
                    active_rel = self.manager.get_active_release()
                    if active_rel and active_rel.id == release.id:
                        if hasattr(self.controller, 'btn_exit_baseline'):
                            self.controller.btn_exit_baseline.setVisible(False)
                        from PyQt6.QtWidgets import QAbstractItemView
                        self.controller.table.setEditTriggers(
                            QAbstractItemView.EditTrigger.DoubleClicked |
                            QAbstractItemView.EditTrigger.AnyKeyPressed
                        )
                        self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name}")

                    QMessageBox.information(self, "Success", f"Baseline '{release.name}' has been unfrozen. You can now edit its table data.")
                else:
                    QMessageBox.critical(self, "Access Denied", "Incorrect master password.")
        else:
            # Freezing doesn't require a password
            release.is_baseline = True
            if self.manager._db:
                self.manager._db.update_release(release.id, is_baseline=1)
                self.manager.log_baseline_event(release, frozen=True)  # NC-4
                self.manager._db.commit()
            self.refresh_list()
            self.update_buttons()
            
            # Update active release UI edit triggers immediately if currently loaded
            active_rel = self.manager.get_active_release()
            if active_rel and active_rel.id == release.id:
                if hasattr(self.controller, 'btn_exit_baseline'):
                    self.controller.btn_exit_baseline.setVisible(True)
                self.controller.table.setEditTriggers(self.controller.table.editTriggers().NoEditTriggers)
                self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name} (READ ONLY)")

            QMessageBox.information(self, "Success", f"Release '{release.name}' has been frozen as a baseline.")

    def on_load_release(self, item=None):
        row = self.list_widget.currentRow()
        if row < 0:
            rows = self.list_widget.selectedIndexes()
            if not rows:
                return
            row = rows[0].row()
            
        release = self.active_releases[row]
        actual_index = self.manager.releases.index(release)
        # Finding M: flush pending edits + the active release's data_cache before
        # switching, so unsaved changes can't be discarded by set_active_release().
        try:
            self.controller.flush_pending_edits()
        except Exception:
            pass
        release = self.manager.set_active_release(actual_index)
        
        # Load the Data into the Architecture Controller
        elf_reloaded = False
        if release:
            parser_obj = getattr(self.controller, 'parser', None)
            current_hash = parser_obj.md5_hash if parser_obj else None
            
            db = getattr(self.controller, '_db', None) or getattr(self.controller.main_window, 'project_db', None)
            
            loaded_symbols = False
            if release.elf_hash:
                # 1. DB check - check if symbols are already loaded in database tables
                if db and db.is_open:
                    cur = db._conn.execute("SELECT 1 FROM elf_index WHERE elf_hash=?", (release.elf_hash,))
                    if cur.fetchone():
                        if release.elf_hash != current_hash:
                            from core.elf_parser import ELFParser
                            parser = ELFParser()
                            parser.load_from_db(db, release.elf_hash)
                            parser.elf_path = release.elf_path
                            self.controller.populate_from_parser(parser, release_name=None)
                            elf_reloaded = True
                        loaded_symbols = True

                # 2. Local cache directory check
                if not loaded_symbols and db and db.is_open:
                    cache_dir = db.db_path + ".elf_caches"
                    cache_file = os.path.join(cache_dir, f"elf_{release.elf_hash}.json")
                    if os.path.exists(cache_file):
                        from UI.loading_window import LoadingDialog
                        loader = LoadingDialog(self)
                        loader.ui.lbl_loading_text.setText(f"Loading local cache for release {release.name}...")
                        if loader.run_task(self._parse_task, 'JSON', cache_file):
                            self.controller.populate_from_parser(loader.result, release_name=None)
                            elf_reloaded = True
                            loaded_symbols = True

                # 3. Prompt user to select file on fallback
                if not loaded_symbols:
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle("Locate Release File")
                    msg_box.setIcon(QMessageBox.Icon.Question)
                    msg_box.setText(
                        f"The compiled symbol data for release '{release.name}' is not present in the database or local cache.\n\n"
                        f"Would you like to manually locate the ELF/JSON file for this release?"
                    )
                    msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                    # StyledMessageBox.exec() returns Accepted/Rejected, not the button
                    # enum — read the clicked button from result_button instead.
                    msg_box.exec()
                    reply = msg_box.result_button

                    if reply == QMessageBox.StandardButton.Yes:
                        file_path, _ = QFileDialog.getOpenFileName(
                            self, f"Open ELF/JSON File for Release {release.name}", "",
                            "ELF/JSON Files (*.elf *.json);; All Files (*)",
                            options=QFileDialog.Option(0)
                        )
                        if file_path:
                            from UI.loading_window import LoadingDialog
                            loader = LoadingDialog(self)
                            loader.ui.lbl_loading_text.setText(f"Loading {os.path.basename(file_path)}...")
                            mode = 'ELF' if file_path.lower().endswith('.elf') else 'JSON'
                            if loader.run_task(self._parse_task, mode, file_path):
                                loaded_hash = loader.result.md5_hash
                                if loaded_hash == release.elf_hash:
                                    self.controller.populate_from_parser(loader.result, release_name=None)
                                    release.elf_path = file_path
                                    self.manager.save_registry()
                                    elf_reloaded = True
                                    loaded_symbols = True
                                else:
                                    err_box = QMessageBox(self)
                                    err_box.setWindowTitle("Hash Mismatch")
                                    err_box.setIcon(QMessageBox.Icon.Critical)
                                    err_box.setText(
                                        f"The selected file has hash '{loaded_hash}', but the release expected '{release.elf_hash}'.\n"
                                        f"Please select the correct binary file."
                                    )
                                    err_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                                    err_box.exec()
                            else:
                                err_box = QMessageBox(self)
                                err_box.setWindowTitle("Error")
                                err_box.setIcon(QMessageBox.Icon.Critical)
                                err_box.setText(f"Failed to load file: {loader.error_msg}")
                                err_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                                err_box.exec()
            
            if not loaded_symbols or not release.elf_hash:
                 # Clear parser/matcher when switching to a release with no active/valid loaded symbols
                 self.controller.parser = None
                 self.controller.matcher = None

            data = self.manager._load_data(release)
            is_new_release = not data.get("rows")

            # If the loaded release data has no rows, clone from the active model
            if is_new_release:
                if hasattr(self.controller, 'model_manager') and self.controller.model_manager:
                    active_model = self.controller.model_manager.get_active_model()
                    if active_model:
                        self.controller.flush_current_data_to_model()
                        active_model_data = active_model.data_cache or {}
                        active_rows = active_model_data.get("rows", [])
                        if active_rows:
                            import copy
                            data["rows"] = copy.deepcopy(active_rows)
                            if "column_metadata" in active_model_data:
                                data["column_metadata"] = copy.deepcopy(active_model_data["column_metadata"])
                            if "release_results" in active_model_data:
                                data["release_results"] = copy.deepcopy(active_model_data["release_results"])
                            if "linked_release_column" in active_model_data:
                                data["linked_release_column"] = copy.deepcopy(active_model_data["linked_release_column"])
                            self.manager._save_data(release, data)
            
            # Enforce Read-Only if Baseline
            if release.is_baseline:
                 if hasattr(self.controller, 'btn_exit_baseline'):
                      self.controller.btn_exit_baseline.setVisible(True)
                 self.controller.table.setEditTriggers(self.controller.table.editTriggers().NoEditTriggers)
                 self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name} (READ ONLY)")
            else:
                 if hasattr(self.controller, 'btn_exit_baseline'):
                      self.controller.btn_exit_baseline.setVisible(False)
                 from PyQt6.QtWidgets import QAbstractItemView
                 self.controller.table.setEditTriggers(
                     QAbstractItemView.EditTrigger.DoubleClicked |
                     QAbstractItemView.EditTrigger.AnyKeyPressed
                 )

            # Let's try loading it directly
            self.controller.load_project_data(data)

            # When a different ELF was loaded, re-run the active fuzzy matcher so the
            # (Match) columns reflect the new symbol set. Baselines are read-only
            # snapshots, so their stored matches are left untouched.
            # ASPICE: Skip matching on release switch if the release has saved data to prevent back-and-forth overwrite
            if elf_reloaded and is_new_release and not release.is_baseline:
                self.controller.refresh_fuzzy_matches(
                    show_progress=True,
                    progress_label="Loading symbols for the selected ELF...",
                )

            self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name}")
            if release.is_baseline:
                 self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name} (READ ONLY)")

            self.accept()
            
    def on_create_result(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        
        index = rows[0].row()
        release = self.active_releases[index]
        
        # Call controller to add columns
        if hasattr(self, 'controller') and self.controller:
             try:
                 self.controller.create_result_columns_for_release(release)
                 QMessageBox.information(self, "Success", f"Result columns updated for {release.name}")
             except Exception as e:
                 QMessageBox.warning(self, "Error", f"Failed to create result columns: {e}")
        else:
             QMessageBox.warning(self, "Error", "Controller not linked.")

    def on_link_result(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        
        index = rows[0].row()
        release = self.active_releases[index]
        rel_res_name = f"Release_{release.name}_Result"
        
        # Check if the column exists in active columns
        has_col = False
        if hasattr(self, 'controller') and self.controller:
            has_col = any(c.name == rel_res_name for c in self.controller.active_columns)
            
            if not has_col:
                # Ask user if they want to create and link
                reply = QMessageBox.question(
                    self,
                    "Create and Link Column",
                    f"The result column '{rel_res_name}' does not exist.\n"
                    f"Would you like to create it and link it to 'Last Result'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        self.controller.create_result_columns_for_release(release)
                        has_col = True
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to create column: {e}")
                        return
                else:
                    return
            
            if has_col:
                current_model = self.controller.model_manager.get_active_model()
                if current_model:
                    if current_model.data_cache is None:
                        current_model.data_cache = {}
                    current_model.data_cache["linked_release_column"] = rel_res_name
                    
                    # Force a save to model's cache
                    self.controller.flush_current_data_to_model()
                    
                    # Save to temporary file to mark as dirty
                    if self.controller.main_window.current_project_file:
                        from Application_Logic.Logic_Project_Saving import ProjectSaver
                        ProjectSaver.save_temp(self.controller.main_window, self.controller.main_window.current_project_file)
                    
                    # Update all rows' "Last Result" column values immediately in the table
                    self.controller.table.blockSignals(True)
                    try:
                        from UI.column_types import LastResultColumn
                        # Find the LastResultColumn index
                        last_res_col_idx = -1
                        last_res_col_obj = None
                        for i, col_obj in enumerate(self.controller.active_columns):
                            if isinstance(col_obj, LastResultColumn):
                                last_res_col_idx = i
                                last_res_col_obj = col_obj
                                break
                        
                        # Find the linked ReleaseResultColumn index
                        linked_col_idx = -1
                        for i, col_obj in enumerate(self.controller.active_columns):
                            if col_obj.name == rel_res_name:
                                linked_col_idx = i
                                break
                        
                        if last_res_col_idx != -1 and linked_col_idx != -1:
                            for row in range(self.controller.table.rowCount()):
                                val = "No Result"
                                widget = self.controller.table.cellWidget(row, linked_col_idx)
                                item = self.controller.table.item(row, linked_col_idx)
                                if widget and isinstance(widget, QtWidgets.QComboBox):
                                    val = widget.currentText()
                                elif item:
                                    val = item.text()
                                
                                last_item = self.controller.table.item(row, last_res_col_idx)
                                if not last_item:
                                    last_item = QtWidgets.QTableWidgetItem()
                                    self.controller.table.setItem(row, last_res_col_idx, last_item)
                                last_item.setText(val)
                                last_res_col_obj.on_change(
                                    self.controller.table, row, last_res_col_idx, val, self.controller
                                )
                    finally:
                        self.controller.table.blockSignals(False)
                    
                    QMessageBox.information(
                        self,
                        "Success",
                        f"Linked 'Last Result' to column '{rel_res_name}' successfully."
                    )
                    self.accept()

    def on_baseline(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        release = self.active_releases[index]
        actual_index = self.manager.releases.index(release)
        
        name, ok = QInputDialog.getText(self, "Create Baseline", "Enter Baseline Name:")
        if not ok or not name.strip():
            return
            
        try:
              layout_data = None
              if hasattr(self.controller, 'get_current_layout_data'):
                  layout_data = self.controller.get_current_layout_data()
                  
              active_model_data = {}
              if hasattr(self.controller, 'model_manager') and self.controller.model_manager:
                  active_model = self.controller.model_manager.get_active_model()
                  if active_model:
                      self.controller.flush_current_data_to_model()
                      active_model_data = active_model.data_cache or {}
                  
              baseline = self.manager.create_baseline(actual_index, name, layout_data, active_model_data)
              QMessageBox.information(self, "Success", f"Created Baseline: {baseline.name}")
              self.refresh_list()
              
              if hasattr(self.controller, 'load_active_model_to_table'):
                  self.controller.load_active_model_to_table()
        except ValueError as e:
             QMessageBox.warning(self, "Error", str(e))

    def on_add_release(self):
        # 1. Select File
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open ELF/JSON File", "",
            "ELF/JSON Files (*.elf *.json);; All Files (*)",
            options=QFileDialog.Option(0)
        )
        if not file_path:
            return
            
        # Fast Hash Check before slow parser import
        parser_hash = None
        try:
            if file_path.lower().endswith('.elf'):
                import hashlib
                hash_md5 = hashlib.md5()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                parser_hash = hash_md5.hexdigest()

            if parser_hash:
                for r in self.manager.releases:
                    if r.elf_hash == parser_hash:
                        QMessageBox.warning(self, "Release Already Mapped",
                                            f"The selected file is already mapped to release '{r.name}'.")
                        return
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not perform fast hash check: {e}")
            
        # 2. Prompt for Name
        # Check if we can infer name from filename?
        default_name = os.path.splitext(os.path.basename(file_path))[0]
        name, ok = QInputDialog.getText(self, "New Release Name", "Enter Release Name:", text=default_name)
        if not ok or not name.strip():
            return
            
        # Validate unique name before parsing
        name = name.strip()
        if any(r.name == name for r in self.manager.releases):
            QMessageBox.warning(self, "Error", f"Release '{name}' already exists.")
            return
            
        # 3. Parse File (Background)
        from UI.loading_window import LoadingDialog
        loader = LoadingDialog(self)
        
        mode = 'ELF' if file_path.lower().endswith('.elf') else 'JSON'
        
        if loader.run_task(self._parse_task, mode, file_path):
            try:
                final_hash = loader.result.md5_hash or parser_hash

                parser = loader.result

                # Check if there is an active release currently and prompt
                active = self.manager.get_active_release()
                baseline_previous = False
                if active:
                    msg = f"Creating a new release will set the new release '{name}' as the active (main) release, and freeze the current release '{active.name}' as a baseline.\n\nDo you want to continue?"
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle("Create New Release")
                    msg_box.setIcon(QMessageBox.Icon.Question)
                    msg_box.setText(msg)
                    msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                    # StyledMessageBox.exec() returns Accepted/Rejected, not the button
                    # enum. Without this the "No" branch never matched, so a new
                    # release was created even when the user declined.
                    msg_box.exec()
                    reply = msg_box.result_button
                    if reply == QMessageBox.StandardButton.No:
                        return
                    baseline_previous = True

                # ELF data is stored in SQLite; do not rebuild the legacy in-memory blob.
                self.manager.create_release(name, elf_path=file_path, elf_hash=final_hash, baseline_previous=baseline_previous)

                self.refresh_list()
                QMessageBox.information(self, "Success", f"Release '{name}' created from {os.path.basename(file_path)}")
                
                # Auto-select and load the newly created release
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if name in item.text():
                        item.setSelected(True)
                        self.list_widget.setCurrentRow(i)
                        self.on_load_release()
                        break
                
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
        else:
             QMessageBox.critical(self, "Parsing Error", f"Failed to parse file: {loader.error_msg}")

    def _parse_task(self, mode, file_path):
        from core.elf_parser import ELFParser
        parser = ELFParser()
        db = getattr(self.manager, '_db', None)
        # Pass down test_mode to ELFParser (Feature 6)
        if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'main_window'):
            if getattr(self.controller.main_window, 'test_mode', False):
                parser.test_mode = True
                
        if mode == 'ELF':
            parser.load_elf(file_path)
            if db and db.is_open:
                parser.extract_all_streaming_to_db(db)
            else:
                parser.extract_all()
        else:
            if db and db.is_open:
                imported_hash = ELFParser.import_elf_cache_to_db(file_path, db)
                if not imported_hash:
                    raise ValueError("Failed to load JSON cache")
                parser.load_from_db(db, imported_hash)
                # Silently copy JSON cache file to project's .elf_caches folder
                try:
                    cache_dir = db.db_path + ".elf_caches"
                    os.makedirs(cache_dir, exist_ok=True)
                    dest_file = os.path.join(cache_dir, f"elf_{imported_hash}.json")
                    if not os.path.exists(dest_file):
                        import shutil
                        shutil.copy2(file_path, dest_file)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to copy JSON cache silently: {e}")
            elif not parser.load_cache(file_path):
                raise ValueError("Failed to load JSON cache")
        return parser

    def on_reorder(self, parent, start, end, destination, row):
        # Update manager list to match UI list
        # QListWidget internal move updates the UI.
        # We need to sync the manager.releases list.
        
        # It's easier to rebuild the list from UI?
        # Or use the indexes.
        # Let's just rebuild for simplicity as list is small.
        
        new_order = []
        for i in range(self.list_widget.count()):
            text = self.list_widget.item(i).text()
            # Remove " [BASELINE]" suffix if present to find name
            name = text.replace(" [BASELINE]", "")
            # Find in active list or manager
            for r in self.manager.releases:
                if r.name == name:
                    new_order.append(r)
                    break
        
        # Append any deleted baselines back at the end so we don't lose them
        for r in self.manager.releases:
            if r.is_baseline and r.is_deleted:
                new_order.append(r)
                
        self.manager.releases = new_order
        self.manager.save_registry()


class AllBaselinesDialog(QDialog):
    def __init__(self, release_manager: ReleaseManager, architecture_controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("View All Baselines")
        self.resize(600, 400)
        self.manager = release_manager
        self.controller = architecture_controller
        self.baselines = []
        
        self.init_ui()
        self.refresh_list()
        
    def init_ui(self):
        layout = QHBoxLayout()
        
        # Left: List View
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("All Baselines (Active & Deleted):"))
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self.on_load_baseline)
        
        left_layout.addWidget(self.list_widget)
        layout.addLayout(left_layout, stretch=2)
        
        # Right: Actions
        right_layout = QVBoxLayout()
        
        self.btn_select = QPushButton("Load Baseline")
        self.btn_select.clicked.connect(self.on_load_baseline)
        self.btn_select.setStyleSheet("font-weight: bold; background-color: #2a82da; color: white; padding: 10px;")
        self.btn_select.setEnabled(False)
        
        right_layout.addWidget(self.btn_select)
        right_layout.addStretch()
        
        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self.reject)
        right_layout.addWidget(self.btn_close)
        
        layout.addLayout(right_layout, stretch=1)
        self.setLayout(layout)
        
    def refresh_list(self):
        self.list_widget.clear()
        self.baselines = [r for r in self.manager.releases if r.is_baseline]
        
        for baseline in self.baselines:
            text = baseline.name
            if baseline.is_deleted:
                text += " [DELETED]"
            
            item = QListWidgetItem(text)
            if baseline.is_deleted:
                item.setForeground(QColor("red"))
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
            else:
                item.setForeground(QColor("gray"))
                
            self.list_widget.addItem(item)
            
        self.btn_select.setEnabled(False)
        
    def on_selection_changed(self):
        rows = self.list_widget.selectedIndexes()
        self.btn_select.setEnabled(len(rows) > 0)
        
    def on_load_baseline(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
            
        index = rows[0].row()
        selected_baseline = self.baselines[index]
        
        if selected_baseline.is_deleted:
            QMessageBox.information(
                self, "Deleted Baseline Information",
                f"This baseline was soft-deleted.\n\nReason/Comment:\n{selected_baseline.deletion_comment}"
            )
            
        # Load the baseline
        if hasattr(self.controller, 'load_baseline_by_model'):
            self.controller.load_baseline_by_model(selected_baseline)
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Controller load_baseline_by_model method not found.")
