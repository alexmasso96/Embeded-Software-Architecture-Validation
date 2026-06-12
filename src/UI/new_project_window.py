"""
New-Project chooser window (Qt) — moved out of Application_Logic/
Logic_New_Project.py in Phase 0 of the pywebview migration. The import
sequencing itself (ElfImportTask) stays there as pure logic; this window is
widget glue and retires with the PyQt UI in Phase 4.
"""
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QMainWindow
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

import UI
from UI.StyledMessageBox import StyledMessageBox
from UI.loading_window import LoadingDialog
from Application_Logic.Logic_New_Project import ElfImportTask


class NewProjectController(QMainWindow):
    def __init__(self, main_window=None, project_db=None, db_path=None):
        super().__init__()
        self.main_window = main_window
        self.project_db = project_db   # ProjectDatabase — opened inside the worker
        self.db_path = db_path          # where to open it (WAL test runs off-thread)
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

    def _task(self):
        return ElfImportTask(self.project_db, self.db_path, self.main_window)

    def _open_db_task(self):
        """Worker task for the 'Start Empty' path: just open the DB (WAL test)."""
        return self._task().prepare_empty()

    def _parse_logic(self, mode, file_path):
        """Runs on the background thread — delegates to the ElfImportTask which
        sequences + narrates each step to the loading window."""
        task = self._task()
        if mode == 'ELF':
            return task.import_elf(file_path)
        return task.import_json(file_path)

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
        # Open the DB (WAL test + schema) off the UI thread, with feedback, even for
        # an empty project — that step is what freezes on slow/EDR storage.
        if self.project_db is not None and not self.project_db.is_open:
            loader = LoadingDialog(self)
            if not loader.run_task(self._open_db_task):
                self.show_message("Error", f"Failed: {loader.error_msg}", QMessageBox.Icon.Critical)
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
