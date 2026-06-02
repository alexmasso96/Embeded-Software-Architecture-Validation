
from core.elf_parser import ELFParser
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QInputDialog, QMainWindow
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

import UI
import os
from .Logic_Loading_Window import LoadingDialog


class NewProjectController(QMainWindow):
    def __init__(self, main_window=None, project_db=None):
        super().__init__()
        self.main_window = main_window
        self.project_db = project_db   # ProjectDatabase opened before dialog shown
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.ui = UI.win_new_project_dialogue.Ui_win_new_project_dialogue()
        self.ui.setupUi(self)

        self.ui.btn_start_empty.clicked.connect(self.start_empty_handler)
        self.ui.btn_help_new_project.clicked.connect(self.help_new_project)
        self.ui.btn_new_elf.clicked.connect(self.open_elf_handler)
        self.ui.btn_Load_json.clicked.connect(self.open_json_handler)

        self.parser = None
        self.release_name = None
        self._start_empty = False

    def _parse_logic(self, mode, file_path):
        """Runs on the background thread."""
        parser = ELFParser()
        if self.main_window and getattr(self.main_window, 'test_mode', False):
            parser.test_mode = True

        if mode == 'ELF':
            parser.load_elf(file_path)
            if self.project_db and self.project_db.is_open:
                # Stream directly to DB — never accumulates full ELF in RAM
                parser.extract_all_streaming_to_db(self.project_db)
            else:
                # Fallback: in-memory (flushed at save time)
                parser.extract_all()
        else:
            # JSON cache: fast enough to load into RAM; flush to DB at save time
            success = parser.load_cache(file_path)
            if not success:
                raise ValueError("Failed to load JSON cache file.")
            if self.project_db and self.project_db.is_open:
                parser.flush_to_db(self.project_db)

        return parser

    def open_elf_handler(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open ELF File", "",
            "ELF Files (*.elf);; All Files (*)"
        )
        if file_path:
            release_name, ok = QtWidgets.QInputDialog.getText(
                self, "Release Version",
                "Enter Release Version/Name (e.g. R1.0):"
            )
            if not ok or not release_name.strip():
                return

            loader = LoadingDialog(self)
            if loader.run_task(self._parse_logic, 'ELF', file_path):
                self.parser = loader.result
                self.release_name = release_name
                stats = self.parser.get_statistics()
                QMessageBox.information(
                    self, "Success",
                    f"Successfully parsed ELF: {os.path.basename(file_path)}\n"
                    f"Functions found: {stats['functions']}"
                )
                self.close()
            else:
                QMessageBox.critical(self, "Error", f"Failed: {loader.error_msg}")

    def open_json_handler(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open JSON Cache File", "",
            "JSON Files (*.json) ;; All Files (*)"
        )
        if file_path:
            release_name, ok = QtWidgets.QInputDialog.getText(
                self, "Release Version",
                "Enter Release Version/Name (e.g. R1.0):"
            )
            if not ok or not release_name.strip():
                return

            loader = LoadingDialog(self)
            if loader.run_task(self._parse_logic, 'JSON', file_path):
                self.parser = loader.result
                self.release_name = release_name
                QMessageBox.information(
                    self, "Success",
                    f"Loaded JSON cache: {os.path.basename(file_path)}"
                )
                self.close()
            else:
                QMessageBox.critical(self, "Error", f"Failed: {loader.error_msg}")

    def start_empty_handler(self):
        self._start_empty = True
        self.close()

    def help_new_project(self):
        self.help_window = QMainWindow(self)
        self.help_ui = UI.win_help_new_project.Ui_win_help_new_project()
        self.help_ui.setupUi(self.help_window)
        self.help_ui.btn_close_window.clicked.connect(self.help_window.close)
        self.help_window.show()

    def exec(self):
        """Shims QDialog.exec() behavior for QMainWindow."""
        self.show()
        loop = QtCore.QEventLoop()
        self.destroyed.connect(loop.quit)
        loop.exec()
        return self.parser is not None or self._start_empty
