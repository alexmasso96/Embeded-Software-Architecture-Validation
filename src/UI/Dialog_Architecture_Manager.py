from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListView, 
                               QPushButton, QLabel, QMessageBox, QAbstractItemView)
from PyQt6.QtCore import Qt
from Application_Logic.Logic_Architecture_Models import ArchitectureManager, ArchitectureListModel
from .Dialog_Architecture_Edit import ArchitectureEditDialog
from .Dialog_Restore_Model import RestoreModelDialog

class ArchitectureManagerDialog(QDialog):
    def __init__(self, manager: ArchitectureManager, parent=None):
        """
        Fullscreen-ish dialog to manage architecture models.
        """
        super().__init__(parent)
        self.setWindowTitle("Architecture Manager")
        self.resize(600, 400)
        self.manager = manager
        
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout()
        
        # Left: List View
        self.list_view = QListView()
        self.model = ArchitectureListModel(self.manager)
        self.list_view.setModel(self.model)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_view.setDragEnabled(True)
        self.list_view.setAcceptDrops(True)
        self.list_view.setDropIndicatorShown(True)
        self.list_view.setSpacing(4)
        
        self.list_view.doubleClicked.connect(self.on_edit)
        
        layout.addWidget(self.list_view, stretch=1)
        
        # Right: Buttons
        btn_layout = QVBoxLayout()
        
        self.btn_new = QPushButton("New Model")
        self.btn_new.clicked.connect(self.on_new)
        
        self.btn_edit = QPushButton("Edit / Rename")
        self.btn_edit.clicked.connect(self.on_edit_click)

        self.btn_duplicate = QPushButton("Duplicate")
        self.btn_duplicate.clicked.connect(self.on_duplicate)
        
        self.btn_delete = QPushButton("Delete (Soft)")
        self.btn_delete.clicked.connect(self.on_delete)
        
        self.btn_restore = QPushButton("Restore Deleted")
        self.btn_restore.clicked.connect(self.on_restore)
        
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_duplicate)
        btn_layout.addSpacing(20)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _get_current_index(self):
        return self.list_view.currentIndex()

    def on_new(self):
        dialog = ArchitectureEditDialog(self)
        if dialog.exec():
            name, status = dialog.get_data()
            if name:
                self.manager.create_model(name, status)
                self.model.refresh()

    def on_edit_click(self):
        self.on_edit(self.list_view.currentIndex())

    def on_edit(self, index):
        if not index.isValid():
            return
            
        real_index = self.model.get_real_index(index.row())
        model = self.manager.models[real_index]
        
        dialog = ArchitectureEditDialog(self, name=model.name, status=model.status)
        if dialog.exec():
            name, status = dialog.get_data()
            if name:
                model.name = name
                model.status = status
                self.manager.save_registry()
                self.model.refresh()

    def on_duplicate(self):
        idx = self._get_current_index()
        if not idx.isValid():
            return

        real_index = self.model.get_real_index(idx.row())
        src_model = self.manager.models[real_index]
        
        new_name = f"{src_model.name} Copy"
        self.manager.create_model(new_name, src_model.status, copy_from_index=real_index)
        self.model.refresh()

    def on_delete(self):
        idx = self._get_current_index()
        if not idx.isValid():
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("ASPICE Compliance Warning")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("Deleting an architecture model may impact traceability and ASPICE compliance.")
        msg.setInformativeText("Are you sure you want to delete this model?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            real_index = self.model.get_real_index(idx.row())
            
            # Ensure we are not disrupting the active model state in the main window uncontrollably
            # The manager window allows deletion. The Controller will have to handle "Active Model Deleted" check later,
            # or we handle it here by warning?
            # User requirement 8: "There should be a button that allows the user to restore any deleted model"
            # It's soft delete, so safe.
            
            self.manager.soft_delete_model(real_index)
            self.model.refresh()

    def on_restore(self):
        deleted = [m for m in self.manager.models if m.is_deleted]
        if not deleted:
            QMessageBox.information(self, "Info", "No deleted models to restore.")
            return

        dialog = RestoreModelDialog(deleted, self)
        if dialog.exec():
            selected_row = dialog.get_selected_index()
            # Identify model again safely
            model_to_restore = deleted[selected_row]
            real_index = self.manager.models.index(model_to_restore)
            
            self.manager.restore_model(real_index)
            self.model.refresh()
