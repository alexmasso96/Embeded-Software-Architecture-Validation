"""
Project Database
================
SQLite-backed storage for a single .arch project file.
All project state lives here: layout, models, releases, ELF data, history.
"""
import sqlite3
import os
import sys
import json
import hashlib
import hmac
import base64
import datetime
import time
import logging
from contextlib import contextmanager
from typing import Optional

# Override via environment: ARCH_SQLITE_JOURNAL_MODE=DELETE for network shares
_JOURNAL_MODE = os.environ.get("ARCH_SQLITE_JOURNAL_MODE", "WAL").upper()

# Set ARCH_PERF_LOG=1 to enable timing logs for hot DB paths
_PERF_LOG = os.environ.get("ARCH_PERF_LOG", "0") == "1"
_perf_logger = logging.getLogger("arch.perf")


@contextmanager
def _timed(label: str, **extra):
    if not _PERF_LOG:
        yield
        return
    t0 = time.perf_counter()
    yield
    ms = (time.perf_counter() - t0) * 1000
    detail = " ".join(f"{k}={v}" for k, v in extra.items())
    _perf_logger.info("[PERF] %-45s %6.1f ms  %s", label, ms, detail)

DB_SCHEMA_VERSION = 3

# --- Finding D: integrity-digest sort keys -------------------------------
# compute_content_digest() must order rows deterministically AND independently of
# physical/rowid order (so the same logical project digests identically across
# machines). The old code ordered by ALL columns, which means sorting by the big
# `row_data` JSON blob — the dominant cost on Ctrl+S. For the heavy tables we sort
# by a cheap, unique content key instead (the row bytes are still fully hashed —
# we just don't SORT by the megabytes of JSON). Other (small) tables keep the
# all-columns ordering. NOTE: this changes the digest VALUE once, so existing
# projects show a one-time "integrity mismatch" prompt after upgrading (accepted).
_DIGEST_ORDER_KEYS = {
    "release_rows": ("release_id", "row_index"),
    "architecture_rows": ("model_id", "row_index"),
    "release_results": ("release_id", "col_name"),
    "release_column_metadata": ("release_id", "col_name"),
    "model_metadata": ("model_id", "key"),
    "project_meta": ("key",),
}

# --- Finding F: WAL vs DELETE journal mode -------------------------------
# WAL corrupts on network filesystems (its shared-memory index can't work over
# SMB/NFS). Use DELETE (rollback journal) on network/UNC drives, WAL locally.
_LINUX_NET_FS_MAGIC = {
    0x6969,        # NFS
    0x517B,        # SMB (old smbfs)
    0xFF534D42,    # CIFS
    0xFE534D42,    # SMB2
    0x5346414F,    # AFS
    0x564C,        # NCP
    0x73757245,    # CODA
    0x01161970,    # GFS
    0x47504653,    # GFS2
}
_MAC_NET_FSTYPES = {"smbfs", "nfs", "afpfs", "webdav", "cifs", "ftp"}


def _is_network_path_windows(db_path: str) -> bool:
    p = os.path.abspath(db_path)
    if p.startswith("\\\\") or p.startswith("//"):
        return True  # UNC path
    try:
        import ctypes
        drive = os.path.splitdrive(p)[0]
        if drive:
            DRIVE_REMOTE = 4
            return ctypes.windll.kernel32.GetDriveTypeW(
                ctypes.c_wchar_p(drive + "\\")) == DRIVE_REMOTE
    except Exception:
        pass
    return False


def _is_network_fs_posix(db_path: str) -> bool:
    """Best-effort: True if db_path is on a known network filesystem. Uses statfs
    via ctypes (works regardless of packaging, incl. flatpak — no /proc/mounts).
    Returns False on any error (treated as local)."""
    import ctypes
    target = os.path.dirname(os.path.abspath(db_path)) or "."
    try:
        if sys.platform == "darwin":
            class _statfs(ctypes.Structure):
                _fields_ = [
                    ("f_bsize", ctypes.c_uint32), ("f_iosize", ctypes.c_int32),
                    ("f_blocks", ctypes.c_uint64), ("f_bfree", ctypes.c_uint64),
                    ("f_bavail", ctypes.c_uint64), ("f_files", ctypes.c_uint64),
                    ("f_ffree", ctypes.c_uint64), ("f_fsid", ctypes.c_int32 * 2),
                    ("f_owner", ctypes.c_uint32), ("f_type", ctypes.c_uint32),
                    ("f_flags", ctypes.c_uint32), ("f_fssubtype", ctypes.c_uint32),
                    ("f_fstypename", ctypes.c_char * 16),
                    ("f_mntonname", ctypes.c_char * 1024),
                    ("f_mntfromname", ctypes.c_char * 1024),
                    ("f_reserved", ctypes.c_uint32 * 8),
                ]
            libc = ctypes.CDLL("libc.dylib", use_errno=True)
            buf = _statfs()
            if libc.statfs(os.fsencode(target), ctypes.byref(buf)) != 0:
                return False
            return buf.f_fstypename.decode("ascii", "ignore").lower() in _MAC_NET_FSTYPES
        if sys.platform.startswith("linux"):
            class _statfs(ctypes.Structure):
                _fields_ = [("f_type", ctypes.c_long), ("_pad", ctypes.c_byte * 112)]
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            buf = _statfs()
            if libc.statfs(os.fsencode(target), ctypes.byref(buf)) != 0:
                return False
            return (buf.f_type & 0xFFFFFFFF) in _LINUX_NET_FS_MAGIC
    except Exception:
        return False
    return False


class BaselineLockedError(Exception):
    """Raised when a write is attempted against a frozen (is_baseline=1) release.
    Unfreeze the baseline (master-password gated) to make it editable."""


# --- Change-history protection (NC-3) -------------------------------------
# The change history is excluded from the project content digest (it is appended
# outside an explicit save and would balloon the per-save hash cost under the
# target's EDR I/O limits). To still deter tampering by a normal user we
# (1) OBFUSCATE the description at rest and (2) maintain an append-only HMAC
# hash-chain so any edit / deletion / reordering of rows is detectable. The key
# is app-embedded (obfuscation-grade, by design — the threat model is a normal
# user with a SQLite browser, not a determined attacker with the app source).
_HISTORY_SECRET = b"ArchValidatorPro::history-integrity::v1"
_HISTORY_HMAC_KEY = hashlib.sha256(_HISTORY_SECRET + b"::hmac").digest()

