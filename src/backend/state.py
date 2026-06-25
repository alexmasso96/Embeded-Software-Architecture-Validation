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
import base64
import logging
import os
import shutil
import tempfile
import threading
from typing import Optional

from Application_Logic.Logic_Database import ProjectDatabase
from Application_Logic.Logic_Architecture_Models import ArchitectureManager
from Application_Logic.Logic_Release_Manager import ReleaseManager
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
        self.lock_info: dict = {}
        self.lock_lost: bool = False
        self._matchers: dict = {}   # elf_hash -> SymbolMatcher (name-list cache)
        self._hb_thread: Optional[threading.Thread] = None
        self._hb_stop: Optional[threading.Event] = None

        # Per-block at-rest encryption (master-password protected projects). The
        # .arch is a PLAINTEXT SQLite file opened directly — only sensitive content
        # columns are encrypted, each under a per-category key held in
        # ``_block_cipher`` for the session. ``_encrypted`` means "has a block
        # cipher". The temp-file machinery below is used ONLY by the one-time
        # legacy whole-file (ARCHENC1) migration.
        self._db_file: Optional[str] = None
        self._encrypted: bool = False
        self._password: Optional[str] = None
        self._block_cipher = None
        self._temp_dir: Optional[str] = None
        self._atexit_registered: bool = False

    def block_cipher(self):
        """The session's per-block content cipher (or None). Read by worker
        threads to set_block_cipher on their own connections. Immutable once set,
        so safe to share across threads."""
        return self._block_cipher

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

    def require_table_edit(self) -> ProjectDatabase:
        """Like require_edit, but also rejects writes while a baseline snapshot is
        the active release (a loaded baseline is read-only). Branch/freeze use
        plain require_edit so they still work from a baseline."""
        db = self.require_edit()
        rm = self.release_manager
        active_r = rm.get_active_release() if rm is not None else None
        if active_r is not None and active_r.is_baseline:
            raise ProjectError("Active release is a read-only baseline — "
                               "switch to a release to edit the table.")
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

        With a real ``password`` the project uses per-block content encryption:
        the .arch is a plaintext SQLite file (opened directly) whose sensitive
        columns are encrypted under per-category keys derived from the password.
        No password (or a test-bypass password) → fully plaintext SQLite.
        """
        with self._lock:
            self._close_locked()
            if os.path.exists(path):
                raise ProjectError(f"File already exists: {path}")

            encrypted = not crypto.bypasses_encryption(password)

            db = ProjectDatabase()
            db.open(path)               # plaintext SQLite directly at path
            cipher = None
            if encrypted:
                cipher = self._init_block_encryption(db, password)
                db.set_block_cipher(cipher)
            # Seed the default table layout so a brand-new project opens with the
            # same basic columns the PyQt6 app provided (Logic_Column_Layout).
            from Application_Logic.Logic_Column_Layout import DEFAULT_COLUMN_LAYOUT
            db.save_column_layout(DEFAULT_COLUMN_LAYOUT)
            db.commit()

            acquired, msg = FileLockManager.acquire_lock(path)
            if not acquired:
                db.close()
                raise ProjectError(f"Could not acquire edit lock: {msg}")

            self._db_file = path
            self._encrypted = encrypted
            self._password = password
            self._block_cipher = cipher
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

            # Resolve the per-block cipher (and migrate a legacy whole-file
            # ARCHENC1 project to per-block in place). Raises PasswordRequired /
            # PasswordInvalid for the existing 401/403 mapping — before we lock.
            cipher = self._resolve_cipher_on_open(path, password)
            encrypted = cipher is not None

            if mode == MODE_EXCLUSIVE:
                acquired, msg = FileLockManager.acquire_lock(path)
                if not acquired:
                    # Fall back to view-only with the contended-lock detail.
                    self.lock_info = FileLockManager.check_lock(path)
                    raise ProjectError(f"Locked by another session: {msg}")

            db = ProjectDatabase()
            db.open(path)
            # Attach the cipher BEFORE _wire (registry loads read encrypted rows)
            # and before read-only (reads still need to decrypt in view mode).
            if cipher is not None:
                db.set_block_cipher(cipher)
            if mode == MODE_VIEW:
                db.set_read_only(True)   # PRAGMA query_only=ON
            self._db_file = path
            self._encrypted = encrypted
            self._password = password
            self._block_cipher = cipher
            self._wire(db, path, mode)
            self.bus.publish("db-changed", {"reason": "open"})
            return self.status()

    def flush_active_model_to_release(self) -> None:
        """Sync the active model's working rows (architecture_rows) into the
        active release's release_rows.

        The React table edits architecture_rows directly; release_rows is the
        per-release snapshot the lineage/baselines read. Keeping them in sync on
        save (and on release switch) is what makes activating a release actually
        change the table — see activate_release. No-op for a frozen baseline
        (write-protected) or a read-only DB.
        """
        if self.db is None or getattr(self.db, "read_only", False):
            return
        mgr_a = self.arch_manager
        rm = self.release_manager
        if mgr_a is None or rm is None:
            return
        model = mgr_a.get_active_model()
        rel = rm.get_active_release()
        if model is None or model.id is None or rel is None or rel.id is None:
            return
        if rel.is_baseline:
            return  # frozen snapshot — never overwrite
        self.db.save_release_rows(rel.id, self.db.get_model_rows(model.id))

    def save_project(self) -> dict:
        """Persist pending work: commit, checkpoint.

        In the worker the .arch *is* the live DB — routers mutate it directly —
        so 'save' is a durability barrier (commit + WAL checkpoint), not a
        table-flush like the Qt app. We do still flush the active model's working
        rows into the active release snapshot so release_rows stays authoritative.
        """
        with self._lock:
            db = self.require_edit()
            try:
                self.flush_active_model_to_release()
                db.commit()
                try:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:  # noqa: BLE001 — checkpoint best-effort
                    pass
                db.commit()
                # No whole-file re-encryption: content is already encrypted at the
                # column level, so the .arch on disk is durable after the commit.
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
            active_release_is_baseline = False
            if self.release_manager is not None:
                active_r = self.release_manager.get_active_release()
                active_release = active_r.name if active_r else None
                active_release_is_baseline = bool(active_r and active_r.is_baseline)
                release_count = len(self.release_manager.releases)
            return {
                "open": self.is_open,
                "path": self.project_path,
                "mode": self.mode,
                # A loaded baseline is a read-only snapshot: edits are blocked even
                # in an exclusive-edit project, so fold it into can_edit.
                "can_edit": self.can_edit and not active_release_is_baseline,
                "active_model": active_model,
                "active_release": active_release,
                "active_release_is_baseline": active_release_is_baseline,
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

    # ------------------------------------------------------------------
    # Per-block encryption helpers (call with self._lock held)
    # ------------------------------------------------------------------
    def _init_block_encryption(self, db: ProjectDatabase, password: str):
        """Generate a salt + cipher for a NEW encrypted project and stamp the
        scheme/salt/canary/master-hash into project_meta. Returns the cipher.
        Called before set_block_cipher, so the meta writes land plaintext (the
        canary is already cipher output; the salt/scheme/hash must stay plain)."""
        from Application_Logic.Logic_Block_Crypto import BlockCipher, ENC_SCHEME
        salt = BlockCipher.new_salt()
        cipher = BlockCipher.from_password(password, salt)
        db.set_meta("enc_scheme", ENC_SCHEME)
        db.set_meta("enc_kdf_salt", base64.urlsafe_b64encode(salt).decode("ascii"))
        db.set_meta("enc_canary", cipher.make_canary())
        db.set_meta("master_password_hash", SecurityManager.hash_password(password))
        return cipher

    def _resolve_cipher_on_open(self, path: str, password: Optional[str]):
        """Resolve the per-block cipher for an existing file, migrating a legacy
        whole-file (ARCHENC1) project in place. Returns the cipher, or None for a
        plaintext/test-bypass project. Raises PasswordRequired/PasswordInvalid."""
        from Application_Logic.Logic_Block_Crypto import BlockCipher, ENC_SCHEME
        if crypto.is_encrypted_file(path):
            if not password:
                raise crypto.PasswordRequired("Master password required.")
            return self._migrate_legacy_encrypted(path, password)
        if not crypto.is_plaintext_sqlite(path):
            raise ProjectError("Unrecognized project file format.")
        scheme, salt_b64, canary = self._peek_enc_meta(path)
        if scheme != ENC_SCHEME:
            return None  # plaintext / test-bypass project — no cipher
        if not password:
            raise crypto.PasswordRequired("Master password required.")
        if not salt_b64:
            raise ProjectError("Encrypted project is missing its key salt.")
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        cipher = BlockCipher.from_password(password, salt)
        cipher.verify_canary(canary)   # raises PasswordInvalid on wrong password
        return cipher

    @staticmethod
    def _peek_enc_meta(path: str):
        """Read (enc_scheme, enc_kdf_salt, enc_canary) from a plaintext SQLite
        without going through the full open path. Returns (None, None, None) for
        a project that predates per-block encryption."""
        import sqlite3
        conn = sqlite3.connect(path)
        try:
            def g(k):
                try:
                    row = conn.execute(
                        "SELECT value FROM project_meta WHERE key=?", (k,)).fetchone()
                    return row[0] if row else None
                except sqlite3.Error:
                    return None
            return g("enc_scheme"), g("enc_kdf_salt"), g("enc_canary")
        finally:
            conn.close()

    def _migrate_legacy_encrypted(self, path: str, password: str):
        """One-time: decrypt a legacy ARCHENC1 whole-file project to a temp DB,
        encrypt all content columns per-block, then write the plaintext SQLite
        back over ``path``. Returns the cipher."""
        from Application_Logic.Logic_Block_Crypto import migrate_to_per_block
        from Application_Logic.Logic_Database import ENCRYPTED_META_KEYS
        db_file = self._provision_db_file(path, encrypted=True)
        crypto.decrypt_file(path, db_file, password)   # PasswordInvalid on wrong pw
        db = ProjectDatabase()
        db.open(db_file)               # create_schema=True runs any v→4 upgrade
        try:
            cipher = migrate_to_per_block(db, password, meta_keys=ENCRYPTED_META_KEYS)
            db.commit()
            try:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.commit()
            except Exception:  # noqa: BLE001 — checkpoint best-effort
                pass
        finally:
            db.close()
        tmp = path + ".mig.tmp"
        shutil.copyfile(db_file, tmp)
        os.replace(tmp, path)          # atomic replace of the ARCHENC1 blob
        self._purge_temp()
        return cipher

    def _provision_db_file(self, project_path: str, encrypted: bool) -> str:
        """A private temp file for the one-time legacy-migration decrypt."""
        if not self._atexit_registered:
            atexit.register(self._purge_temp)   # crash-safety net for the temp dir
            self._atexit_registered = True
        self._temp_dir = tempfile.mkdtemp(prefix="archsess_")
        try:
            os.chmod(self._temp_dir, 0o700)
        except OSError:
            pass
        return os.path.join(self._temp_dir, "project.db")

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
        self.lock_info = {}
        self._matchers = {}
        self._db_file = None
        self._encrypted = False
        self._password = None
        self._block_cipher = None
