import logging

from core.elf_parser import ELFParser
from PyQt6.QtWidgets import QDialog, QMainWindow, QApplication, QFileDialog, QMessageBox
from PyQt6.QtCore import QThread, pyqtSignal
import UI
import os
import sys
from .Logging_Handler import Signaller, QtLoggingHandler
from .Logic_Loading_Window import LoadingDialog

class ParsingWorker (QThread):
    """
    Worker thread to handle heavy ELF/JSON parsing without freezing the UI.
    """
    finished = pyqtSignal(object) # Sends the parser back
    error = pyqtSignal (str)

    def __init__(self, mode, file_path):
        super().__init__()
        self.mode = mode # 'ELF' or 'JSON'
        self.file_path = file_path

    def run(self):
        try:
            parser = ELFParser()
            if self.mode == 'ELF':
                parser.load_elf(self.file_path)
            else:
                parser. load_cache(self.file_path)

            parser.extract_all()
            self.finished.emit(parser)

        except Exception as e:
            self.error.emit(str(e))


class NewProjectController (QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = UI.win_new_project_dialogue.Ui_win_new_project_dialogue()
        self.ui.setupUi(self)

        #Connect Internal Dialogue
        self.ui.btn_help_new_project.clicked.connect(self.HelpNewProject)
        self.ui.btn_new_elf.clicked.connect(self.open_elf_handler)
        self.ui.btn_Load_json.clicked.connect(self.open_json_handler)

        self.parser = None
        self.loading_win = None
        self.log_handler = None

    def start_parsing_task(self, mode, file_path):
        """
        Sets up the UI redirection and starts the background worker.
        """
        self.loading_win =LoadingDialog(self)
        signaller = Signaller()
        signaller.text_received.connect(self.loading_win.append_log)

        #redirect Logging and Stdout
        self.log_handler = QtLoggingHandler(signaller)
        self.log_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        self.old_stdout = sys.stdout
        sys.stdout = signaller

        #setup Worker
        self.worker = ParsingWorker(mode, file_path)
        self.worker.finished.connect(self.on_parsing_finished)
        self.worker.error.connect(self.on_parsing_error)

        self.loading_win.show()
        self.worker.start()

    def cleanup_ui(self):
        """
        Restores stdout and removes logging handler.
        """
        if hasattr(self, 'old_stdout') :
            sys.stdout = self.old_stdout
        if self.log_handler:
            logging.getLogger().removeHandler(self.log_handler)
        if self.loading_win:
            self.loading_win.close()

    def on_parsing_finished(self, parser):
        self.parser = parser
        self.cleanup_ui()

        stats = self.parser.get_statistics()
        QMessageBox.information(self, "Success",
                                f"Successfully loaded {os.path.basename(self.parser.elf_path)}\n"
                                f"Functions: {stats['functions']}")
        self.close()

    def on_parsing_error(self, error_message):
        self.cleanup_ui()
        QMessageBox.critical(self, "Error", f"Parsing Error: \n{error_message}")

    def open_elf_handler (self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open ELF File", "", "ELF Files (*.elf);; All Files (*)")
        if file_path:
            self.start_parsing_task('ELF', file_path)

    def open_json_handler (self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open JSON File", "", "JSON Files (*.json) ;; All Files (*)")
        if file_path:
            self.start_parsing_task('JSON', file_path)

    def HelpNewProject(self):
        self.help_window = QMainWindow(self)
        self.help_ui = UI.win_help_new_project.Ui_win_help_new_project()
        self.help_ui.setupUi(self.help_window)

        #Connect Close Button
        self.help_ui.btn_close_window.clicked.connect(self.help_window.close)
        self.help_window.show()

    def exec(self):
        """
        Shims the QDialog.exec() behavior for QMainWindow
        """
        self.show()
        import PyQt6.QtCore
        loop = PyQt6.QtCore.QEventLoop()
        self.destroyed.connect(loop.quit)
        loop.exec()
        return self.parser is not None