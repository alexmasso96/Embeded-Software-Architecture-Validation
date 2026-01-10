from core.elf_parser import ELFParser
from PyQt6.QtWidgets import QMainWindow, QFileDialog, QMessageBox

import UI
import os
from .Logic_Loading_Window import LoadingDialog

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

    def _parse_logic(self, mode, file_path):
        """
        This function runs on the background thread
        """
        parser = ELFParser()
        if mode == 'ELF':
            parser.load_elf(file_path)
            # Only extract all if we are loading a new elf
            parser.extract_all()
        else:
            # load_cache already populates lists from JSON
            success = parser.load_cache(file_path)
            if not success:
                raise ValueError("Failed to load JSON cache file.")

        return parser

    def open_elf_handler (self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open ELF File", "", "ELF Files (*.elf);; All Files (*)")
        if file_path:
            loader = LoadingDialog(self)
            if loader.run_task(self._parse_logic, 'ELF', file_path):
                self.parser = loader.result
                stats = self.parser.get_statistics()
                QMessageBox.information(self, "Success",
                                        f"Successfully parsed ELF: {os.path.basename(file_path)}\n"
                                        f"Functions found: {stats['functions']}")
                self.close()
            else:
                QMessageBox.critical(self, "Error", f"Failed: {loader.error_msg}")

    def open_json_handler (self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open JSON File", "", "JSON Files (*.json) ;; All Files (*)")
        if file_path:
            loader = LoadingDialog(self)
            if loader.run_task(self._parse_logic, 'JSON', file_path):
                self.parser = loader.result
                QMessageBox.information(self, "Success", f"Loaded JSON database: {os.path.basename(file_path)}")
                self.close()
            else:
                QMessageBox.critical(self, "Error", f" Failed: {loader.error_msg}")

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