from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QComboBox, QCheckBox, QHeaderView, QListWidget, QDialogButtonBox
)
from PyQt6.QtCore import Qt
import os

class ImportModeDialog(QDialog):
    def __init__(self, file_name, sheet_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Software Architecture")
        self.resize(450, 350)
        self.file_name = file_name
        self.sheet_names = sheet_names
        self.selected_mode = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # File info
        lbl_file = QLabel(f"<b>File:</b> {os.path.basename(self.file_name)}")
        layout.addWidget(lbl_file)
        
        layout.addWidget(QLabel("<b>Sheets found:</b>"))
        self.list_sheets = QListWidget()
        self.list_sheets.addItems(self.sheet_names)
        self.list_sheets.setEnabled(False) # Just to display them read-only
        layout.addWidget(self.list_sheets)
        
        layout.addWidget(QLabel("Select how you want to import the sheets:"))
        
        btn_layout = QHBoxLayout()
        self.btn_auto = QPushButton("Automated Import")
        self.btn_auto.clicked.connect(self.on_auto)
        
        self.btn_manual = QPushButton("Manual Import")
        self.btn_manual.clicked.connect(self.on_manual)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        # Style buttons
        self.btn_auto.setStyleSheet("padding: 8px; font-weight: bold;")
        self.btn_manual.setStyleSheet("padding: 8px; font-weight: bold;")
        self.btn_cancel.setStyleSheet("padding: 8px;")
        
        btn_layout.addWidget(self.btn_auto)
        btn_layout.addWidget(self.btn_manual)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def on_auto(self):
        self.selected_mode = "automated"
        self.accept()

    def on_manual(self):
        self.selected_mode = "manual"
        self.accept()


class ManualImportDialog(QDialog):
    def __init__(self, sheet_names, existing_models, parent=None):
        """
        sheet_names: list of strings
        existing_models: list of strings (existing model names)
        """
        super().__init__(parent)
        self.setWindowTitle("Manual Import Configuration")
        self.resize(600, 400)
        self.sheet_names = sheet_names
        self.existing_models = existing_models
        self.mappings = {} # {sheet_name: (import_bool, target_model)}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Configure sheet mapping to Architecture Models:"))
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Import", "Excel Sheet Name", "Target Model"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        self.table.setRowCount(len(self.sheet_names))
        
        self.combos = {}
        self.checkboxes = {}
        
        # Populate table
        for idx, sheet in enumerate(self.sheet_names):
            # Checkbox
            chk = QCheckBox()
            chk.setChecked(True)
            chk_widget = QHBoxLayout()
            chk_widget.addWidget(chk)
            chk_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_widget.setContentsMargins(0, 0, 0, 0)
            cell_widget = QtWidgets = QDialog().parent() # Just a dummy QWidget
            from PyQt6.QtWidgets import QWidget
            cell_widget = QWidget()
            cell_widget.setLayout(chk_widget)
            self.table.setCellWidget(idx, 0, cell_widget)
            self.checkboxes[sheet] = chk
            
            # Sheet Name
            sheet_item = QTableWidgetItem(sheet)
            sheet_item.setFlags(sheet_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 1, sheet_item)
            
            # Target Model Combo
            combo = QComboBox()
            combo.addItems(self.existing_models)
            combo.addItem("<Create New Model>")
            
            # Pre-select matching model by exact name or default to "<Create New Model>"
            if sheet in self.existing_models:
                combo.setCurrentText(sheet)
            else:
                combo.setCurrentText("<Create New Model>")
                
            self.table.setCellWidget(idx, 2, combo)
            self.combos[sheet] = combo
            
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        btn_confirm = QPushButton("Next")
        btn_confirm.clicked.connect(self.on_next)
        btn_confirm.setStyleSheet("padding: 8px; font-weight: bold;")
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet("padding: 8px;")
        
        btn_layout.addWidget(btn_confirm)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def on_next(self):
        # Gather mappings
        self.mappings = {}
        for sheet in self.sheet_names:
            is_checked = self.checkboxes[sheet].isChecked()
            target_model = self.combos[sheet].currentText()
            self.mappings[sheet] = (is_checked, target_model)
        self.accept()


class FuzzyMatchPromptDialog(QDialog):
    def __init__(self, sheet_name, candidates, parent=None):
        """
        candidates: list of tuples (model_name, score)
        """
        super().__init__(parent)
        self.setWindowTitle("Fuzzy Match Suggestion")
        self.resize(450, 300)
        self.sheet_name = sheet_name
        self.candidates = candidates
        self.selected_model = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        label = QLabel(f"The sheet name '<b>{self.sheet_name}</b>' partially matches existing models:")
        layout.addWidget(label)
        layout.addWidget(QLabel("Please select a target model or choose to create a new one:"))
        
        self.list_widget = QListWidget()
        for model_name, score in self.candidates:
            self.list_widget.addItem(f"{model_name} ({score:.0f}% similarity)")
        self.list_widget.addItem("<Create New Model>")
        
        # Select first item by default
        self.list_widget.setCurrentRow(0)
        
        layout.addWidget(self.list_widget)
        
        # Double click to accept
        self.list_widget.itemDoubleClicked.connect(self.accept)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)

    def accept(self):
        row = self.list_widget.currentRow()
        if row == -1:
            return
        
        if row < len(self.candidates):
            self.selected_model = self.candidates[row][0]
        else:
            self.selected_model = "<Create New Model>"
        super().accept()


class ImportConfirmationDialog(QDialog):
    def __init__(self, mappings, parent=None):
        """
        mappings: dict {sheet_name: target_model} (only containing selected ones)
        """
        super().__init__(parent)
        self.setWindowTitle("Confirm Import Mappings")
        self.resize(500, 350)
        self.mappings = mappings
        self.selected_action = None # "confirm", "advanced", "cancel"
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("<b>Summary of sheets to be imported:</b>"))
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Excel Sheet Name", "Target Architecture Model"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        
        self.table.setRowCount(len(self.mappings))
        
        for idx, (sheet, target) in enumerate(self.mappings.items()):
            sheet_item = QTableWidgetItem(sheet)
            sheet_item.setFlags(sheet_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 0, sheet_item)
            
            target_item = QTableWidgetItem(target)
            target_item.setFlags(target_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 1, target_item)
            
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        self.btn_confirm = QPushButton("Confirm")
        self.btn_confirm.clicked.connect(self.on_confirm)
        self.btn_confirm.setStyleSheet("padding: 8px; font-weight: bold; background-color: #2e8b57; color: white;")
        
        self.btn_advanced = QPushButton("Advanced Configuration")
        self.btn_advanced.clicked.connect(self.on_advanced)
        self.btn_advanced.setStyleSheet("padding: 8px;")
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setStyleSheet("padding: 8px;")
        
        btn_layout.addWidget(self.btn_confirm)
        btn_layout.addWidget(self.btn_advanced)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def on_confirm(self):
        self.selected_action = "confirm"
        self.accept()

    def on_advanced(self):
        self.selected_action = "advanced"
        self.accept()
