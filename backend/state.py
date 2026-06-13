"""
AppState — headless project lifecycle (plan §3.2 / §3.3).

The Qt app drove the logic layer through a god-object ``main_window``. The
worker has no widgets, so AppState owns the equivalent state directly: the open
``ProjectDatabase`` plus the Qt-free ``ArchitectureManager`` / ``ReleaseManager``,
the project path, the edit mode, and the file-lock state. Routers read and
mutate the DB through here.

View-only is enforced server-side with ``PRAGMA query_only=ON`` (so a read-only
session physically cannot write), in addition to the edit lock.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
from typing import Optional

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Application_Logic.Logic_File_Locking import FileLockManager

from .events import EventBus

logger = logging.getLogger(__name__)

MODE_VIEW = "view"          # read-only, no lock
MODE_EXCLUSIVE = "exclusive"  # holds the edit lock, read-write


class ProjectError(RuntimeError):
    """Raised for expected project-lifecycle failures (surfaced as 4xx)."""


class AppState:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self._lock = threading.RLock()

        self.db: Optional[ProjectDatabase] = None
        self.project_path: Optional[str] = None
        self.mode: Optional[str] = None
        self.arch_manager: Optional[ArchitectureManager] = None
        self.release_manager: Optional[ReleaseManager] = None
        self.master_password_hash: Optional[str] = None
        self.integrity_mismatch: bool = False
        self.lock_info: dict = {}
        self._matchers: dict = {}   # elf_hash -> SymbolMatcher (name-list cache)

    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self.db is not None and self.db.is_open

    @property
    def can_edit(self) -> bool:
        return self.mode == MODE_EXCLUSIVE

    def require_open(self) -> ProjectDatabase:
        if not self.is_open:
            raise ProjectError("No project is open.")
        return self.db  # type: ignore[return-value]

    def require_edit(self) -> ProjectDatabase:
        db = self.require_open()
        if not self.can_edit:
            raise ProjectError("Project is open in view-only mode.")
        return db

    def require_arch(self) -> ArchitectureManager:
        self.require_open()
        if self.arch_manager is None:
            raise ProjectError("No architecture manager.")
        return self.arch_manager

    def model_index_by_id(self, model_id: int) -> int:
        """Index of a model in the manager's list, or raise ProjectError."""
        mgr = self.require_arch()
        for i, m in enumerate(mgr.models):
            if m.id == model_id:
                return i
        raise ProjectError(f"No such model: {model_id}")

    def require_releases(self) -> ReleaseManager:
        self.require_open()
        if self.release_manager is None:
            raise ProjectError("No release manager.")
        return self.release_manager

    def release_index_by_id(self, release_id: int) -> int:
        rm = self.require_releases()
        for i, r in enumerate(rm.releases):
            if r.id == release_id:
                return i
        raise ProjectError(f"No such release: {release_id}")

    def active_elf_hash(self) -> Optional[str]:
        """ELF hash of the active release, or None when no ELF is imported."""
        rm = self.release_manager
        if rm is None:
            return None
        active = rm.get_active_release()
        return active.elf_hash if active else None

    def get_symbol_matcher(self, elf_hash: str):
        """A name-list-only SymbolMatcher for ``elf_hash``, cached per session.

        The DB-backed matcher loads only symbol *name* strings (not full objects)
        and never touches the parser, so we build it with ``parser=None``.
        """
        from Application_Logic.Logic_Symbol_Matcher import SymbolMatcher
        db = self.require_open()
        if not db.has_elf(elf_hash):
            raise ProjectError(f"No ELF in project for hash {elf_hash}.")
        if elf_hash not in self._matchers:
            self._matchers[elf_hash] = SymbolMatcher(None, db=db, elf_hash=elf_hash)
        return self._matchers[elf_hash]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def new_project(self, path: str) -> dict:
        """Create a fresh .arch at ``path`` and open it exclusive-edit."""
        with self._lock:
            self._close_locked()
            if os.path.exists(path):
                raise ProjectError(f"File already exists: {path}")
            # Create the .arch first — the lock manager keys its lock file off an
            # existing project path, so the DB file must exist before we lock it.
            db = ProjectDatabase()
            db.open(path)            # create_schema=True by default
            db.commit()
            acquired, msg = FileLockManager.acquire_lock(path)
            if not acquired:
                db.close()
                raise ProjectError(f"Could not acquire edit lock: {msg}")
            self._wire(db, path, MODE_EXCLUSIVE)
            self.bus.publish("db-changed", {"reason": "new"})
            return self.status()

    def open_project(self, path: str, mode: str = MODE_EXCLUSIVE) -> dict:
        """Open an existing .arch. ``mode`` is 'exclusive' or 'view'."""
        if mode not in (MODE_VIEW, MODE_EXCLUSIVE):
            raise ProjectError(f"Unknown mode: {mode}")
        with self._lock:
            self._close_locked()
            if not os.path.exists(path):
                raise ProjectError(f"No such file: {path}")

            if mode == MODE_EXCLUSIVE:
                acquired, msg = FileLockManager.acquire_lock(path)
                if not acquired:
                    # Fall back to view-only with the contended-lock detail.
                    self.lock_info = FileLockManager.check_lock(path)
                    raise ProjectError(f"Locked by another session: {msg}")

            db = ProjectDatabase()
            db.open(path)
            if mode == MODE_VIEW:
                db.set_read_only(True)   # PRAGMA query_only=ON
            self._wire(db, path, mode)
            self._check_integrity()
            self.bus.publish("db-changed", {"reason": "open"})
            return self.status()

    def save_project(self) -> dict:
        """Persist pending work: commit, re-stamp the integrity HMAC, checkpoint.

        In the worker the .arch *is* the live DB — routers mutate it directly —
        so 'save' is a durability barrier (commit + WAL checkpoint) plus a fresh
        tamper-evident integrity stamp, not a table-flush like the Qt app.
        """
        with self._lock:
            db = self.require_edit()
            try:
                stamp = ProjectSaver.compute_integrity_hmac(db, self.master_password_hash)
                db.set_meta("integrity_hmac", stamp)
                db.commit()
                try:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:  # noqa: BLE001 — checkpoint best-effort
                    pass
                db.commit()
            except Exception as e:  # noqa: BLE001
                raise ProjectError(f"Save failed: {e}") from e
            self.bus.publish("db-changed", {"reason": "save"})
            return self.status()

    def close_project(self) -> dict:
        with self._lock:
            self._close_locked()
            self.bus.publish("db-changed", {"reason": "close"})
            return self.status()

    # ------------------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            active_model = None
            active_release = None
            model_count = release_count = 0
            if self.arch_manager is not None:
                active = self.arch_manager.get_active_model()
                active_model = active.name if active else None
                model_count = len([m for m in self.arch_manager.models if not m.is_deleted])
            if self.release_manager is not None:
                active_r = self.release_manager.get_active_release()
                active_release = active_r.name if active_r else None
                release_count = len(self.release_manager.releases)
            return {
                "open": self.is_open,
                "path": self.project_path,
                "mode": self.mode,
                "can_edit": self.can_edit,
                "integrity_mismatch": self.integrity_mismatch,
                "active_model": active_model,
                "active_release": active_release,
                "model_count": model_count,
                "release_count": release_count,
                "lock_info": self.lock_info,
            }

    # ------------------------------------------------------------------
    # internals (call with self._lock held)
    # ------------------------------------------------------------------
    def _wire(self, db: ProjectDatabase, path: str, mode: str) -> None:
        self.db = db
        self.project_path = path
        self.mode = mode
        self.arch_manager = ArchitectureManager(path)
        self.arch_manager.set_db(db)
        self.arch_manager.load_registry()
        self.release_manager = ReleaseManager(path)
        self.release_manager.set_db(db)
        self.release_manager.load_registry()
        self.master_password_hash = db.get_meta("master_password_hash")
        if mode == MODE_EXCLUSIVE:
            self.lock_info = {"held": True, "by": FileLockManager.get_username()}
        else:
            self.lock_info = FileLockManager.check_lock(path)

    def _check_integrity(self) -> None:
        self.integrity_mismatch = False
        db = self.db
        if db is None:
            return
        try:
            stored = db.get_meta("integrity_hmac")
            if stored:
                expected = ProjectSaver.compute_integrity_hmac(db, self.master_password_hash)
                self.integrity_mismatch = not hmac.compare_digest(str(stored), str(expected))
        except Exception:  # noqa: BLE001 — legacy/partial projects open silently
            self.integrity_mismatch = False

    def _close_locked(self) -> None:
        if self.db is not None and self.db.is_open:
            try:
                self.db.close()
            except Exception:  # noqa: BLE001
                logger.warning("Error closing DB", exc_info=True)
        if self.project_path and self.mode == MODE_EXCLUSIVE:
            try:
                FileLockManager.release_lock(self.project_path)
            except Exception:  # noqa: BLE001
                logger.warning("Error releasing lock", exc_info=True)
        self.db = None
        self.project_path = None
        self.mode = None
        self.arch_manager = None
        self.release_manager = None
        self.master_password_hash = None
        self.integrity_mismatch = False
        self.lock_info = {}
        self._matchers = {}
