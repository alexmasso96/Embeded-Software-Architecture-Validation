from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import UI

class LoadingDialog (QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        #instantiate the generated UI
        self.ui = UI.win_simple_loading.Ui_Standard_Loading()
        self.ui.setupUi(self)
        self.setup_loading_icon()

        # Configure the text edit for logging
        self.ui.plainTextEdit.setReadOnly(True)


        #Ensre it uses a Monospace font for the "console" look
        font = self.ui.plainTextEdit.font()
        font.setFamily("Courier New")
        self.ui.plainTextEdit.setFont(font)

    def setup_loading_icon(self):
        """
        Loads the standard Qt system icon into lbl_icon_loading
        """
        icon = QIcon.fromTheme(QIcon.ThemeIcon.AppointmentSoon)

        if not icon.isNull():
            # Convert the icon to a pixmap and scale it to the label size (41x41)
            pixmap = icon.pixmap(self.ui.lbl_icon_loading.size())
            self.ui.lbl_icon_loading.setPixmap(pixmap)
            self.ui.lbl_icon_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            # Fallback to a generic information icon if the theme is not found
            icon = QIcon.fromTheme(QIcon.ThemeIcon.Information)
            pixmap = icon.pixmap(self.ui.lbl_icon_loading.size())
            self.ui.lbl_icon_loading.setPixmap(pixmap)

    def append_log(self, text):
        """
        Slot to receive the text from the Signaller and update the UI
        """

        self.ui.plainTextEdit.appendPlainText(text)
        #Scroll to the buttom automatically
        self.ui.plainTextEdit.ensureCursorVisible()
