import sys
import logging
import os
from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import UI
from .Logging_Handler import Signaller, QtLoggingHandler

class TaskWorker (QThread):
    """
    Generic worker to run any task in a background thread.
    """
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, task_fn, *args, **kwargs):
        super().__init__()
        self.task_fn = task_fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.task_fn(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class LoadingDialog (QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        # Instantiate the generated UI
        self.ui = UI.win_simple_loading.Ui_Standard_Loading()
        self.ui.setupUi(self)
        self.setup_loading_icon()

        # Configure the text edit for logging
        self.ui.plainTextEdit.setReadOnly(True)


        # Ensure it uses a Monospace font for the "console" look
        font = self.ui.plainTextEdit.font()
        font.setFamily("Courier New")
        font.setPointSize(10)
        font.setBold(False)
        self.ui.plainTextEdit.setFont(font)

        # Internals for task management
        self.result = None
        self.error_msg = None
        self.log_handler = None
        self.old_stdout = None

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

    def run_task (self, task_fn, *args, **kwargs):
        """
        Executes a task with full log redirection and a background thread.
        """

        # Setup Redirection
        signaller = Signaller()
        signaller.text_received.connect(self.append_log)

        self.log_handler = QtLoggingHandler(signaller)
        self.log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)

        self.old_stdout = sys.stdout
        sys.stdout = signaller

        # Setup Thread
        self.worker = TaskWorker(task_fn, *args, **kwargs)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)

        self.worker.start()

        # Block untill worker is done (returns dialog result)
        return self.exec()

    def _on_finished(self, result):
        self.result = result
        self._cleanup()
        self.accept()

    def _on_error(self, error_msg):
        self.error_msg = error_msg
        self._cleanup()
        self.reject()  # Closes the dialog with QDialog.Rejected

    def _cleanup (self):
        if self.old_stdout:
            sys.stdout = self.old_stdout
        if self.log_handler:
            logging.getLogger().removeHandler(self.log_handler)

    def append_log(self, text):
        """
        Slot to receive the text from the Signaller and update the UI
        """

        self.ui.plainTextEdit.appendPlainText(text)
        #Scroll to the buttom automatically
        self.ui.plainTextEdit.ensureCursorVisible()
