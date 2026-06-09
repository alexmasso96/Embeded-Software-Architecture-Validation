"""
Project Saving
==============
Save / load a .arch SQLite project file.
The "dirty" concept is tracked via a sidecar .dirty flag file.
"""
import os
import logging
import hashlib
import hmac
import json
from PyQt6 import QtWidgets

from .Logic_Database import ProjectDatabase
from core.elf_parser import ELFParser

logger = logging.getLogger(__name__)


class ProjectSaver:
    """
    Handles saving and loading of .arch project files (SQLite databases).
    """

    # ------------------------------------------------------------------
    # Dirty / temp tracking  (sidecar .dirty flag)
    # ------------------------------------------------------------------

    @staticmethod
    def _dirty_path(project_path: str) -> str:
        return project_path + ".dirty"

    @staticmethod
    def has_temp_changes(project_path: str) -> bool:
        if not project_path:
            return False
        return os.path.exists(ProjectSaver._dirty_path(project_path))

    @staticmethod
    def cleanup_temp(project_path: str):
        if not project_path:
            return
        dirty = ProjectSaver._dirty_path(project_path)
        try:
            if os.path.exists(dirty):
                os.remove(dirty)
        except OSError:
            pass

    @staticmethod
    def save_temp(main_window, original_path: str):
        """
        Flush current table data to DB and set the dirty flag.
        Called on every cell change in 'immediate' auto-save mode.
        """
        if not original_path:
            return False, "No project file."
        db = getattr(main_window, 'project_db', None)
        if not db or not db.is_open:
            return False, "No open database."
        try:
            main_window.arch_controller.flush_current_data_to_model()
            # Touch dirty flag
            with open(ProjectSaver._dirty_path(original_path), 'w'):
                pass
            return True, "Changes staged."
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Integrity hash
    # ------------------------------------------------------------------

    # Fallback key used for projects that have no master password configured.
    # Integrity still detects accidental external modification; it just isn't
    # keyed to a user secret in that case.
    _DEFAULT_INTEGRITY_KEY = b"arch-validator-integrity-v1"

    @staticmethod
    def _integrity_key(master_hash) -> bytes:
        if master_hash:
            return str(master_hash).encode("utf-8")
        return ProjectSaver._DEFAULT_INTEGRITY_KEY

    @staticmethod
    def compute_integrity_hmac(db, master_hash) -> str:
        """
        HMAC-SHA256 over the project's canonical logical content, keyed by the
        master-password hash (or a fixed fallback key when none is set).

        This replaces the old whole-file SHA-256. The file-byte approach was
        unstable: SQLite rewrites its own header (change counter, version
        fields), checkpoints the WAL on close, and the app commits to the DB
        outside the save path (ui_state, history) — so the raw bytes changed on
        nearly every reopen and triggered spurious master-password prompts.
        Hashing logical content instead is stable across reopen and SQLite
        versions while remaining tamper-evident.
        """
        digest = db.compute_content_digest()
        return hmac.new(
            ProjectSaver._integrity_key(master_hash),
            digest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ------------------------------------------------------------------
    # ELF cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _elf_cache_dir(project_path: str) -> str:
        return project_path + ".elf_caches"

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    @staticmethod
    def save_project(main_window, path: str, is_temp: bool = False, progress: bool = False):
        """Save the project.

        Split into two phases so the slow, EDR-amplified file I/O never freezes
        the UI:
          * Phase 1 (this method, MAIN thread): everything that reads Qt widgets —
            the Save-As DB handoff, flushing the live table, and collecting the
            test-case-design text. Widgets must only be touched on the GUI thread.
          * Phase 2 (`_persist`, off-thread when progress=True): all DB writes,
            ELF-cache export, integrity HMAC and WAL checkpoint. These touch only
            the DB / managers / files, never widgets.

        progress=True runs Phase 2 in a worker behind a responsive modal
        (LoadingDialog.run_task — the safe exec() form, see the modal pitfall
        memory) and still returns (success, msg) synchronously, so every existing
        caller is unchanged. progress=False (default, and auto-save) runs Phase 2
        inline, preserving prior behaviour for headless/scripted callers.
        """
        if not getattr(main_window, 'edit_mode', True):
            return False, "Saving is disabled in View-Only mode."

        # Re-entrancy guard: a modal save pumps the event loop, so the auto-save /
        # other timers can fire mid-save. A second concurrent save would write the
        # same DB connection from two paths — refuse it.
        if getattr(main_window, '_save_in_progress', False):
            return False, "A save is already in progress."
        main_window._save_in_progress = True
        try:
            db: ProjectDatabase = getattr(main_window, 'project_db', None)
            if db is None or not db.is_open:
                # First save — create DB at the new path
                db = ProjectDatabase()
                db.open(path)
                main_window.project_db = db
                main_window.arch_controller.set_project_db(db)
            elif db.db_path != path:
                # Save-As: checkpoint the WAL into the main DB file FIRST, then
                # close + copy. Without the checkpoint, recent commits may still
                # live only in the -wal sidecar, which shutil.copy2 (main file
                # only) would not carry to the new path — silent data loss.
                src_path = db.db_path
                try:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    db.commit()
                except Exception:
                    pass
                db.close()
                import shutil
                if src_path and os.path.exists(src_path):
                    shutil.copy2(src_path, path)
                db.open(path)
                main_window.project_db = db
                main_window.arch_controller.set_project_db(db)

            # --- Phase 1: gather everything that reads Qt widgets (MAIN thread) ---
            # 1. Flush current table rows to DB (reads the live QTableWidget)
            main_window.arch_controller.flush_current_data_to_model()
            # 2. Column layout + settings (get_project_data reads the table)
            full_data = main_window.arch_controller.get_project_data()
            settings = full_data.get("settings", {})
            settings["auto_save_interval"] = getattr(main_window, 'auto_save_interval', 'immediate')
            # 3. Test-case design text (reads QLineEdit/QPlainTextEdit)
            tc_payload = None
            if hasattr(main_window, 'test_case_controller'):
                tc = main_window.test_case_controller
                tc_payload = {
                    "project_title": tc.get_project_title(),
                    "design_template": tc.get_design_template(),
                    "operation_grouping": tc.get_operation_grouping(),
                }
            payload = {
                "config": full_data.get("config", []),
                "settings": settings,
                "tc": tc_payload,
                "master_hash": getattr(main_window, 'master_password_hash', None),
            }

            # --- Phase 2: persist (DB / files / managers only — no widgets) ---
            use_modal = (progress and not is_temp
                         and isinstance(main_window, QtWidgets.QWidget)
                         and not getattr(main_window, 'test_mode', False)
                         and QtWidgets.QApplication.instance() is not None)
            if use_modal:
                from .Logic_Loading_Window import LoadingDialog
                loader = LoadingDialog(main_window)
                try:
                    loader.ui.lbl_loading_text.setText("Saving project…")
                except Exception:
                    pass
                ok = loader.run_task(ProjectSaver._persist, main_window, db, path, payload, is_temp)
                if not ok:
                    return False, f"Failed to save project: {loader.error_msg}"
            else:
                ProjectSaver._persist(main_window, db, path, payload, is_temp)

            return True, "Project saved successfully." + (" (Temp)" if is_temp else "")

        except Exception as e:
            return False, f"Failed to save project: {e}"
        finally:
            main_window._save_in_progress = False

    @staticmethod
    def _persist(main_window, db, path, payload, is_temp):
        """Phase 2 of save: DB writes, ELF cache, integrity HMAC, WAL checkpoint.

        Touches only the DB connection, the (widget-free) model/release managers,
        the parser and the filesystem — safe to run on a worker thread. Progress
        is logged so it streams into the LoadingDialog console."""
        logger.info("Writing project metadata…")
        # 2. Column layout
        db.save_column_layout(payload.get("config", []))

        # 3. Settings
        for k, v in payload.get("settings", {}).items():
            db.set_meta(k, v)

        # 4. Master password hash
        master_hash = payload.get("master_hash")
        if master_hash:
            db.set_meta("master_password_hash", master_hash)

        # 5. Test-case design
        if payload.get("tc") is not None:
            db.set_test_case_design(payload["tc"])

        # 6. ELF data: flush parser to DB (first save) and export cache JSON only when changed
        if main_window.parser:
            parser: ELFParser = main_window.parser
            if parser.md5_hash and not db.has_elf(parser.md5_hash):
                # Still in-memory — flush to DB now
                logger.info("Writing ELF data to project database…")
                parser.flush_to_db(db)
            elif parser.md5_hash and not parser._db:
                parser._db = db
                parser._active_elf_hash = parser.md5_hash

            # Export cache JSON only when the ELF hash changed or the file is missing
            if parser._db and parser._active_elf_hash:
                last_exported = db.get_meta("last_exported_elf_hash")
                cache_dir = ProjectSaver._elf_cache_dir(path)
                cache_file = os.path.join(
                    cache_dir, f"elf_{parser._active_elf_hash}.json"
                )
                if (parser._active_elf_hash != last_exported
                        or not os.path.exists(cache_file)):
                    logger.info("Exporting ELF cache…")
                    parser.export_elf_cache(cache_dir)
                    db.set_meta("last_exported_elf_hash", parser._active_elf_hash)

        # 7. Release registry + ELF hash linkage
        active_release = main_window.arch_controller.release_manager.get_active_release()
        if active_release and main_window.parser and main_window.parser.md5_hash:
            if not active_release.elf_hash:
                active_release.elf_hash = main_window.parser.md5_hash
                active_release.elf_path = str(main_window.parser.elf_path or "")
        logger.info("Saving models and releases…")
        main_window.arch_controller.release_manager.save_registry()
        main_window.arch_controller.model_manager.save_registry()
        # Persist EVERY model's rows (not just the active one). Models created
        # during a multi-sheet import live only in data_cache until now.
        main_window.arch_controller.model_manager.save_all_model_data()

        # 8. History
        if not hasattr(main_window, 'history_manager') or main_window.history_manager is None:
            from .Logic_History import HistoryManager
            main_window.history_manager = HistoryManager(db)
        else:
            main_window.history_manager.set_db(db)

        # Integrity stamp: HMAC over canonical logical content, stored INSIDE
        # the DB (so it travels with the file and can't desync like the old
        # sidecar). Must be the last content write before commit; it is
        # excluded from the digest so it isn't self-referential.
        if not is_temp:
            logger.info("Computing integrity stamp…")
            master_hash = db.get_meta("master_password_hash")
            integrity = ProjectSaver.compute_integrity_hmac(db, master_hash)
            db.set_meta("integrity_hmac", integrity)

        db.commit()

        if not is_temp:
            ProjectSaver.cleanup_temp(path)

            if db.is_open:
                logger.info("Checkpointing database…")
                db.execute("PRAGMA wal_checkpoint(FULL)")

            # Remove any stale sidecar left by the old file-byte scheme.
            legacy_sidecar = path + ".integrity"
            if os.path.exists(legacy_sidecar):
                try:
                    os.remove(legacy_sidecar)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @staticmethod
    def load_project(main_window, path: str):
        try:
            # 1. Close any existing open ProjectDatabase to release locks
            old_db = getattr(main_window, 'project_db', None)
            if old_db and old_db.is_open:
                old_db.close()
            main_window.project_db = None

            # 2. Prevent any auto-saves during project load by resetting current_project_file to None
            main_window.current_project_file = None

            # 3. Clear stale parser, matcher, and database references
            if hasattr(main_window, 'arch_controller') and main_window.arch_controller:
                main_window.arch_controller._db = None
                main_window.arch_controller.parser = None
                main_window.arch_controller.matcher = None
            main_window.parser = None

            main_window.arch_controller.is_loading = True
            main_window.arch_controller.reset_controller()

            # Open DB
            db = ProjectDatabase()
            db.open(path)
            main_window.project_db = db
            main_window.arch_controller.set_project_db(db)

            # Integrity check: recompute the HMAC over canonical logical content
            # and compare to the value stored in the DB. Done right after open,
            # before any load-time writes. Legacy projects (no stored integrity)
            # open silently and get stamped on the next save.
            integrity_mismatch = False
            try:
                stored = db.get_meta("integrity_hmac")
                if stored:
                    master_hash = db.get_meta("master_password_hash")
                    expected = ProjectSaver.compute_integrity_hmac(db, master_hash)
                    integrity_mismatch = not hmac.compare_digest(
                        str(stored), str(expected)
                    )
            except Exception:
                integrity_mismatch = False
            main_window.integrity_mismatch = integrity_mismatch

            success, msg = ProjectSaver._load_from_db(main_window, db, path)
            main_window.arch_controller.is_loading = False

            if success:
                main_window.current_project_file = path

            # History manager
            from .Logic_History import HistoryManager
            main_window.history_manager = HistoryManager(db)

            return success, msg

        except Exception as e:
            if hasattr(main_window, 'arch_controller'):
                main_window.arch_controller.is_loading = False
            return False, f"Failed to load project: {e}"

    @staticmethod
    def _load_from_db(main_window, db: ProjectDatabase, path: str):
        try:
            # 1. Load column layout
            layout_config = db.load_column_layout()

            # 2. Load settings
            all_meta = db.get_all_meta()
            settings_config = {
                "default_cyclicity": all_meta.get("default_cyclicity", "10"),
                "show_retired": all_meta.get("show_retired", True),
                "show_deleted": all_meta.get("show_deleted", False),
            }
            main_window.master_password_hash = all_meta.get("master_password_hash")
            auto_save_val = all_meta.get("auto_save_interval", "immediate")

            # 3. Apply to controller (before loading rows so column config is ready)
            main_window.arch_controller.active_config = [tuple(c) for c in layout_config]
            main_window.arch_controller._rebuild_column_objects()
            main_window.arch_controller.current_default_cyclicity = str(
                settings_config.get("default_cyclicity", "10")
            )
            show_retired = settings_config.get("show_retired", True)
            if isinstance(show_retired, str):
                show_retired = show_retired.lower() == "true"
            main_window.arch_controller.show_retired = show_retired
            show_deleted = settings_config.get("show_deleted", False)
            if isinstance(show_deleted, str):
                show_deleted = show_deleted.lower() == "true"
            main_window.arch_controller.show_deleted = show_deleted
            main_window.arch_controller._setup_table_style()

            # 4. Load model manager
            main_window.arch_controller.model_manager.set_db(db)
            main_window.arch_controller.list_model.refresh()
            main_window.arch_controller.model_manager.preload_all_models()

            # 5. Load release manager
            main_window.arch_controller.release_manager.set_db(db)

            # 6. Load ELF parser from DB
            active_release = main_window.arch_controller.release_manager.get_active_release()
            if active_release and active_release.elf_hash:
                elf_hash = active_release.elf_hash
                if db.has_elf(elf_hash):
                    parser = ELFParser()
                    parser.elf_path = None
                    if active_release.elf_path:
                        from pathlib import Path
                        parser.elf_path = Path(active_release.elf_path)
                    parser.load_from_db(db, elf_hash)
                    main_window.parser = parser
                    main_window.arch_controller.populate_from_parser(
                        parser, skip_release_create=True
                    )
                else:
                    # ELF data missing from DB — try to import from cache
                    cache_dir = ProjectSaver._elf_cache_dir(path)
                    cache_file = os.path.join(cache_dir, f"elf_{elf_hash}.json")
                    if os.path.exists(cache_file):
                        imported_hash = ELFParser.import_elf_cache_to_db(cache_file, db)
                        if imported_hash:
                            parser = ELFParser()
                            parser.load_from_db(db, imported_hash)
                            main_window.parser = parser
                            main_window.arch_controller.populate_from_parser(
                                parser, skip_release_create=True
                            )

            # 7. Load active model into table
            main_window.arch_controller.load_active_model_to_table()

            # 8. Test-case design
            tc_data = db.get_test_case_design()
            if tc_data and hasattr(main_window, 'test_case_controller'):
                main_window.test_case_controller.load_data(tc_data)

            # 9. Auto-save interval
            if hasattr(main_window, 'set_auto_save_interval'):
                main_window.set_auto_save_interval(auto_save_val)

            return True, "Project loaded successfully."

        except Exception as e:
            return False, f"Failed to load project from DB: {e}"

    # ------------------------------------------------------------------
    # Legacy shim — _populate_parser kept for baseline loading
    # ------------------------------------------------------------------

    @staticmethod
    def _populate_parser(main_window, elf_data: dict):
        """Legacy path: populate parser from a dict (baseline load, etc.)."""
        parser = ELFParser()
        db = getattr(main_window, 'project_db', None)

        elf_hash = elf_data.get("elf_hash")
        if db and db.is_open and elf_hash:
            if not db.has_elf(elf_hash):
                db.register_elf(elf_hash, elf_data.get("elf_path", ""))
                db.bulk_insert_symbols(elf_hash, elf_data.get("symbols", []))
                db.bulk_insert_functions(elf_hash, elf_data.get("functions", []))
                db.bulk_insert_structures(elf_hash, elf_data.get("structures", {}))
                db.bulk_insert_global_vars(elf_hash, elf_data.get("global_vars", {}))
                db.commit()
            from pathlib import Path
            parser.elf_path = Path(elf_data.get("elf_path", ""))
            parser.load_from_db(db, elf_hash)
        else:
            # Fully in-memory fallback (e.g. during baseline view with no DB)
            from pathlib import Path
            from core.elf_parser import Symbol, Function
            parser.elf_path = Path(elf_data.get("elf_path", ""))
            parser.md5_hash = elf_hash
            parser.symbols = [Symbol(**s) for s in elf_data.get("symbols", [])]
            parser.functions = [Function(**f) for f in elf_data.get("functions", [])]
            parser.structures = elf_data.get("structures", {})
            parser.global_vars_dwarf = elf_data.get("global_vars", {})
            parser._build_function_address_map()

        main_window.parser = parser
        main_window.arch_controller.populate_from_parser(parser, skip_release_create=True)

    # ------------------------------------------------------------------
    # Unused / removed legacy helpers (stubs for import compatibility)
    # ------------------------------------------------------------------

    _cached_elf_data = None
    _cached_parser_hash = None

    @staticmethod
    def get_temp_path(file_path):
        return None