try:
    from cryptography.fernet import Fernet, InvalidToken
    _HISTORY_FERNET = Fernet(base64.urlsafe_b64encode(
        hashlib.sha256(_HISTORY_SECRET + b"::obf").digest()))
except Exception:  # pragma: no cover - cryptography always present in this app
    _HISTORY_FERNET = None
    InvalidToken = Exception


def _obfuscate_history(text: str) -> str:
    if not text or _HISTORY_FERNET is None:
        return text
    try:
        return "enc:" + _HISTORY_FERNET.encrypt(text.encode("utf-8")).decode("ascii")
    except Exception:
        return text


def _deobfuscate_history(stored: str) -> str:
    if not stored or _HISTORY_FERNET is None or not stored.startswith("enc:"):
        return stored                      # legacy plaintext rows pass through
    try:
        return _HISTORY_FERNET.decrypt(stored[4:].encode("ascii")).decode("utf-8")
    except Exception:
        return stored


def _history_row_hmac(prev_head: str, timestamp: str, username: str,
                      model_name: str, stored_description: str,
                      release_id) -> str:
    payload = json.dumps(
        [prev_head or "", timestamp or "", username or "", model_name or "",
         stored_description or "", release_id],
        ensure_ascii=False, sort_keys=True, default=str,
    ).encode("utf-8")
    return hmac.new(_HISTORY_HMAC_KEY, payload, hashlib.sha256).hexdigest()

# Tables excluded from the integrity content digest. These are either cosmetic /
# volatile state the app writes OUTSIDE an explicit save (so they must not affect
# integrity), or bulky ELF caches that are already hash-addressed by their own
# md5 and don't need re-hashing here.
_INTEGRITY_EXCLUDED_TABLES = frozenset({
    "ui_state",          # active model id, geometry — written on selection/load
    "history",           # audit log, appended independently of save
    "elf_symbols",       # large, hash-addressed ELF cache
    "elf_functions",
    "elf_structures",
    "elf_global_vars",
    "sqlite_sequence",   # internal AUTOINCREMENT bookkeeping
    "ai_model_mindmaps", # derived AI cache, recomputable from source
    "ai_code_diffs",     # derived AI cache, recomputable from source
})

# project_meta keys excluded from the digest: the integrity value itself (would be
# self-referential) and volatile bookkeeping keys.
_INTEGRITY_EXCLUDED_META = frozenset({
    "integrity_hmac",
    "schema_version",
    "last_exported_elf_hash",
    "ai_source_path",            # machine-specific absolute path
    "ai_previous_source_path",   # machine-specific absolute path
    "ai_requirements_context",   # non-critical AI support metadata (user-locked)
})


