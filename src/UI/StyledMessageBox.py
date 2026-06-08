from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt6.QtCore import Qt

class StyledMessageBox(QDialog):
    # Expose the same enums for compatibility
    Icon = QMessageBox.Icon
    StandardButton = QMessageBox.StandardButton
    ButtonRole = QMessageBox.ButtonRole

    def __init__(self, parent=None, title="", text="", icon_type=QMessageBox.Icon.NoIcon, buttons=QMessageBox.StandardButton.Ok):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Application-modal (NOT window-modal) so macOS shows a normal, properly
        # sized centered dialog instead of a collapsed sheet attached to the
        # parent's title bar (KI-07: the previous `& ~Qt.Sheet` flag hack still
        # rendered as an empty sliver for the 3-button question() prompt).
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setMinimumWidth(380)
        self.setMaximumWidth(600)
        
        # Apply style sheet to self explicitly to guarantee visual theme inheritance
        self.setStyleSheet("""
            QDialog {
                background-color: #242424;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-size: 13px;
            }
        """)

        # Outer Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Message content layout (horizontal to show icon next to text)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        
        # Icon Label
        self.icon_label = QLabel(self)
        content_layout.addWidget(self.icon_label, 0)
        
        # Text Area layout (vertical)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(8)
        
        # Text Label
        self.lbl_text = QLabel(self)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_layout.addWidget(self.lbl_text)
        
        # Informative Text Label
        self.lbl_informative = QLabel(self)
        self.lbl_informative.setWordWrap(True)
        self.lbl_informative.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_informative.setStyleSheet("color: #bbbbbb; font-size: 12px;")
        self.lbl_informative.hide()
        text_layout.addWidget(self.lbl_informative)
        
        content_layout.addLayout(text_layout, 1)
        layout.addLayout(content_layout)
        
        # Buttons layout
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addStretch()
        layout.addLayout(self.buttons_layout)
        
        self.buttons = {}
        self.result_button = QMessageBox.StandardButton.NoButton
        
        # Apply initial settings if provided
        if text:
            self.setText(text)
        if icon_type != QMessageBox.Icon.NoIcon:
            self.setIcon(icon_type)
        if buttons != QMessageBox.StandardButton.Ok:
            self.setStandardButtons(buttons)
        else:
            self.setStandardButtons(QMessageBox.StandardButton.Ok)

        # Ensure the window opens at its content size (macOS can otherwise open a
        # freshly-flagged dialog collapsed — KI-07).
        self.adjustSize()
        self.setMinimumHeight(self.sizeHint().height())

    def setText(self, text):
        self.lbl_text.setText(text)

    def setInformativeText(self, info_text):
        self.lbl_informative.setText(info_text)
        if info_text:
            self.lbl_informative.show()
        else:
            self.lbl_informative.hide()

    def setIcon(self, icon_type):
        pixmap = None
        style = self.style()
        if icon_type == QMessageBox.Icon.Information:
            pixmap = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation).pixmap(32, 32)
        elif icon_type == QMessageBox.Icon.Warning:
            pixmap = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(32, 32)
        elif icon_type == QMessageBox.Icon.Critical:
            pixmap = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical).pixmap(32, 32)
        elif icon_type == QMessageBox.Icon.Question:
            pixmap = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxQuestion).pixmap(32, 32)
            
        if pixmap and not pixmap.isNull():
            self.icon_label.setPixmap(pixmap)
            self.icon_label.show()
        else:
            self.icon_label.hide()

    def setStandardButtons(self, buttons):
        # Clear existing buttons (keeping the spacer at index 0)
        while self.buttons_layout.count() > 1:
            item = self.buttons_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self.buttons.clear()
        
        # Re-add buttons from the bitmask
        if buttons & QMessageBox.StandardButton.Cancel:
            self.add_button("Cancel", QMessageBox.StandardButton.Cancel)
        if buttons & QMessageBox.StandardButton.No:
            self.add_button("No", QMessageBox.StandardButton.No)
        if buttons & QMessageBox.StandardButton.Yes:
            self.add_button("Yes", QMessageBox.StandardButton.Yes, is_default=True)
        if buttons & QMessageBox.StandardButton.Ok:
            self.add_button("OK", QMessageBox.StandardButton.Ok, is_default=True)

    def setDefaultButton(self, button_role):
        # Update stylesheet of the button to be highlighted blue
        for role, btn in self.buttons.items():
            if role == button_role:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2a82da;
                        color: white;
                        border: 1px solid #2a82da;
                        border-radius: 6px;
                        font-size: 13px;
                        font-weight: bold;
                        padding: 6px 16px;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #4a9eef;
                        border: 1px solid #4a9eef;
                    }
                    QPushButton:pressed {
                        background-color: #1a62ba;
                    }
                """)
                btn.setDefault(True)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #353535;
                        color: white;
                        border: 1px solid #444444;
                        border-radius: 6px;
                        font-size: 13px;
                        font-weight: bold;
                        padding: 6px 16px;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #444444;
                    }
                    QPushButton:pressed {
                        background-color: #222222;
                    }
                """)
                btn.setDefault(False)

    def add_button(self, text, role, is_default=False):
        btn = QPushButton(text, self)
        btn.setFixedHeight(32)
        if is_default:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a82da;
                    color: white;
                    border: 1px solid #2a82da;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 6px 16px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #4a9eef;
                    border: 1px solid #4a9eef;
                }
                QPushButton:pressed {
                    background-color: #1a62ba;
                }
            """)
            btn.setDefault(True)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #353535;
                    color: white;
                    border: 1px solid #444444;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 6px 16px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #444444;
                }
                QPushButton:pressed {
                    background-color: #222222;
                }
            """)
        
        btn.clicked.connect(lambda: self.on_button_clicked(role))
        self.buttons_layout.addWidget(btn)
        self.buttons[role] = btn

    def on_button_clicked(self, role):
        self.result_button = role
        if role in [QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Yes]:
            self.accept()
        elif role in [QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.No]:
            self.reject()
        else:
            self.done(role.value)

    @classmethod
    def information(cls, parent, title, text, buttons=QMessageBox.StandardButton.Ok):
        dialog = cls(parent, title, text, QMessageBox.Icon.Information, buttons)
        dialog.exec()
        return dialog.result_button

    @classmethod
    def warning(cls, parent, title, text, buttons=QMessageBox.StandardButton.Ok):
        dialog = cls(parent, title, text, QMessageBox.Icon.Warning, buttons)
        dialog.exec()
        return dialog.result_button

    @classmethod
    def critical(cls, parent, title, text, buttons=QMessageBox.StandardButton.Ok):
        dialog = cls(parent, title, text, QMessageBox.Icon.Critical, buttons)
        dialog.exec()
        return dialog.result_button

    @classmethod
    def question(cls, parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No):
        dialog = cls(parent, title, text, QMessageBox.Icon.Question, buttons)
        dialog.exec()
        return dialog.result_button
