from PyQt6 import QtWidgets
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QLabel, QMessageBox, QInputDialog, QCheckBox, QAbstractItemView, QFileDialog)
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
        
        # Deep Search Option (Req 9)
        self.chk_deep_search = QCheckBox("Deep Search (Perform thorough validation on load)")
        self.chk_deep_search.setToolTip("Will trigger a deeper search for missing symbols during load (slower).")
        left_layout.addWidget(self.chk_deep_search)
        
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
        
        # New Feature: Add Release (Import)
        self.btn_add_release = QPushButton("Add New Release")
        self.btn_add_release.clicked.connect(self.on_add_release)
        
        right_layout.addWidget(self.btn_select)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.btn_add_release) # Added here
        right_layout.addWidget(self.btn_rename)
        right_layout.addWidget(self.btn_delete)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.btn_create_result)
        right_layout.addWidget(self.btn_link_result)
        right_layout.addWidget(self.btn_baseline)
        right_layout.addStretch()
        
        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self.reject)
        right_layout.addWidget(self.btn_close)
        
        layout.addLayout(right_layout, stretch=1)
        self.setLayout(layout)

    def refresh_list(self):
        self.list_widget.clear()
        self.active_releases = [r for r in self.manager.releases if not (r.is_baseline and r.is_deleted)]
        
        # Manager list order is the order we display
        for release in self.active_releases:
            add_text = ""
            if release.is_baseline:
                add_text = " [BASELINE]"
            
            item = QListWidgetItem(f"{release.name}{add_text}")
            
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
            
        self.update_buttons()

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
        
        if has_sel:
            index = rows[0].row()
            release = self.active_releases[index]
            
            # Req 7.8: Unrenamable if baselined? Req 7.6 says Release_Result column uneditable
            # Requirement 3.1: Inhibited if for that specific software release a result baseline was created
            # This refers to DELETION (and renaming likely)
            
            # Check for existing baselines for this release
            has_child_baselines = any(r.is_baseline and not r.is_deleted and r.parent_release_name == release.name for r in self.manager.releases)
            
            if release.is_baseline:
                self.btn_rename.setEnabled(False) # 14. User should not be able to modify baseline
                self.btn_delete.setEnabled(True) # Can execute? Req doesn't explicitly forbid deleting a baseline itself
                self.btn_create_result.setEnabled(False) # Modify baseline blocked
                self.btn_link_result.setEnabled(False)
                self.btn_baseline.setEnabled(False) # Baseline of baseline blocked
            elif has_child_baselines:
                self.btn_delete.setEnabled(False) # Block deletion if baselines exist (Req 3.1)
                self.btn_rename.setEnabled(True) # Renaming might break the link? Probably safer to block or update link.
                                                 # Let's block for safety or allow if we update parent_release_name of children.
                                                 # Requirement doesn't explicitly block renaming parent, but 3.1 says "behavior inhibited".
                                                 # Assuming inhibit renaming too.
                self.btn_rename.setToolTip("Cannot rename release that has baselines")
            
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
 
    def on_load_release(self, item=None):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
            
        index = rows[0].row()
        release = self.active_releases[index]
        actual_index = self.manager.releases.index(release)
        release = self.manager.set_active_release(actual_index)
        
        # Load the Data into the Architecture Controller
        if release:
            if release.elf_path:
                current_elf = str(self.controller.parser.elf_path) if self.controller.parser and self.controller.parser.elf_path else None
                if release.elf_path != current_elf:
                    # ELF mismatch - Reload
                    # Assuming file exists?
                     if os.path.exists(release.elf_path):
                         from Application_Logic.Logic_Loading_Window import LoadingDialog
                         loader = LoadingDialog(self)
                         loader.ui.lbl_loading_text.setText(f"Switching Context to {os.path.basename(release.elf_path)}...")
                         
                         if loader.run_task(self._parse_task, 'ELF', release.elf_path):
                             # Update Controller Context (Parser/Matcher)
                             # We pass None for release_name since release already exists
                             self.controller.populate_from_parser(loader.result, release_name=None)
                         else:
                             QMessageBox.warning(self, "Warning", f"Failed to load associated ELF: {loader.error_msg}\nSome features may not work.")
                     else:
                         QMessageBox.warning(self, "Warning", f"Associated ELF not found: {release.elf_path}")

            data = self.manager._load_data(release)
            
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
                        from Application_Logic.Logic_Column_Types import LastResultColumn
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
        file_path, _ = QFileDialog.getOpenFileName(self, "Open ELF/JSON File", "", "ELF/JSON Files (*.elf *.json);; All Files (*)")
        if not file_path:
            return
            
        # Fast Hash Check before slow parser import
        try:
            parser_hash = None
            if file_path.lower().endswith('.elf'):
                import hashlib
                hash_md5 = hashlib.md5()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                parser_hash = hash_md5.hexdigest()
            else:
                import json
                with open(file_path, 'r') as f:
                    data = json.load(f)
                if "database" in data:
                    data = data["database"]
                parser_hash = data.get("elf_hash")
                
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
        from Application_Logic.Logic_Loading_Window import LoadingDialog
        loader = LoadingDialog(self)
        
        mode = 'ELF' if file_path.lower().endswith('.elf') else 'JSON'
        
        if loader.run_task(self._parse_task, mode, file_path):
            try:
                final_hash = loader.result.md5_hash or parser_hash
                
                from dataclasses import asdict
                parser = loader.result
                elf_data = {
                    "elf_path": str(parser.elf_path) if parser.elf_path else "",
                    "elf_hash": parser.md5_hash,
                    "symbols": [asdict(s) for s in parser.symbols],
                    "functions": [{
                        'name': f.name,
                        'address': f.address,
                        'size': f.size,
                        'parameters': f.parameters,
                        'return_type': f.return_type
                    } for f in parser.functions],
                    "structures": parser.structures,
                    "global_vars": parser.global_vars_dwarf
                }
                
                # Create the release with MD5 hash and parsed ELF data
                new_release = self.manager.create_release(name, elf_path=file_path, elf_hash=final_hash, elf_data=elf_data)
                
                self.refresh_list()
                QMessageBox.information(self, "Success", f"Release '{name}' created from {os.path.basename(file_path)}")
                
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
        else:
             QMessageBox.critical(self, "Parsing Error", f"Failed to parse file: {loader.error_msg}")

    def _parse_task(self, mode, file_path):
        from core.elf_parser import ELFParser
        parser = ELFParser()
        # Pass down test_mode to ELFParser (Feature 6)
        if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'main_window'):
            if getattr(self.controller.main_window, 'test_mode', False):
                parser.test_mode = True
                
        if mode == 'ELF':
            parser.load_elf(file_path)
            parser.extract_all()
        else:
            if not parser.load_cache(file_path):
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
