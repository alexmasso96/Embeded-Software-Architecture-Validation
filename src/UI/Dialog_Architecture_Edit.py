from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QDialogButtonBox

class ArchitectureEditDialog(QDialog):
    def __init__(self, parent=None, name="", status="In Work"):
        """
        Dialog to Create or Edit an Architecture Model.
        """
        super().__init__(parent)
        self.setWindowTitle("Architecture Model")
        self.resize(300, 150)
        
        self.name = name
        self.status = status
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Name
        lbl_name = QLabel("Model Name:")
        self.txt_name = QLineEdit(self.name)
        layout.addWidget(lbl_name)
        layout.addWidget(self.txt_name)
        
        # Status
        lbl_status = QLabel("Status:")
        self.cmb_status = QComboBox()
        self.cmb_status.addItems(["In Work", "Released", "Retired"])
        self.cmb_status.setCurrentText(self.status)
        layout.addWidget(lbl_status)
        layout.addWidget(self.cmb_status)
        
        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
        self.setLayout(layout)
        
    def get_data(self):
        return self.txt_name.text(), self.cmb_status.currentText()
