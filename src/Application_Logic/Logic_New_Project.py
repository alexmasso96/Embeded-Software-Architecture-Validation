
import logging
from core.elf_parser import ELFParser
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QInputDialog, QMainWindow
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt

import UI
from UI.StyledMessageBox import StyledMessageBox
import os
from .Logic_Loading_Window import LoadingDialog


class ElfImportTask:
    """Embedded-style import task for the New-Project flow.

    It runs on the loading window's worker thread and *sequences + narrates* the
    import steps — open DB (WAL/journal test + schema), load the ELF/JSON, pick the
    parser backend, extract — logging each phase so the window never sits blank and
    the app never *looks* hung. The heavy work stays in ProjectDatabase / ELFParser;
    those log their own sub-phases (the loading window captures the root logger).
    """

    def __init__(self, project_db=None, db_path=None, main_window=None):
        self.project_db = project_db
        self.db_path = db_path
        self.main_window = main_window
        self.log = logging.getLogger("ELF Import")

    def _is_test_mode(self) -> bool:
        return bool(self.main_window and getattr(self.main_window, "test_mode", False))

    def prepare_db(self):
        """Open the project DB on the worker thread (WAL/journal test + schema)."""
        if self.project_db is not None and not self.project_db.is_open and self.db_path:
            self.log.info("Preparing project database…")
            self.project_db.open(self.db_path)   # logs the WAL test + journal mode + schema
            self.log.info(f"Database ready (journal mode: "
                          f"{getattr(self.project_db, 'journal_mode', '?')}).")

    def prepare_empty(self):
        """Worker task for 'Start Empty' — just open the DB."""
        self.prepare_db()
        return True

    def import_elf(self, file_path):
        self.prepare_db()
        parser = ELFParser()
        if self._is_test_mode():
            parser.test_mode = True
        self.log.info("Loading ELF file…")
        parser.load_elf(file_path)
        backend = ("native Rust parser" if parser.parser_backend == "rust_elf_parser"
                   else "Python (pyelftools) parser")
        self.log.info(f"Using the {backend}.")
        if self.project_db and self.project_db.is_open:
            self.log.info("Extracting symbols & debug info — large binaries can take a while…")
            parser.extract_all_streaming_to_db(self.project_db)
        else:
            parser.extract_all()
        self.log.info("ELF import complete.")
        self._build_initial_code_map(parser)
        return parser

    def _build_initial_code_map(self, parser):
        """#1b: build the initial DWARF/Capstone code map *here on the worker thread*
        so it lives under the SAME loading window as the import — instead of running
        synchronously in populate_from_parser on the main thread (the 3–4 s beachball
        in the gap between the import window closing and the code-map appearing).

        The build is model-agnostic; populate_from_parser only has to save the result
        to the active model (a cheap write). Failures are non-fatal — populate_from_parser
        falls back to an inline build if no pre-built map is attached."""
        if not (parser and getattr(parser, "_db", None)
                and getattr(parser, "_active_elf_hash", None)):
            return
        try:
            self.log.info("Building initial code map (call graph & symbol join)…")
            from Application_Logic.Logic_Code_Map import build_code_map
            parser._initial_code_map = build_code_map(parser, None, source_root="")
            self.log.info("Initial code map ready.")
        except Exception as e:  # noqa: BLE001 — non-fatal, populate_from_parser retries
            self.log.warning(f"Initial code map build skipped: {e}")

    def import_json(self, file_path):
        self.prepare_db()
        parser = ELFParser()
        if self._is_test_mode():
            parser.test_mode = True
        self.log.info("Loading JSON symbol cache…")
        if not parser.load_cache(file_path):
            raise ValueError("Failed to load JSON cache file.")
        if self.project_db and self.project_db.is_open:
            self.log.info("Writing cached symbols to the database…")
            parser.flush_to_db(self.project_db)
            # Silently copy the JSON cache into the project's .elf_caches folder.
            try:
                cache_dir = self.project_db.db_path + ".elf_caches"
                os.makedirs(cache_dir, exist_ok=True)
                dest_file = os.path.join(cache_dir, f"elf_{parser.md5_hash}.json")
                if not os.path.exists(dest_file):
                    import shutil
                    shutil.copy2(file_path, dest_file)
            except Exception as e:  # noqa: BLE001
                self.log.warning(f"Failed to copy JSON cache silently: {e}")
        self.log.info("JSON import complete.")
        self._build_initial_code_map(parser)
        return parser


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
