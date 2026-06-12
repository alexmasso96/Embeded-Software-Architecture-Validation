"""
Master password dialogs — moved out of Application_Logic/Logic_Security.py
in Phase 0 of the pywebview migration (logic must not create widgets).
SecurityManager (hashing/verification) stays in Logic_Security.
"""

from PyQt6 import QtWidgets


class MasterPasswordSetupDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Master Password")
        self.resize(400, 220)

        # Design aesthetics: elegant dark theme integration
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QtWidgets.QLabel("<b>Configure Project Master Password</b>", self)
        title_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(title_label)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(10)

        self.txt_password = QtWidgets.QLineEdit(self)
        self.txt_password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Enter master password")

        self.txt_confirm = QtWidgets.QLineEdit(self)
        self.txt_confirm.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.txt_confirm.setPlaceholderText("Confirm master password")

        form_layout.addRow("Password:", self.txt_password)
        form_layout.addRow("Confirm:", self.txt_confirm)

        layout.addLayout(form_layout)

        # Validation error message area
        self.lbl_error = QtWidgets.QLabel("", self)
        self.lbl_error.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        layout.addWidget(self.lbl_error)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.btn_ok = QtWidgets.QPushButton("Set Password", self)
        self.btn_ok.setStyleSheet("background-color: #2a82da; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_ok.clicked.connect(self.validate_and_accept)
        # Submit on Enter from either field, and make "Set Password" the default.
        self.btn_ok.setDefault(True)
        self.btn_ok.setAutoDefault(True)
        self.txt_password.returnPressed.connect(self.validate_and_accept)
        self.txt_confirm.returnPressed.connect(self.validate_and_accept)

        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_ok)

        layout.addLayout(button_layout)

    def validate_and_accept(self):
        password = self.txt_password.text()
        confirm = self.txt_confirm.text()

        if not password:
            self.lbl_error.setText("Password cannot be empty.")
            return

        if len(password) < 6:
            self.lbl_error.setText("Password must be at least 6 characters.")
            return

        if password != confirm:
            self.lbl_error.setText("Passwords do not match.")
            return

        self.accept()

    def get_password(self) -> str:
        return self.txt_password.text()


class MasterPasswordPromptDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, prompt_text="Enter Master Password:"):
        super().__init__(parent)
        self.setWindowTitle("Authentication Required")
        self.resize(360, 160)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QtWidgets.QLabel(f"<b>{prompt_text}</b>", self)
        title_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(title_label)

        self.txt_password = QtWidgets.QLineEdit(self)
        self.txt_password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Enter password")
        layout.addWidget(self.txt_password)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.btn_ok = QtWidgets.QPushButton("Verify", self)
        self.btn_ok.setStyleSheet("background-color: #2a82da; color: white; font-weight: bold; padding: 6px 12px;")
        self.btn_ok.clicked.connect(self.accept)
        # Enter in the password field submits; "Verify" is the default button.
        self.btn_ok.setDefault(True)
        self.btn_ok.setAutoDefault(True)
        self.txt_password.returnPressed.connect(self.accept)

        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_ok)

        layout.addLayout(button_layout)

    def get_password(self) -> str:
        return self.txt_password.text()
