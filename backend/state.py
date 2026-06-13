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

import atexit
import hmac
import logging
import os
import shutil
import tempfile
import threading
from typing import Optional

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Release_Manager import ReleaseManager
from Application_Logic.Logic_Project_Saving import ProjectSaver
from Application_Logic.Logic_Security import SecurityManager
from Application_Logic.Logic_File_Locking import (
    FileLockManager, LOCK_HEARTBEAT_INTERVAL_SECONDS,
)
from Application_Logic import Logic_Crypto as crypto

from .events import EventBus

logger = logging.getLogger(__name__)

MODE_VIEW = "view"          # read-only, no lock
MODE_EXCLUSIVE = "exclusive"  # holds the edit lock, read-write


class ProjectError(RuntimeError):
    """Raised for expected project-lifecycle failures (surfaced as 4xx)."""


class AppState:
    def __init__(self, bus: EventBus,
                 heartbeat_interval: float = LOCK_HEARTBEAT_INTERVAL_SECONDS) -> None:
        self.bus = bus
        self._lock = threading.RLock()
        self._heartbeat_interval = heartbeat_interval

        self.db: Optional[ProjectDatabase] = None
        self.project_path: Optional[str] = None
        self.mode: Optional[str] = None
        self.arch_manager: Optional[ArchitectureManager] = None
        self.release_manager: Optional[ReleaseManager] = None
        self.master_password_hash: Optional[str] = None
        self.integrity_mismatch: bool = False
        self.lock_info: dict = {}
        self.lock_lost: bool = False
        self._matchers: dict = {}   # elf_hash -> SymbolMatcher (name-list cache)
        self._hb_thread: Optional[threading.Thread] = None
        self._hb_stop: Optional[threading.Event] = None

        # At-rest encryption (master-password protected projects). For an
        # encrypted project the live DB lives in a private temp file; project_path
        # stays the user-facing encrypted .arch. Plaintext/legacy projects leave
        # these at their defaults (db_file == project_path, encrypted False).
        self._db_file: Optional[str] = None
        self._encrypted: bool = False
        self._password: Optional[str] = None
        self._temp_dir: Optional[str] = None
        self._atexit_registered: bool = False

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
        if self.lock_lost:
            raise ProjectError("Edit lock was lost (taken over by another session). "
                               "Reopen the project to regain exclusive edit.")
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
    def new_project(self, path: str, password: Optional[str] = None) -> dict:
        """Create a fresh .arch at ``path`` and open it exclusive-edit.

        With a real ``password`` the project is encrypted at rest: the live DB is
        created in a private temp file and the encrypted blob is written to
        ``path``. No password (or a test-bypass password) → plaintext SQLite.
        """
        with self._lock:
            self._close_locked()
            if os.path.exists(path):
                raise ProjectError(f"File already exists: {path}")

            encrypted = not crypto.bypasses_encryption(password)
            db_file = self._provision_db_file(path, encrypted)

            db = ProjectDatabase()
            db.open(db_file)            # create_schema=True by default
            if encrypted:
                db.set_meta("master_password_hash", SecurityManager.hash_password(password))
            db.commit()

            if encrypted:
                # The lock manager keys its lock file off an existing project
                # path, so the encrypted blob must exist before we lock it.
                self._encrypt_to_disk(db, db_file, path, password)

            acquired, msg = FileLockManager.acquire_lock(path)
            if not acquired:
                db.close()
                self._purge_temp()
                raise ProjectError(f"Could not acquire edit lock: {msg}")

            self._db_file, self._encrypted, self._password = db_file, encrypted, password
            self._wire(db, path, MODE_EXCLUSIVE)
            self.bus.publish("db-changed", {"reason": "new"})
            return self.status()

    def open_project(self, path: str, mode: str = MODE_EXCLUSIVE,
                     password: Optional[str] = None) -> dict:
        """Open an existing .arch. ``mode`` is 'exclusive' or 'view'.

        Plaintext (legacy/dev) projects open directly. Encrypted projects need
        the master password — without it, ``crypto.PasswordRequired`` is raised;
        a wrong password raises ``crypto.PasswordInvalid`` (mapped to 401/403).
        """
        if mode not in (MODE_VIEW, MODE_EXCLUSIVE):
            raise ProjectError(f"Unknown mode: {mode}")
        with self._lock:
            self._close_locked()
            if not os.path.exists(path):
                raise ProjectError(f"No such file: {path}")

            encrypted = crypto.is_encrypted_file(path)
            if encrypted:
                if not password:
                    raise crypto.PasswordRequired("Master password required.")
                db_file = self._provision_db_file(path, encrypted=True)
                # Raises PasswordInvalid on a wrong password (before we lock).
                crypto.decrypt_file(path, db_file, password)
            elif crypto.is_plaintext_sqlite(path):
                db_file = path
            else:
                raise ProjectError("Unrecognized project file format.")

            if mode == MODE_EXCLUSIVE:
                acquired, msg = FileLockManager.acquire_lock(path)
                if not acquired:
                    # Fall back to view-only with the contended-lock detail.
                    self.lock_info = FileLockManager.check_lock(path)
                    self._purge_temp()
                    raise ProjectError(f"Locked by another session: {msg}")

            db = ProjectDatabase()
            db.open(db_file)
            if mode == MODE_VIEW:
                db.set_read_only(True)   # PRAGMA query_only=ON
            self._db_file, self._encrypted, self._password = db_file, encrypted, password
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
                if self._encrypted:
                    # Re-encrypt the now-consistent temp DB back to the .arch.
                    self._encrypt_to_disk(db, self._db_file, self.project_path,
                                          self._password)
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
                "lock_lost": self.lock_lost,
                "encrypted": self._encrypted,
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
        self.lock_lost = False
        if mode == MODE_EXCLUSIVE:
            self.lock_info = {"held": True, "by": FileLockManager.get_username()}
            self._start_heartbeat(path)
        else:
            self.lock_info = FileLockManager.check_lock(path)

    def _check_integrity(self) -> None:
        self.integrity_mismatch = False
        db = self.db
        if db is None:
            return
        if self._encrypted:
            # Fernet already authenticated the payload on decrypt — a wrong
            # password or any tampering would have failed before we got here.
            return
        try:
            stored = db.get_meta("integrity_hmac")
            if stored:
                expected = ProjectSaver.compute_integrity_hmac(db, self.master_password_hash)
                self.integrity_mismatch = not hmac.compare_digest(str(stored), str(expected))
        except Exception:  # noqa: BLE001 — legacy/partial projects open silently
            self.integrity_mismatch = False

    # ------------------------------------------------------------------
    # At-rest encryption helpers (call with self._lock held)
    # ------------------------------------------------------------------
    def _provision_db_file(self, project_path: str, encrypted: bool) -> str:
        """The actual file the SQLite connection uses. Plaintext → the project
        path itself; encrypted → a private temp file the blob decrypts into."""
        if not encrypted:
            return project_path
        if not self._atexit_registered:
            atexit.register(self._purge_temp)   # crash-safety net for the temp dir
            self._atexit_registered = True
        self._temp_dir = tempfile.mkdtemp(prefix="archsess_")
        try:
            os.chmod(self._temp_dir, 0o700)
        except OSError:
            pass
        return os.path.join(self._temp_dir, "project.db")

    def _encrypt_to_disk(self, db: ProjectDatabase, db_file: str,
                         real_path: str, password: str) -> None:
        """Checkpoint the live temp DB to a consistent on-disk state, then write
        the encrypted blob to the user-facing .arch."""
        db.commit()
        try:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.commit()
        except Exception:  # noqa: BLE001 — checkpoint best-effort
            pass
        crypto.encrypt_file(db_file, real_path, password)

    def _purge_temp(self) -> None:
        """Best-effort shred + remove the session temp dir (decrypted DB)."""
        tmp = self._temp_dir
        if not tmp:
            return
        try:
            for name in os.listdir(tmp):
                fp = os.path.join(tmp, name)
                try:
                    size = os.path.getsize(fp)
                    with open(fp, "r+b") as f:
                        f.write(b"\x00" * size)
                        f.flush()
                        os.fsync(f.fileno())
                except OSError:
                    pass
        except OSError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
        self._temp_dir = None

    # ------------------------------------------------------------------
    # Lock heartbeat (plan §3.3)
    # ------------------------------------------------------------------
    def _start_heartbeat(self, path: str) -> None:
        self._stop_heartbeat()
        stop = threading.Event()
        self._hb_stop = stop
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop, args=(path, stop),
            name="lock-heartbeat", daemon=True)
        self._hb_thread.start()

    def _stop_heartbeat(self) -> None:
        if self._hb_stop is not None:
            self._hb_stop.set()
        thread = self._hb_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._hb_thread = None
        self._hb_stop = None

    def _heartbeat_loop(self, path: str, stop: threading.Event) -> None:
        """Refresh the lock's last_seen on a timer; if we no longer own it, flag
        the session lock-lost and emit a `lock` SSE event so the UI drops to
        view-only. Runs on its own thread and never touches the DB connection
        (sqlite connections are thread-affine) — it only reads/writes the lock file.
        """
        while not stop.wait(self._heartbeat_interval):
            try:
                status = FileLockManager.check_lock(path)
            except Exception:  # noqa: BLE001 — lock file race; try again next tick
                continue
            if status.get("status") != "locked_by_me":
                self._on_lock_lost(status)
                return
            FileLockManager.write_heartbeat(path)

    def _on_lock_lost(self, info: dict) -> None:
        # Minimal, thread-safe: flip a flag + publish. require_edit() then refuses
        # writes (409) and status() reports lock_lost; we do NOT mutate the DB
        # connection or managers from this thread.
        self.lock_lost = True
        self.lock_info = info
        self.bus.publish("lock", {"lost": True, "info": info})

    def _close_locked(self) -> None:
        self._stop_heartbeat()
        self.lock_lost = False
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
        self._purge_temp()
        self.db = None
        self.project_path = None
        self.mode = None
        self.arch_manager = None
        self.release_manager = None
        self.master_password_hash = None
        self.integrity_mismatch = False
        self.lock_info = {}
        self._matchers = {}
        self._db_file = None
        self._encrypted = False
        self._password = None
