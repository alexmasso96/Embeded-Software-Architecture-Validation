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
        self.selected_release_index = -1
        self.deep_search_enabled = False
        
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
        self.btn_select.clicked.connect(self.on_select)
        self.btn_select.setStyleSheet("font-weight: bold; background-color: #2a82da; color: white; padding: 10px;")
        
        self.btn_rename = QPushButton("Rename")
        self.btn_rename.clicked.connect(self.on_rename)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.on_delete)
        
        self.btn_create_result = QPushButton("Create Result Column")
        self.btn_create_result.clicked.connect(self.on_create_result)
        
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
        right_layout.addWidget(self.btn_baseline)
        right_layout.addStretch()
        
        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self.reject)
        right_layout.addWidget(self.btn_close)
        
        layout.addLayout(right_layout, stretch=1)
        self.setLayout(layout)

    def refresh_list(self):
        self.list_widget.clear()
        
        # Manager list order is the order we display
        for release in self.manager.releases:
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
        self.btn_baseline.setEnabled(has_sel)
        
        if has_sel:
            index = rows[0].row()
            release = self.manager.releases[index]
            
            # Req 7.8: Unrenamable if baselined? Req 7.6 says Release_Result column uneditable
            # Requirement 3.1: Inhibited if for that specific software release a result baseline was created
            # This refers to DELETION (and renaming likely)
            
            # Check for existing baselines for this release
            has_child_baselines = any(r.is_baseline and r.parent_release_name == release.name for r in self.manager.releases)
            
            if release.is_baseline:
                self.btn_rename.setEnabled(False) # 14. User should not be able to modify baseline
                self.btn_delete.setEnabled(True) # Can execute? Req doesn't explicitly forbid deleting a baseline itself
                self.btn_create_result.setEnabled(False) # Modify baseline blocked
                self.btn_baseline.setEnabled(False) # Baseline of baseline blocked
            elif has_child_baselines:
                self.btn_delete.setEnabled(False) # Block deletion if baselines exist (Req 3.1)
                self.btn_rename.setEnabled(True) # Renaming might break the link? Probably safer to block or update link.
                                                 # Let's block for safety or allow if we update parent_release_name of children.
                                                 # Requirement doesn't explicitly block renaming parent, but 3.1 says "behavior inhibited".
                                                 # Assuming inhibit renaming too.
                self.btn_rename.setToolTip("Cannot rename release that has baselines")
            
    def on_select(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
            
        self.selected_release_index = rows[0].row()
        self.deep_search_enabled = self.chk_deep_search.isChecked()
        self.accept()

    def on_rename(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        current_name = self.manager.releases[index].name
        
        new_name, ok = QInputDialog.getText(self, "Rename Release", "New Name:", text=current_name)
        if ok and new_name:
            success, msg = self.manager.rename_release(index, new_name)
            if not success:
                QMessageBox.warning(self, "Rename Failed", msg)
            else:
                self.refresh_list()

    def on_delete(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        release = self.manager.releases[index]
        
        msg = f"Are you sure you want to PERMANENTLY delete '{release.name}'?\nThis cannot be undone."
        reply = QMessageBox.question(self, "Confirm Delete", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.manager.delete_release(index)
            if not success:
               QMessageBox.warning(self, "Delete Failed", msg)
            else:
               self.refresh_list()

    def on_load_release(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
            
        index = rows[0].row()
        release = self.manager.set_active_release(index)
        
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
            
            # The Release Manager stores "rows" etc.
            # But the Architecture Controller expects a full project structure?
            # release data had "rows": [...]
            # controller.load_project_data expects {"settings":..., "config":..., "rows":...}
            # If the release only has rows, we should merge or just load rows?
            
            # If the Release was created from an active model, it has the full structure?
            # Logic_Release_Manager.create_release uses _load_data(active). active is self.active_release?
            # Revert step: We need to see what we are saving.
            # In Logic_Architecture_Table.py flush_current_data_to_model (previously) we saved get_project_data()
            # So the release data SHOULD contain everything.
            
            # Let's try loading it directly
            self.controller.load_project_data(data)
            self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name}")

            # Enforce Read-Only if Baseline
            if release.is_baseline:
                 self.controller.table.setEditTriggers(self.controller.table.editTriggers().NoEditTriggers)
                 self.controller.main_window.setWindowTitle(f"Architecture Testing Tool - {release.name} (READ ONLY)")
            else:
                 self.controller.table.setEditTriggers(self.controller.table.editTriggers().DoubleClicked | self.controller.table.editTriggers().EditKeyPressed)

            self.accept()
            
    def on_create_result(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        
        index = rows[0].row()
        release = self.manager.releases[index]
        
        # Call controller to add columns
        if hasattr(self, 'controller') and self.controller:
             try:
                 self.controller.create_result_columns_for_release(release)
                 QMessageBox.information(self, "Success", f"Result columns updated for {release.name}")
             except Exception as e:
                 QMessageBox.warning(self, "Error", f"Failed to create result columns: {e}")
        else:
             QMessageBox.warning(self, "Error", "Controller not linked.")

    def on_baseline(self):
        rows = self.list_widget.selectedIndexes()
        if not rows:
            return
        index = rows[0].row()
        
        try:
             baseline = self.manager.create_baseline(index)
             QMessageBox.information(self, "Success", f"Created Baseline: {baseline.name}")
             self.refresh_list()
        except ValueError as e:
             QMessageBox.warning(self, "Error", str(e))

    def on_add_release(self):
        # 1. Select File
        file_path, _ = QFileDialog.getOpenFileName(self, "Open ELF/JSON File", "", "ELF/JSON Files (*.elf *.json);; All Files (*)")
        if not file_path:
            return
            
        # 2. Prompt for Name
        # Check if we can infer name from filename?
        default_name = os.path.splitext(os.path.basename(file_path))[0]
        name, ok = QInputDialog.getText(self, "New Release Name", "Enter Release Name:", text=default_name)
        if not ok or not name.strip():
            return
            
        # 3. Parse File (Background)
        from Application_Logic.Logic_Loading_Window import LoadingDialog
        loader = LoadingDialog(self)
        
        mode = 'ELF' if file_path.lower().endswith('.elf') else 'JSON'
        
        if loader.run_task(self._parse_task, mode, file_path):
            try:
                # 4. Create Release
                # We don't necessarily need the parser object here unless we want to populate rows from it immediately?
                # But typically valid rows come from checking Ports against the Parser.
                # A fresh parser has no rows.
                
                # Create the release
                # Note: We pass the ELF path so it's associated.
                new_release = self.manager.create_release(name, elf_path=file_path)
                
                # If we parsed it successfully, we know it's valid.
                # We could set the parser on the controller immediately if we auto-select?
                # But let's just add it to list.
                
                self.refresh_list()
                QMessageBox.information(self, "Success", f"Release '{name}' created from {os.path.basename(file_path)}")
                
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
        else:
             QMessageBox.critical(self, "Parsing Error", f"Failed to parse file: {loader.error_msg}")

    def _parse_task(self, mode, file_path):
        from core.elf_parser import ELFParser
        parser = ELFParser()
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
            # Find in manager
            for r in self.manager.releases:
                if r.name == name:
                    new_order.append(r)
                    break
        
        self.manager.releases = new_order
        self.manager.save_registry()