class ProjectDatabase:

    def __init__(self):
        self.db_path: Optional[str] = None
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def open(self, db_path: str):
        if self._conn:
            self._conn.close()
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.journal_mode = self._apply_journal_mode(db_path)
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_schema()

    def _apply_journal_mode(self, db_path: str) -> str:
        """Finding F: pick a safe SQLite journal mode for the project's location.
        WAL on local disks; DELETE on network/UNC drives (WAL corrupts there).
        Honors the ARCH_SQLITE_JOURNAL_MODE override."""
        override = os.environ.get("ARCH_SQLITE_JOURNAL_MODE")
        if override:
            mode = override.upper()
            self._conn.execute(f"PRAGMA journal_mode={mode}")
            return mode
        # Windows: decide from the path before engaging WAL.
        if sys.platform == "win32":
            if _is_network_path_windows(db_path):
                self._conn.execute("PRAGMA journal_mode=DELETE")
                logger.info("Network/UNC drive detected -> journal_mode=DELETE")
                return "DELETE"
            self._conn.execute("PRAGMA journal_mode=WAL")
            return "WAL"
        # POSIX: silent WAL test — if WAL won't engage, the FS can't support it.
        try:
            cur = self._conn.execute("PRAGMA journal_mode=WAL")
            actual = (cur.fetchone()[0] or "").upper()
        except Exception:
            actual = ""
        if actual != "WAL":
            self._conn.execute("PRAGMA journal_mode=DELETE")
            logger.info("WAL did not engage -> journal_mode=DELETE (network FS?)")
            return "DELETE"
        # WAL engaged; double-check it isn't a known network FS (permissive shares
        # accept WAL but still corrupt). On inconclusive statfs, trust the WAL test.
        try:
            if _is_network_fs_posix(db_path):
                self._conn.execute("PRAGMA journal_mode=DELETE")
                logger.info("Network filesystem detected -> journal_mode=DELETE")
                return "DELETE"
        except Exception:
            pass
        return "WAL"

    def close(self):
        if self._conn:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def commit(self):
        if self._conn:
            self._conn.commit()

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params):
        return self._conn.executemany(sql, params)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self):
        self._conn.execute("BEGIN IMMEDIATE TRANSACTION;")
        try:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS project_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS column_layout (
                    sort_order  INTEGER NOT NULL,
                    col_name    TEXT    NOT NULL,
                    col_type    TEXT    NOT NULL,
                    col_visible INTEGER NOT NULL DEFAULT 1,
                    col_width   INTEGER NOT NULL DEFAULT 100
                );

                CREATE TABLE IF NOT EXISTS test_case_design (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS ui_state (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS architecture_models (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT    NOT NULL UNIQUE,
                    status     TEXT    NOT NULL DEFAULT 'In Work',
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS architecture_rows (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id  INTEGER NOT NULL REFERENCES architecture_models(id) ON DELETE CASCADE,
                    row_index INTEGER NOT NULL,
                    row_data  TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_arch_rows ON architecture_rows(model_id, row_index);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_arch_rows_unique
                    ON architecture_rows(model_id, row_index);

                CREATE TABLE IF NOT EXISTS model_metadata (
                    model_id INTEGER NOT NULL REFERENCES architecture_models(id) ON DELETE CASCADE,
                    key      TEXT    NOT NULL,
                    value    TEXT,
                    PRIMARY KEY (model_id, key)
                );

                CREATE TABLE IF NOT EXISTS releases (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name                 TEXT    NOT NULL,
                    is_baseline          INTEGER NOT NULL DEFAULT 0,
                    parent_release_name  TEXT,
                    description          TEXT    NOT NULL DEFAULT '',
                    timestamp            TEXT    NOT NULL DEFAULT '',
                    elf_path             TEXT,
                    elf_hash             TEXT,
                    is_deleted           INTEGER NOT NULL DEFAULT 0,
                    deletion_comment     TEXT    NOT NULL DEFAULT '',
                    is_active            INTEGER NOT NULL DEFAULT 0,
                    sort_order           INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS release_rows (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
                    row_index  INTEGER NOT NULL,
                    row_data   TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_release_rows ON release_rows(release_id, row_index);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_release_rows_unique
                    ON release_rows(release_id, row_index);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_releases_unique_name
                    ON releases(name) WHERE is_deleted = 0;

                CREATE TABLE IF NOT EXISTS release_column_metadata (
                    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
                    col_name   TEXT    NOT NULL,
                    metadata   TEXT    NOT NULL DEFAULT '{}',
                    PRIMARY KEY (release_id, col_name)
                );

                CREATE TABLE IF NOT EXISTS release_results (
                    release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
                    col_name   TEXT    NOT NULL,
                    results    TEXT    NOT NULL DEFAULT '[]',
                    PRIMARY KEY (release_id, col_name)
                );

                CREATE TABLE IF NOT EXISTS elf_index (
                    elf_hash         TEXT PRIMARY KEY,
                    elf_path         TEXT NOT NULL DEFAULT '',
                    import_timestamp TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS elf_symbols (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    elf_hash TEXT    NOT NULL,
                    name     TEXT    NOT NULL DEFAULT '',
                    address  INTEGER NOT NULL DEFAULT 0,
                    size     INTEGER NOT NULL DEFAULT 0,
                    sym_type TEXT    NOT NULL DEFAULT '',
                    binding  TEXT    NOT NULL DEFAULT '',
                    section  TEXT    NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_elf_sym_hash ON elf_symbols(elf_hash);
                CREATE INDEX IF NOT EXISTS idx_elf_sym_name ON elf_symbols(elf_hash, name);
                CREATE INDEX IF NOT EXISTS idx_elf_sym_addr ON elf_symbols(elf_hash, address);

                CREATE TABLE IF NOT EXISTS elf_functions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    elf_hash    TEXT    NOT NULL,
                    name        TEXT    NOT NULL DEFAULT '',
                    address     INTEGER NOT NULL DEFAULT 0,
                    size        INTEGER NOT NULL DEFAULT 0,
                    parameters  TEXT    NOT NULL DEFAULT '[]',
                    return_type TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_elf_func_hash ON elf_functions(elf_hash);
                CREATE INDEX IF NOT EXISTS idx_elf_func_name ON elf_functions(elf_hash, name);
                CREATE INDEX IF NOT EXISTS idx_elf_func_addr ON elf_functions(elf_hash, address);

                CREATE TABLE IF NOT EXISTS elf_structures (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    elf_hash TEXT NOT NULL,
                    name     TEXT NOT NULL DEFAULT '',
                    fields   TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_elf_struct_hash ON elf_structures(elf_hash);

                CREATE TABLE IF NOT EXISTS elf_global_vars (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    elf_hash TEXT NOT NULL,
                    name     TEXT NOT NULL DEFAULT '',
                    var_type TEXT NOT NULL DEFAULT 'unknown'
                );
                CREATE INDEX IF NOT EXISTS idx_elf_gvar_hash ON elf_global_vars(elf_hash);
                CREATE INDEX IF NOT EXISTS idx_elf_gvar_name ON elf_global_vars(elf_hash, name);

                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    username    TEXT NOT NULL DEFAULT '',
                    model_name  TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL,
                    release_id  INTEGER REFERENCES releases(id) ON DELETE CASCADE
                );

                -- AI Part 2: per-architecture-model "mind map" index (derived
                -- cache; recomputable from source, excluded from integrity).
                CREATE TABLE IF NOT EXISTS ai_model_mindmaps (
                    model_id        INTEGER PRIMARY KEY
                                        REFERENCES architecture_models(id) ON DELETE CASCADE,
                    mindmap_json    TEXT NOT NULL,
                    source_hash     TEXT,
                    diff_hash       TEXT,
                    builder_version TEXT,
                    char_count      INTEGER DEFAULT 0,
                    updated_at      TEXT
                );

                -- AI Part 2: per-file unified diffs between a current and a
                -- previous source folder. model_id = -1 means project-wide.
                -- (Non-null sentinel so UNIQUE dedups; not declared FK so -1 is
                -- allowed — model-scoped cleanup is explicit in delete_model_mindmap.)
                CREATE TABLE IF NOT EXISTS ai_code_diffs (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id     INTEGER NOT NULL DEFAULT -1,
                    diff_hash    TEXT NOT NULL,
                    file_path    TEXT NOT NULL,
                    status       TEXT NOT NULL,
                    unified_diff TEXT,
                    UNIQUE(model_id, diff_hash, file_path)
                );
                CREATE INDEX IF NOT EXISTS idx_ai_code_diffs_lookup
                    ON ai_code_diffs(model_id, diff_hash);
            """)

            # Add parser_backend column to elf_index if missing (Phase 13 migration)
            try:
                self._conn.execute("ALTER TABLE elf_index ADD COLUMN parser_backend TEXT")
            except sqlite3.OperationalError:
                pass

            # Add code_map_json column to ai_model_mindmaps if missing (Phase 15 migration)
            try:
                self._conn.execute("ALTER TABLE ai_model_mindmaps ADD COLUMN code_map_json TEXT")
            except sqlite3.OperationalError:
                pass

            # Add release_id column to history if missing (Phase 16.5 migration)
            try:
                self._conn.execute("ALTER TABLE history ADD COLUMN release_id INTEGER REFERENCES releases(id) ON DELETE CASCADE")
            except sqlite3.OperationalError:
                pass

            # Add entry_hmac column to history if missing (NC-3: tamper-evidence chain)
            try:
                self._conn.execute("ALTER TABLE history ADD COLUMN entry_hmac TEXT")
            except sqlite3.OperationalError:
                pass

            # Record / upgrade the schema version on the SAME connection+transaction
            # (must NOT call set_meta here — it opens its own `with self._conn`).
            cur = self._conn.execute(
                "SELECT value FROM project_meta WHERE key='schema_version'"
            )
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO project_meta (key, value) VALUES ('schema_version', ?)",
                    (str(DB_SCHEMA_VERSION),)
                )
            elif int(row[0]) < DB_SCHEMA_VERSION:
                # v2 objects are derived caches created above via IF NOT EXISTS —
                # no data backfill needed, just bump the recorded version.
                self._conn.execute(
                    "UPDATE project_meta SET value=? WHERE key='schema_version'",
                    (str(DB_SCHEMA_VERSION),)
                )
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise e

    # ------------------------------------------------------------------
    # Project meta
    # ------------------------------------------------------------------

    def get_meta(self, key: str, default=None):
        cur = self._conn.execute("SELECT value FROM project_meta WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value):
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
                (key, str(value) if value is not None else None)
            )

    def get_all_meta(self) -> dict:
        cur = self._conn.execute("SELECT key, value FROM project_meta")
        return {r[0]: r[1] for r in cur.fetchall()}

    # ------------------------------------------------------------------
    # AI Part 2 — mind map (per architecture model)
    # ------------------------------------------------------------------

    def get_model_mindmap(self, model_id: int) -> Optional[dict]:
        """Return the parsed CompactMindMap dict for a model, or None."""
        cur = self._conn.execute(
            "SELECT mindmap_json FROM ai_model_mindmaps WHERE model_id=?", (model_id,)
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None

    def get_model_mindmap_meta(self, model_id: int) -> Optional[dict]:
        """Return provenance (source_hash/diff_hash/builder_version/char_count/
        updated_at) WITHOUT loading the large mindmap_json blob, or None."""
        cur = self._conn.execute(
            "SELECT source_hash, diff_hash, builder_version, char_count, updated_at "
            "FROM ai_model_mindmaps WHERE model_id=?", (model_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "source_hash": row[0], "diff_hash": row[1],
            "builder_version": row[2], "char_count": row[3], "updated_at": row[4],
        }

    def save_model_mindmap(self, model_id: int, mindmap_json: str,
                           source_hash: str = "", diff_hash: str = "",
                           builder_version: str = "", char_count: int = 0,
                           updated_at: str = "", code_map_json: Optional[str] = None) -> None:
        """Insert or replace the mind map row for a model."""
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO ai_model_mindmaps "
                "(model_id, mindmap_json, source_hash, diff_hash, builder_version, "
                " char_count, updated_at, code_map_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (model_id, mindmap_json, source_hash, diff_hash, builder_version,
                 int(char_count or 0), updated_at, code_map_json),
            )

    def get_model_code_map(self, model_id: int) -> Optional[dict]:
        """Return the parsed CodeMap dict for a model, or None."""
        cur = self._conn.execute(
            "SELECT code_map_json FROM ai_model_mindmaps WHERE model_id=?", (model_id,)
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None

    def save_model_code_map(self, model_id: int, code_map_json: str) -> None:
        """Save or update the CodeMap JSON for a model."""
        with self._conn:
            cur = self._conn.execute("SELECT 1 FROM ai_model_mindmaps WHERE model_id=?", (model_id,))
            if cur.fetchone():
                self._conn.execute(
                    "UPDATE ai_model_mindmaps SET code_map_json=? WHERE model_id=?",
                    (code_map_json, model_id)
                )
            else:
                ts = datetime.datetime.now().isoformat()
                self._conn.execute(
                    "INSERT INTO ai_model_mindmaps (model_id, mindmap_json, updated_at, code_map_json) VALUES (?, ?, ?, ?)",
                    (model_id, "", ts, code_map_json)
                )

    def delete_model_mindmap(self, model_id: int) -> None:
        """Remove a model's mind map AND its associated code-diff rows (the diff
        table is not an FK, so its cascade is handled explicitly here)."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM ai_model_mindmaps WHERE model_id=?", (model_id,))
            self._conn.execute(
                "DELETE FROM ai_code_diffs WHERE model_id=?", (model_id,))

    def has_model_mindmap(self, model_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM ai_model_mindmaps WHERE model_id=? LIMIT 1", (model_id,))
        return cur.fetchone() is not None

    # ------------------------------------------------------------------
    # AI Part 2 — per-file code diffs (current vs previous source)
    # ------------------------------------------------------------------

    def save_code_diffs(self, model_id: int, diff_hash: str,
                        diffs: list) -> None:
        """Clear prior rows for (model_id, diff_hash) then batch-insert. diffs is
        a list of {'file_path','status','unified_diff'} dicts. model_id=-1 for
        project-wide/inception diffs. Clear-then-executemany keeps it batch-
        friendly (EDR per-syscall I/O constraint)."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM ai_code_diffs WHERE model_id=? AND diff_hash=?",
                (model_id, diff_hash))
            self._conn.executemany(
                "INSERT OR REPLACE INTO ai_code_diffs "
                "(model_id, diff_hash, file_path, status, unified_diff) "
                "VALUES (?, ?, ?, ?, ?)",
                [(model_id, diff_hash, d.get("file_path", ""),
                  d.get("status", ""), d.get("unified_diff", "")) for d in diffs],
            )

    def get_code_diffs(self, model_id: int, diff_hash: str) -> list:
        cur = self._conn.execute(
            "SELECT file_path, status, unified_diff FROM ai_code_diffs "
            "WHERE model_id=? AND diff_hash=? ORDER BY file_path",
            (model_id, diff_hash))
        return [{"file_path": r[0], "status": r[1], "unified_diff": r[2]}
                for r in cur.fetchall()]

    def has_code_diff(self, model_id: int, diff_hash: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM ai_code_diffs WHERE model_id=? AND diff_hash=? LIMIT 1",
            (model_id, diff_hash))
        return cur.fetchone() is not None

    def list_diff_files(self, model_id: int, diff_hash: str) -> list:
        cur = self._conn.execute(
            "SELECT file_path FROM ai_code_diffs WHERE model_id=? AND diff_hash=? "
            "ORDER BY file_path", (model_id, diff_hash))
        return [r[0] for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Integrity content digest
    # ------------------------------------------------------------------

    def compute_content_digest(self) -> str:
        """
        Deterministic SHA-256 over the project's *logical* content.

        Unlike hashing the raw .arch file bytes, this is stable across
        save -> close -> reopen cycles and across SQLite versions: it ignores
        SQLite's internal bookkeeping (file change counter, WAL state, page
        layout, freelist) and the volatile/cosmetic tables the app writes
        outside of an explicit save (UI state, history), as well as the
        integrity value itself. That makes it suitable as the basis for a
        tamper-evidence check that does NOT fire on every benign reopen.
        """
        h = hashlib.sha256()
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [
            r[0] for r in cur.fetchall()
            if r[0] not in _INTEGRITY_EXCLUDED_TABLES
            and not r[0].startswith("sqlite_")
        ]
        for tbl in tables:
            cols = [r[1] for r in self._conn.execute(
                f'PRAGMA table_info("{tbl}")'
            ).fetchall()]
            if not cols:
                continue
            # Order rows deterministically and independently of physical/rowid
            # order. Heavy tables (big row_data JSON) use a cheap unique content
            # key (Finding D) so we don't sort by megabytes of JSON; small tables
            # keep the all-columns ordering. The full row bytes are still hashed.
            order_key = _DIGEST_ORDER_KEYS.get(tbl)
            if order_key:
                key_cols = [c for c in order_key if c in cols]
                order_cols = key_cols if key_cols else cols
            else:
                order_cols = cols
            order = ", ".join(f'"{c}"' for c in order_cols)
            h.update(b"\x00TABLE\x00")
            h.update(tbl.encode("utf-8"))
            for row in self._conn.execute(f'SELECT * FROM "{tbl}" ORDER BY {order}'):
                if tbl == "project_meta" and row[0] in _INTEGRITY_EXCLUDED_META:
                    continue
                h.update(b"\x00ROW\x00")
                h.update(json.dumps(
                    list(row), default=str, ensure_ascii=False, sort_keys=True
                ).encode("utf-8"))
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Column layout
    # ------------------------------------------------------------------

    def save_column_layout(self, layout: list):
        with self._conn:
            self._conn.execute("DELETE FROM column_layout")
            rows = []
            for i, col in enumerate(layout):
                name = col[0]
                col_type = col[1]
                visible = int(col[2]) if len(col) > 2 and col[2] is not None else 1
                width = int(col[3]) if len(col) > 3 and col[3] is not None else 100
                rows.append((i, name, col_type, visible, width))
            self._conn.executemany(
                "INSERT INTO column_layout (sort_order, col_name, col_type, col_visible, col_width)"
                " VALUES (?,?,?,?,?)",
                rows
            )

    def load_column_layout(self) -> list:
        cur = self._conn.execute(
            "SELECT col_name, col_type, col_visible, col_width"
            " FROM column_layout ORDER BY sort_order"
        )
        return [(r[0], r[1], bool(r[2]), r[3]) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Test-case design
    # ------------------------------------------------------------------

    def get_test_case_design(self) -> dict:
        cur = self._conn.execute("SELECT key, value FROM test_case_design")
        return {r[0]: r[1] for r in cur.fetchall()}

    def set_test_case_design(self, data: dict):
        with self._conn:
            self._conn.execute("DELETE FROM test_case_design")
            self._conn.executemany(
                "INSERT INTO test_case_design (key, value) VALUES (?, ?)",
                [(k, str(v) if v is not None else None) for k, v in data.items()]
            )

    # ------------------------------------------------------------------
    # UI state
    # ------------------------------------------------------------------

    def get_ui_state(self, key: str, default=None):
        cur = self._conn.execute("SELECT value FROM ui_state WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_ui_state(self, key: str, value):
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO ui_state (key, value) VALUES (?, ?)",
                (key, str(value) if value is not None else None)
            )

    # ------------------------------------------------------------------
    # Architecture models
    # ------------------------------------------------------------------

    def get_all_models(self) -> list:
        cur = self._conn.execute(
            "SELECT id, name, status, is_deleted, sort_order"
            " FROM architecture_models ORDER BY sort_order, id"
        )
        return [dict(r) for r in cur.fetchall()]

    def create_model(self, name: str, status: str = "In Work", sort_order: int = 0) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO architecture_models (name, status, sort_order) VALUES (?, ?, ?)",
                (name, status, sort_order)
            )
            return cur.lastrowid

    def update_model(self, model_id: int, **kwargs):
        allowed = {"name", "status", "is_deleted", "sort_order"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k}=?" for k in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE architecture_models SET {set_clause} WHERE id=?",
                list(fields.values()) + [model_id]
            )

    def get_model_rows(self, model_id: int) -> list:
        with _timed("get_model_rows", model_id=model_id):
            cur = self._conn.execute(
                "SELECT row_data FROM architecture_rows"
                " WHERE model_id=? ORDER BY row_index",
                (model_id,)
            )
            return [json.loads(r[0]) for r in cur.fetchall()]

    def get_model_row(self, model_id: int, row_index: int) -> dict:
        cur = self._conn.execute(
            "SELECT row_data FROM architecture_rows"
            " WHERE model_id=? AND row_index=?",
            (model_id, row_index)
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else {}

    def save_model_rows(self, model_id: int, rows: list):
        with _timed("save_model_rows", model_id=model_id, rows=len(rows)):
            with self._conn:
                self._conn.execute(
                    "DELETE FROM architecture_rows WHERE model_id=?", (model_id,)
                )
                self._conn.executemany(
                    "INSERT INTO architecture_rows (model_id, row_index, row_data) VALUES (?,?,?)",
                    [(model_id, i, json.dumps(row)) for i, row in enumerate(rows)]
                )

    def upsert_model_row(self, model_id: int, row_index: int, row_data: dict):
        """Insert or update a single row — used by dirty-row incremental saves."""
        with _timed("upsert_model_row", model_id=model_id, row_index=row_index):
            with self._conn:
                self._conn.execute(
                    "INSERT INTO architecture_rows (model_id, row_index, row_data)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(model_id, row_index)"
                    " DO UPDATE SET row_data=excluded.row_data",
                    (model_id, row_index, json.dumps(row_data))
                )

    def upsert_model_rows_batch(self, model_id: int, rows: dict):
        """Upsert a batch of {row_index: row_data} — used by dirty-row saves."""
        with _timed("upsert_model_rows_batch", model_id=model_id, rows=len(rows)):
            with self._conn:
                self._conn.executemany(
                    "INSERT INTO architecture_rows (model_id, row_index, row_data)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(model_id, row_index)"
                    " DO UPDATE SET row_data=excluded.row_data",
                    [(model_id, idx, json.dumps(data)) for idx, data in rows.items()]
                )

    def delete_model_row(self, model_id: int, row_index: int):
        with self._conn:
            self._conn.execute(
                "DELETE FROM architecture_rows WHERE model_id=? AND row_index=?",
                (model_id, row_index)
            )

    def copy_model_rows(self, src_model_id: int, dst_model_id: int):
        rows = self.get_model_rows(src_model_id)
        self.save_model_rows(dst_model_id, rows)

    def get_model_metadata(self, model_id: int) -> dict:
        cur = self._conn.execute(
            "SELECT key, value FROM model_metadata WHERE model_id=?",
            (model_id,)
        )
        return {r[0]: json.loads(r[1]) if r[1] else None for r in cur.fetchall()}

    def save_model_metadata(self, model_id: int, metadata: dict):
        with self._conn:
            self._conn.execute("DELETE FROM model_metadata WHERE model_id=?", (model_id,))
            if metadata:
                self._conn.executemany(
                    "INSERT INTO model_metadata (model_id, key, value) VALUES (?,?,?)",
                    [(model_id, k, json.dumps(v)) for k, v in metadata.items()]
                )

    def copy_model_metadata(self, src_model_id: int, dst_model_id: int):
        meta = self.get_model_metadata(src_model_id)
        self.save_model_metadata(dst_model_id, meta)

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    def get_all_releases(self) -> list:
        cur = self._conn.execute(
            "SELECT id, name, is_baseline, parent_release_name, description, timestamp,"
            "       elf_path, elf_hash, is_deleted, deletion_comment, is_active, sort_order"
            " FROM releases ORDER BY sort_order, id"
        )
        return [dict(r) for r in cur.fetchall()]

    def create_release(self, name: str, is_baseline: int = 0,
                       parent_release_name=None, description: str = "",
                       timestamp: str = "", elf_path=None,
                       elf_hash=None, sort_order: int = 0) -> int:
        ts = timestamp or datetime.datetime.now().isoformat()
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO releases (name, is_baseline, parent_release_name, description,"
                " timestamp, elf_path, elf_hash, sort_order)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (name, is_baseline, parent_release_name, description,
                 ts, elf_path, elf_hash, sort_order)
            )
            return cur.lastrowid

    def update_release(self, release_id: int, **kwargs):
        allowed = {"name", "is_baseline", "parent_release_name", "description",
                   "timestamp", "elf_path", "elf_hash",
                   "is_deleted", "deletion_comment", "is_active", "sort_order"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k}=?" for k in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE releases SET {set_clause} WHERE id=?",
                list(fields.values()) + [release_id]
            )

    def set_active_release(self, release_id: Optional[int]):
        with self._conn:
            self._conn.execute("UPDATE releases SET is_active=0")
            if release_id is not None:
                self._conn.execute(
                    "UPDATE releases SET is_active=1 WHERE id=?", (release_id,)
                )

    def get_active_release_id(self) -> Optional[int]:
        cur = self._conn.execute("SELECT id FROM releases WHERE is_active=1 AND is_deleted=0")
        row = cur.fetchone()
        return row[0] if row else None

    def delete_release_record(self, release_id: int):
        with self._conn:
            self._conn.execute("DELETE FROM releases WHERE id=?", (release_id,))

    def is_release_frozen(self, release_id: int) -> bool:
        """True if the release exists and is a frozen baseline (is_baseline=1)."""
        cur = self._conn.execute(
            "SELECT is_baseline FROM releases WHERE id=?", (release_id,)
        )
        row = cur.fetchone()
        return bool(row and row[0])

    def _guard_release_writable(self, release_id: int, allow_frozen: bool):
        """NC-5: reject data writes to a frozen baseline at the DB layer. The
        baseline-creation/clone path passes allow_frozen=True to populate the
        snapshot once; normal edits must first unfreeze (master-password gated)."""
        if not allow_frozen and self.is_release_frozen(release_id):
            raise BaselineLockedError(
                f"Release {release_id} is a frozen baseline; unfreeze it to edit."
            )

    def get_release_rows(self, release_id: int) -> list:
        cur = self._conn.execute(
            "SELECT row_data FROM release_rows"
            " WHERE release_id=? ORDER BY row_index",
            (release_id,)
        )
        return [json.loads(r[0]) for r in cur.fetchall()]

    def save_release_rows(self, release_id: int, rows: list, _allow_frozen: bool = False):
        self._guard_release_writable(release_id, _allow_frozen)
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_rows WHERE release_id=?", (release_id,)
            )
            self._conn.executemany(
                "INSERT INTO release_rows (release_id, row_index, row_data) VALUES (?,?,?)",
                [(release_id, i, json.dumps(row)) for i, row in enumerate(rows)]
            )

    def copy_release_rows(self, src_id: int, dst_id: int):
        rows = self.get_release_rows(src_id)
        self.save_release_rows(dst_id, rows)

    def get_release_column_metadata(self, release_id: int) -> dict:
        cur = self._conn.execute(
            "SELECT col_name, metadata FROM release_column_metadata WHERE release_id=?",
            (release_id,)
        )
        return {r[0]: json.loads(r[1]) for r in cur.fetchall()}

    def save_release_column_metadata(self, release_id: int, metadata: dict,
                                     _allow_frozen: bool = False):
        self._guard_release_writable(release_id, _allow_frozen)
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_column_metadata WHERE release_id=?", (release_id,)
            )
            self._conn.executemany(
                "INSERT INTO release_column_metadata (release_id, col_name, metadata)"
                " VALUES (?,?,?)",
                [(release_id, k, json.dumps(v)) for k, v in metadata.items()]
            )

    def get_release_results(self, release_id: int) -> dict:
        cur = self._conn.execute(
            "SELECT col_name, results FROM release_results WHERE release_id=?",
            (release_id,)
        )
        return {r[0]: json.loads(r[1]) for r in cur.fetchall()}

    def save_release_results(self, release_id: int, results: dict,
                             _allow_frozen: bool = False):
        self._guard_release_writable(release_id, _allow_frozen)
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_results WHERE release_id=?", (release_id,)
            )
            self._conn.executemany(
                "INSERT INTO release_results (release_id, col_name, results) VALUES (?,?,?)",
                [(release_id, k, json.dumps(v)) for k, v in results.items()]
            )

    def get_release_linked_column(self, release_id: int) -> Optional[str]:
        cur = self._conn.execute(
            "SELECT metadata FROM release_column_metadata"
            " WHERE release_id=? AND col_name='__linked_release_column__'",
            (release_id,)
        )
        row = cur.fetchone()
        if row:
            return json.loads(row[0]).get("value")
        return None

    def save_release_linked_column(self, release_id: int, col_name: Optional[str]):
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_column_metadata"
                " WHERE release_id=? AND col_name='__linked_release_column__'",
                (release_id,)
            )
            if col_name is not None:
                self._conn.execute(
                    "INSERT INTO release_column_metadata (release_id, col_name, metadata)"
                    " VALUES (?,?,?)",
                    (release_id, "__linked_release_column__", json.dumps({"value": col_name}))
                )

    # ------------------------------------------------------------------
    # ELF data
    # ------------------------------------------------------------------

    def has_elf(self, elf_hash: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM elf_index WHERE elf_hash=?", (elf_hash,)
        )
        return cur.fetchone() is not None

    def delete_elf(self, elf_hash: str):
        with self._conn:
            self._conn.execute("DELETE FROM elf_index WHERE elf_hash=?", (elf_hash,))
            self._conn.execute("DELETE FROM elf_symbols WHERE elf_hash=?", (elf_hash,))
            self._conn.execute("DELETE FROM elf_functions WHERE elf_hash=?", (elf_hash,))
            self._conn.execute("DELETE FROM elf_structures WHERE elf_hash=?", (elf_hash,))
            self._conn.execute("DELETE FROM elf_global_vars WHERE elf_hash=?", (elf_hash,))

    def register_elf(self, elf_hash: str, elf_path: str, parser_backend: Optional[str] = None):
        ts = datetime.datetime.now().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO elf_index (elf_hash, elf_path, import_timestamp, parser_backend)"
                " VALUES (?,?,?,?)",
                (elf_hash, elf_path or "", ts, parser_backend)
            )

    def bulk_insert_symbols(self, elf_hash: str, symbols):
        BATCH = 2000
        with self._conn:
            batch = []
            for symbol in symbols:
                batch.append(symbol)
                if len(batch) < BATCH:
                    continue
                self._conn.executemany(
                    "INSERT INTO elf_symbols"
                    " (elf_hash, name, address, size, sym_type, binding, section)"
                    " VALUES (?,?,?,?,?,?,?)",
                    [(elf_hash,
                      s.get("name", "") if isinstance(s, dict) else s.name,
                      s.get("address", 0) if isinstance(s, dict) else s.address,
                      s.get("size", 0) if isinstance(s, dict) else s.size,
                      s.get("symbol_type", "") if isinstance(s, dict) else s.symbol_type,
                      s.get("binding", "") if isinstance(s, dict) else s.binding,
                      s.get("section", "") if isinstance(s, dict) else s.section)
                     for s in batch]
                )
                batch.clear()
            if batch:
                self._conn.executemany(
                    "INSERT INTO elf_symbols"
                    " (elf_hash, name, address, size, sym_type, binding, section)"
                    " VALUES (?,?,?,?,?,?,?)",
                    [(elf_hash,
                      s.get("name", "") if isinstance(s, dict) else s.name,
                      s.get("address", 0) if isinstance(s, dict) else s.address,
                      s.get("size", 0) if isinstance(s, dict) else s.size,
                      s.get("symbol_type", "") if isinstance(s, dict) else s.symbol_type,
                      s.get("binding", "") if isinstance(s, dict) else s.binding,
                      s.get("section", "") if isinstance(s, dict) else s.section)
                     for s in batch]
                )

    def bulk_insert_functions(self, elf_hash: str, functions):
        BATCH = 2000
        with self._conn:
            batch = []
            for function in functions:
                batch.append(function)
                if len(batch) < BATCH:
                    continue
                self._conn.executemany(
                    "INSERT INTO elf_functions"
                    " (elf_hash, name, address, size, parameters, return_type)"
                    " VALUES (?,?,?,?,?,?)",
                    [(elf_hash,
                      f.get("name", "") if isinstance(f, dict) else f.name,
                      f.get("address", 0) if isinstance(f, dict) else f.address,
                      f.get("size", 0) if isinstance(f, dict) else f.size,
                      json.dumps(f.get("parameters", []) if isinstance(f, dict) else f.parameters),
                      f.get("return_type") if isinstance(f, dict) else f.return_type)
                     for f in batch]
                )
                batch.clear()
            if batch:
                self._conn.executemany(
                    "INSERT INTO elf_functions"
                    " (elf_hash, name, address, size, parameters, return_type)"
                    " VALUES (?,?,?,?,?,?)",
                    [(elf_hash,
                      f.get("name", "") if isinstance(f, dict) else f.name,
                      f.get("address", 0) if isinstance(f, dict) else f.address,
                      f.get("size", 0) if isinstance(f, dict) else f.size,
                      json.dumps(f.get("parameters", []) if isinstance(f, dict) else f.parameters),
                      f.get("return_type") if isinstance(f, dict) else f.return_type)
                     for f in batch]
                )

    def bulk_insert_structures(self, elf_hash: str, structures: dict):
        BATCH = 500
        items = list(structures.items())
        with self._conn:
            for i in range(0, len(items), BATCH):
                batch = items[i:i + BATCH]
                self._conn.executemany(
                    "INSERT INTO elf_structures (elf_hash, name, fields) VALUES (?,?,?)",
                    [(elf_hash, name, json.dumps(fields)) for name, fields in batch]
                )

    def bulk_insert_global_vars(self, elf_hash: str, global_vars: dict):
        BATCH = 2000
        items = list(global_vars.items())
        with self._conn:
            for i in range(0, len(items), BATCH):
                batch = items[i:i + BATCH]
                self._conn.executemany(
                    "INSERT INTO elf_global_vars (elf_hash, name, var_type) VALUES (?,?,?)",
                    [(elf_hash, name, var_type) for name, var_type in batch]
                )

    def update_function_params(self, elf_hash: str, name: str,
                               parameters: list, return_type=None):
        with self._conn:
            self._conn.execute(
                "UPDATE elf_functions SET parameters=?, return_type=?"
                " WHERE elf_hash=? AND name=?",
                (json.dumps(parameters), return_type, elf_hash, name)
            )

    def get_function_names(self, elf_hash: str) -> list:
        cur = self._conn.execute(
            "SELECT name FROM elf_functions WHERE elf_hash=?", (elf_hash,)
        )
        return [r[0] for r in cur.fetchall()]

    def get_variable_names(self, elf_hash: str) -> list:
        cur = self._conn.execute(
            "SELECT name FROM elf_global_vars WHERE elf_hash=?", (elf_hash,)
        )
        return [r[0] for r in cur.fetchall()]

    def get_symbol_by_address(self, elf_hash: str, address: int):
        cur = self._conn.execute(
            "SELECT name, address, size, sym_type, binding, section"
            " FROM elf_symbols WHERE elf_hash=? AND address=? LIMIT 1",
            (elf_hash, address)
        )
        return cur.fetchone()

    def get_functions_for_address_map(self, elf_hash: str):
        return self._conn.execute(
            "SELECT name, address, size FROM elf_functions WHERE elf_hash=?",
            (elf_hash,)
        )

    def search_functions(self, elf_hash: str, name: str,
                         exact: bool = False) -> list:
        if exact:
            cur = self._conn.execute(
                "SELECT name, address, size, parameters, return_type"
                " FROM elf_functions WHERE elf_hash=? AND name=?",
                (elf_hash, name)
            )
        else:
            cur = self._conn.execute(
                "SELECT name, address, size, parameters, return_type"
                " FROM elf_functions"
                " WHERE elf_hash=? AND name LIKE ?"
                "   AND name NOT LIKE '%_EXIT_%'"
                "   AND name NOT LIKE '%_function_end'",
                (elf_hash, f"%{name}%")
            )
        results = []
        for r in cur.fetchall():
            results.append({
                "name": r[0], "address": r[1], "size": r[2],
                "parameters": json.loads(r[3]) if r[3] else [],
                "return_type": r[4]
            })
        results.sort(key=lambda f: f["name"] != name)
        return results

    def get_all_structures(self, elf_hash: str) -> dict:
        cur = self._conn.execute(
            "SELECT name, fields FROM elf_structures WHERE elf_hash=?", (elf_hash,)
        )
        return {r[0]: json.loads(r[1]) for r in cur.fetchall()}

    def get_all_global_vars(self, elf_hash: str) -> dict:
        cur = self._conn.execute(
            "SELECT name, var_type FROM elf_global_vars WHERE elf_hash=?", (elf_hash,)
        )
        return dict(cur.fetchall())

    def get_elf_stats(self, elf_hash: str) -> dict:
        sym_count = self._conn.execute(
            "SELECT COUNT(*) FROM elf_symbols WHERE elf_hash=?", (elf_hash,)
        ).fetchone()[0]
        func_count = self._conn.execute(
            "SELECT COUNT(*) FROM elf_functions WHERE elf_hash=?", (elf_hash,)
        ).fetchone()[0]
        obj_count = self._conn.execute(
            "SELECT COUNT(*) FROM elf_symbols"
            " WHERE elf_hash=? AND sym_type='STT_OBJECT'", (elf_hash,)
        ).fetchone()[0]
        backend = self._conn.execute(
            "SELECT parser_backend FROM elf_index WHERE elf_hash=?", (elf_hash,)
        ).fetchone()
        parser_backend = backend[0] if backend else "unknown"
        return {
            "total_symbols": sym_count,
            "functions": func_count,
            "objects": obj_count,
            "parser_backend": parser_backend
        }

    def delete_elf(self, elf_hash: str):
        with self._conn:
            for table in ("elf_symbols", "elf_functions", "elf_structures",
                          "elf_global_vars", "elf_index"):
                self._conn.execute(
                    f"DELETE FROM {table} WHERE elf_hash=?", (elf_hash,)
                )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _history_chain_head(self) -> str:
        """The entry_hmac of the most-recently-inserted history row ('' if none)."""
        cur = self._conn.execute(
            "SELECT entry_hmac FROM history ORDER BY id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return (row[0] or "") if row else ""

    def add_history_entry(self, description: str,
                          model_name: str = "", username: str = "", release_id: Optional[int] = None):
        # NC-3: obfuscate the description at rest and extend the HMAC hash-chain.
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        stored_desc = _obfuscate_history(description)
        with self._conn:
            prev = self._history_chain_head()
            entry_hmac = _history_row_hmac(prev, ts, username, model_name,
                                           stored_desc, release_id)
            self._conn.execute(
                "INSERT INTO history (timestamp, username, model_name, description,"
                " release_id, entry_hmac) VALUES (?,?,?,?,?,?)",
                (ts, username, model_name, stored_desc, release_id, entry_hmac)
            )

    def get_history(self, release_id: Optional[int] = None) -> list:
        if release_id is not None:
            cur = self._conn.execute(
                "SELECT timestamp, username, model_name, description"
                " FROM history WHERE release_id=? ORDER BY id",
                (release_id,)
            )
        else:
            cur = self._conn.execute(
                "SELECT timestamp, username, model_name, description"
                " FROM history WHERE release_id IS NULL ORDER BY id"
            )
        return [
            {"timestamp": r[0], "user": r[1], "model": r[2],
             "description": _deobfuscate_history(r[3])}
            for r in cur.fetchall()
        ]

    def copy_release_history(self, src_release_id: int, dst_release_id: int):
        # Clone the (already-obfuscated) descriptions verbatim but re-chain each
        # cloned row so the global hash-chain stays valid past the new inserts.
        with self._conn:
            src = self._conn.execute(
                "SELECT timestamp, username, model_name, description"
                " FROM history WHERE release_id=? ORDER BY id",
                (src_release_id,)
            ).fetchall()
            for ts, user, model, stored_desc in src:
                prev = self._history_chain_head()
                entry_hmac = _history_row_hmac(prev, ts, user, model,
                                               stored_desc, dst_release_id)
                self._conn.execute(
                    "INSERT INTO history (timestamp, username, model_name, description,"
                    " release_id, entry_hmac) VALUES (?,?,?,?,?,?)",
                    (ts, user, model, stored_desc, dst_release_id, entry_hmac)
                )

    def verify_history_chain(self) -> bool:
        """Recompute the append-only HMAC chain over ALL history rows (id order)
        and return True iff every stored entry_hmac matches — i.e. no row has
        been edited, deleted, inserted or reordered outside the app. Rows that
        predate the chain (legacy NULL entry_hmac) are skipped, not failed."""
        cur = self._conn.execute(
            "SELECT timestamp, username, model_name, description, release_id, entry_hmac"
            " FROM history ORDER BY id"
        )
        prev = ""
        for ts, user, model, stored_desc, rel_id, stored_hmac in cur.fetchall():
            if stored_hmac is not None:  # skip legacy rows, but still advance the head
                expected = _history_row_hmac(prev, ts, user, model, stored_desc, rel_id)
                if not hmac.compare_digest(expected, stored_hmac):
                    return False
            prev = stored_hmac or ""     # matches _history_chain_head() NULL->'' coalescing
        return True
