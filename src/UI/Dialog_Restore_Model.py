from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QLabel, QHBoxLayout, QMessageBox

class RestoreModelDialog(QDialog):
    def __init__(self, deleted_models, parent=None):
        """
        Dialog to list deleted models and allow restoration.
        deleted_models: List of ArchitectureModel objects that have is_deleted=True
        """
        super().__init__(parent)
        self.setWindowTitle("Restore Deleted Models")
        self.resize(400, 300)
        self.deleted_models = deleted_models
        self.selected_index = -1
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Select a model to restore:"))
        
        self.list_widget = QListWidget()
        for model in self.deleted_models:
            self.list_widget.addItem(f"{model.name} ({model.status})")
            
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_restore = QPushButton("Restore")
        self.btn_restore.clicked.connect(self.on_restore)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_restore)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
    def on_restore(self):
        row = self.list_widget.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Selection Required", "Please select a model to restore.")
            return
            
        self.selected_index = row
        self.accept()
        
    def get_selected_index(self):
        return self.selected_index
