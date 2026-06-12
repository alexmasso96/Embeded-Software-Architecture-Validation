"""
New-Project import sequencing (pure logic).

Phase 0 (pywebview migration): Qt-free. The New-Project chooser window lives
in UI/new_project_window.py and runs these tasks on its loading window's
worker thread; after Phase 1 the FastAPI `project` router runs them as jobs.
"""
import logging
import os

from core.elf_parser import ELFParser


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
