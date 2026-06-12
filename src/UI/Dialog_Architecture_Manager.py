from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListView,
                               QPushButton, QLabel, QMessageBox, QAbstractItemView)
from PyQt6.QtCore import Qt
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from UI.list_models import ArchitectureListModel
from .Dialog_Architecture_Edit import ArchitectureEditDialog
from .Dialog_Restore_Model import RestoreModelDialog
from .Dialog_Port_Propagation import PortPropagationDialog
from .StyledMessageBox import StyledMessageBox, DIALOG_STYLESHEET

class ArchitectureManagerDialog(QDialog):
    def __init__(self, manager: ArchitectureManager, parent=None):
        """
        Fullscreen-ish dialog to manage architecture models.
        """
        super().__init__(parent)
        self.setWindowTitle("Architecture Manager")
        self.resize(600, 400)
        self.setStyleSheet(DIALOG_STYLESHEET)
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
        
        old_status = model.status
        dialog = ArchitectureEditDialog(self, name=model.name, status=model.status)
        if dialog.exec():
            name, status = dialog.get_data()
            if name:
                model.name = name
                model.status = status
                self.manager.save_registry()
                # #8.1: cascade an In Work → other-state model change onto its ports.
                self._propagate_state_to_ports(model, old_status, status)
                self.model.refresh()

    def _propagate_state_to_ports(self, model, old_status, new_status):
        """#8.2: cascade a model leaving 'In Work' onto its ports — but let the user
        confirm/select which ports follow via `PortPropagationDialog` instead of doing
        it silently. Only the In Work → other transition opens the dialog; Cancel (or
        no ports / no selection) makes no changes."""
        if old_status != "In Work" or new_status == "In Work":
            return

        # Load the rows so the dialog can scan ports, then build the column list
        # (name, type) from the active schema, falling back to row keys when no
        # controller is reachable (e.g. the dialog built without the main window).
        if model.data_cache is None:
            self.manager._load_model_data(model)
        rows = model.data_cache.get("rows", []) if model.data_cache else []
        columns = self._resolve_columns(rows)

        dialog = PortPropagationDialog(columns, rows, new_status, self)
        if not dialog.has_ports():
            return  # nothing currently In Work → nothing to propagate
        if not dialog.exec():
            return  # Cancel → leave every port untouched
        selected = dialog.get_selected_ports()
        if not selected:
            return
        self.manager.propagate_status_to_ports(
            model, old_status, new_status,
            port_state_columns=(dialog.get_port_state_column(),),
            selected_ports=set(selected),
            port_name_column=dialog.get_port_name_column())

    def _resolve_columns(self, rows):
        """(name, type) pairs for the active table columns. Prefers the live schema
        from the table controller; otherwise infers from the row keys so the dialog
        still works (Port State guessed by a 'state' name match)."""
        parent = self.parent()
        ctrl = getattr(parent, "arch_controller", None) if parent is not None else None
        active_config = getattr(ctrl, "active_config", None) if ctrl is not None else None
        if active_config:
            return [(c[0], c[1]) for c in active_config if len(c) > 1]
        keys = list(rows[0].keys()) if rows else []
        return [(k, "PortStateColumn" if "state" in k.lower() else "PortSearchColumn")
                for k in keys]

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

        # StyledMessageBox.warning() returns the clicked button (result_button).
        # The old `QMessageBox(self) ... if msg.exec() == StandardButton.Yes` was
        # broken: QMessageBox is aliased to StyledMessageBox, whose exec() returns
        # QDialog.Accepted(1)/Rejected(0) — never the button enum — so the delete
        # branch never ran (and a stray default "OK" button appeared).
        reply = StyledMessageBox.warning(
            self, "ASPICE Compliance Warning",
            "Deleting an architecture model may impact traceability and ASPICE compliance.\n\n"
            "Are you sure you want to delete this model?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            real_index = self.model.get_real_index(idx.row())
            was_active = (real_index == self.manager.active_model_index)
            self.manager.soft_delete_model(real_index)
            if was_active:
                for i, m in enumerate(self.manager.models):
                    if not m.is_deleted:
                        self.manager.active_model_index = i
                        break
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
