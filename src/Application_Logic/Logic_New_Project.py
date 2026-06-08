
from core.elf_parser import ELFParser
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QInputDialog, QMainWindow
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

import UI
from UI.StyledMessageBox import StyledMessageBox
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
        self._closing = False   # BUG-02 guard: prevent re-entrant / late close()

    def _safe_close(self):
        """Close exactly once. Disconnect the action buttons first so a queued
        click can't re-enter a handler after the C++ object is being torn down
        (WA_DeleteOnClose), and swallow the 'wrapped C/C++ object deleted'
        RuntimeError if the object is already gone."""
        if self._closing:
            return
        self._closing = True
        for btn in (getattr(self.ui, "btn_start_empty", None),
                    getattr(self.ui, "btn_new_elf", None),
                    getattr(self.ui, "btn_Load_json", None)):
            try:
                btn.clicked.disconnect()
            except Exception:
                pass
        # Inc-03: end the modal exec() loop explicitly so a successful ELF/JSON
        # load (or Start Empty) returns control to main.py, which then enters the
        # table view — instead of leaving the New-Project chooser on screen.
        loop = getattr(self, "_loop", None)
        if loop is not None:
            loop.quit()
        try:
            self.close()
        except RuntimeError:
            pass

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
                # Silently copy JSON cache file to project's .elf_caches folder
                try:
                    cache_dir = self.project_db.db_path + ".elf_caches"
                    os.makedirs(cache_dir, exist_ok=True)
                    dest_file = os.path.join(cache_dir, f"elf_{parser.md5_hash}.json")
                    if not os.path.exists(dest_file):
                        import shutil
                        shutil.copy2(file_path, dest_file)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to copy JSON cache silently: {e}")

        return parser

    def show_message(self, title, text, icon=QMessageBox.Icon.Information):
        if self.main_window and getattr(self.main_window, 'test_mode', False):
            return
        msg_box = StyledMessageBox(self, title, text, icon, QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def open_elf_handler(self):
        if self._closing:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open ELF File", "",
            "ELF Files (*.elf);; All Files (*)",
            options=QFileDialog.Option(0)
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
                # Inc-03: go straight to the workspace/table after a successful
                # load — no blocking success popup. main.py reports the result in
                # the status bar; returning to the table IS the confirmation.
                self._safe_close()
            else:
                self.show_message("Error", f"Failed: {loader.error_msg}", QMessageBox.Icon.Critical)

    def open_json_handler(self):
        if self._closing:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open JSON Cache File", "",
            "JSON Files (*.json) ;; All Files (*)",
            options=QFileDialog.Option(0)
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
                # Inc-03: proceed straight to the workspace (see open_elf_handler).
                self._safe_close()
            else:
                self.show_message("Error", f"Failed: {loader.error_msg}", QMessageBox.Icon.Critical)

    def start_empty_handler(self):
        if self._closing:
            return
        self._start_empty = True
        self._safe_close()

    def help_new_project(self):
        self.help_window = QMainWindow(self)
        self.help_ui = UI.win_help_new_project.Ui_win_help_new_project()
        self.help_ui.setupUi(self.help_window)
        self.help_ui.btn_close_window.clicked.connect(self.help_window.close)
        self.help_window.show()

    def exec(self):
        """Shims QDialog.exec() behavior for QMainWindow."""
        self.show()
        self._loop = QtCore.QEventLoop()
        self.destroyed.connect(self._loop.quit)
        self._loop.exec()
        return self.parser is not None or self._start_empty
