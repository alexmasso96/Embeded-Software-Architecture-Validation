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
import gzip
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


def _decode_visible(v):
    """Column visibility: 2→None (Auto), 1→True (Show), 0→False (Hide)."""
    if v == 2:
        return None
    return bool(v)

# Set ARCH_PERF_LOG=1 to enable timing logs for hot DB paths
_PERF_LOG = os.environ.get("ARCH_PERF_LOG", "0") == "1"
_perf_logger = logging.getLogger("arch.perf")

# Module logger (used by open()/_apply_journal_mode — these messages surface in the
# New-Project loading window). Was previously referenced but never defined; the
# branches that used it (network-drive fallbacks) just never ran in dev/tests.
logger = logging.getLogger(__name__)


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

DB_SCHEMA_VERSION = 4

# Category-E project_meta keys (free-text settings, never queried by value) that
# are encrypted at rest when a block cipher is attached. Structural / pre-cipher
# keys (schema_version, enc_*, master_password_hash, activity_status) are
# deliberately excluded — they must be readable before the cipher exists.
ENCRYPTED_META_KEYS = frozenset({
    "ai_prompt", "ai_rules_md", "mind_map_prompt", "mind_map_rules",
    "chat_rules", "ai_requirements_context",
    "inject_build_command", "inject_build_cwd",
})

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


class ProjectDatabase:

    def __init__(self):
        self.db_path: Optional[str] = None
        self._conn: Optional[sqlite3.Connection] = None
        # View-Only sessions set this; a hard SQLite-level backstop (PRAGMA
        # query_only) plus skip-guards on the KV writers so a viewer can never
        # mutate the shared file even via an un-gated code path.
        self.read_only: bool = False
        # Per-block content cipher (Logic_Block_Crypto.BlockCipher) or None.
        # None ⇒ plaintext project / test-bypass / the unit-test suite, where the
        # _enc/_dec helpers are identity. Set via set_block_cipher() right after
        # open(), BEFORE anything reads encrypted columns (registry loads, workers).
        self._cipher = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def open(self, db_path: str, create_schema: bool = True, apply_journal: bool = True):
        """Open the project DB.

        `create_schema`/`apply_journal` default True for the primary connection.
        A secondary connection to an already-open file (e.g. the Code Map worker's
        own connection) passes both False: the journal mode is a persistent property
        of the file and the schema already exists, so re-running them would only take
        an unnecessary write lock and contend with the primary connection."""
        if self._conn:
            self._conn.close()
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if apply_journal:
            self.journal_mode = self._apply_journal_mode(db_path)
            logger.info(f"Journal mode: {self.journal_mode}")
        else:
            try:
                self.journal_mode = (self._conn.execute("PRAGMA journal_mode").fetchone()[0] or "").upper()
            except Exception:
                self.journal_mode = ""
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        if create_schema:
            logger.info("Creating/validating project database schema…")
            self._create_schema()

    def _apply_journal_mode(self, db_path: str) -> str:
        """Finding F: pick a safe SQLite journal mode for the project's location.
        WAL on local disks; DELETE on network/UNC drives (WAL corrupts there).
        Honors the ARCH_SQLITE_JOURNAL_MODE override."""
        logger.info("Testing WAL/journal mode for this storage location…")
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

    def set_read_only(self, flag: bool):
        """Toggle the View-Only backstop. `PRAGMA query_only=ON` makes the SQLite
        connection refuse every write at the engine level — a hard guarantee that a
        viewer can't corrupt the shared file regardless of which code path runs. The
        `read_only` flag also lets the lightweight KV writers skip silently so normal
        read-only navigation doesn't raise."""
        self.read_only = bool(flag)
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA query_only=%s" % ("ON" if flag else "OFF"))
            except Exception:
                pass

    def execute(self, sql: str, params=()):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params):
        return self._conn.executemany(sql, params)

    # ------------------------------------------------------------------
    # Per-block content encryption (see Logic_Block_Crypto)
    # ------------------------------------------------------------------
    def set_block_cipher(self, cipher) -> None:
        """Attach (or clear, with None) the per-category content cipher. Must be
        called before any read of an encrypted column. Plaintext/test projects
        leave this None → the _enc/_dec helpers below are pure identity."""
        self._cipher = cipher

    def _enc_blob(self, category: str, b):
        return self._cipher.encrypt(category, b) if (self._cipher and b) else b

    def _dec_blob(self, category: str, b):
        return self._cipher.decrypt(category, b) if (self._cipher and b) else b

    def _enc_text(self, category: str, s):
        return self._cipher.encrypt_text(category, s) if (self._cipher and s) else s

    def _dec_text(self, category: str, s):
        return self._cipher.decrypt_text(category, s) if (self._cipher and s) else s

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

                -- #2E: source code imported INTO the project, keyed by release.
                -- content_gzip = gzip(utf-8 bytes); read lazily one file at a time.
                -- Excluded from the integrity digest (large, recomputable cache).
                CREATE TABLE IF NOT EXISTS release_source_files (
                    release_id   INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
                    rel_path     TEXT    NOT NULL,
                    content_gzip BLOB    NOT NULL,
                    size         INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT    NOT NULL DEFAULT '',
                    ext          TEXT,
                    PRIMARY KEY (release_id, rel_path)
                );
                CREATE INDEX IF NOT EXISTS idx_release_source_files
                    ON release_source_files(release_id);

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

                -- #2E Phase 2: per-(model, release) mind maps + code maps so each
                -- release keeps its own (supports intermediary releases). release_id
                -- 0 = "no specific release" (project without releases / pre-release
                -- initial map). Derived cache → excluded from the integrity digest.
                -- model_id FK CASCADEs on model delete; release deletes are cleaned
                -- explicitly in delete_release_record (release_id 0 has no FK row).
                CREATE TABLE IF NOT EXISTS ai_release_maps (
                    model_id        INTEGER NOT NULL
                                        REFERENCES architecture_models(id) ON DELETE CASCADE,
                    release_id      INTEGER NOT NULL DEFAULT 0,
                    mindmap_json    TEXT,
                    code_map_json   TEXT,
                    source_hash     TEXT,
                    diff_hash       TEXT,
                    builder_version TEXT,
                    char_count      INTEGER DEFAULT 0,
                    updated_at      TEXT,
                    PRIMARY KEY (model_id, release_id)
                );

                -- Source-Level Test Code Injection -----------------------
                -- A test project bundles imported helper files plus a set of
                -- injection hooks that splice snippets into production source.
                CREATE TABLE IF NOT EXISTS test_projects (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT    NOT NULL,
                    created_at TEXT    NOT NULL DEFAULT ''
                );

                -- Imported .c/.h helper files (gzip-compressed; read lazily).
                CREATE TABLE IF NOT EXISTS test_project_files (
                    test_project_id INTEGER NOT NULL
                                        REFERENCES test_projects(id) ON DELETE CASCADE,
                    rel_path        TEXT    NOT NULL,
                    content_gzip    BLOB    NOT NULL,
                    size            INTEGER NOT NULL DEFAULT 0,
                    ext             TEXT,
                    PRIMARY KEY (test_project_id, rel_path)
                );
                CREATE INDEX IF NOT EXISTS idx_test_project_files
                    ON test_project_files(test_project_id);

                -- Injection hooks: anchor lines locate the splice point, the
                -- fuzzy resolver re-finds it as the source shifts underneath.
                CREATE TABLE IF NOT EXISTS test_code_injections (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_project_id INTEGER NOT NULL
                                        REFERENCES test_projects(id) ON DELETE CASCADE,
                    src_file_path   TEXT    NOT NULL,
                    function_name   TEXT    NOT NULL DEFAULT '',
                    line_above_code TEXT    NOT NULL DEFAULT '',
                    line_below_code TEXT    NOT NULL DEFAULT '',
                    injected_code   TEXT    NOT NULL DEFAULT '',
                    offset_lines    INTEGER NOT NULL DEFAULT 0,
                    created_at      TEXT    NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_test_code_injections
                    ON test_code_injections(test_project_id);
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

            # #2E Phase 2: migrate legacy per-model maps (ai_model_mindmaps) into the
            # per-(model, release) table, keyed to the currently-active release (or 0
            # when the project has no active release). Idempotent: only runs when the
            # new table is still empty, so re-opening never double-migrates.
            try:
                has_new = self._conn.execute(
                    "SELECT COUNT(*) FROM ai_release_maps").fetchone()[0]
                old_rows = self._conn.execute(
                    "SELECT model_id, mindmap_json, source_hash, diff_hash, "
                    "builder_version, char_count, updated_at, code_map_json "
                    "FROM ai_model_mindmaps").fetchall()
                if has_new == 0 and old_rows:
                    arow = self._conn.execute(
                        "SELECT id FROM releases WHERE is_active=1 LIMIT 1").fetchone()
                    active_rid = arow[0] if arow else 0
                    for r in old_rows:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO ai_release_maps "
                            "(model_id, release_id, mindmap_json, code_map_json, "
                            " source_hash, diff_hash, builder_version, char_count, updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (r[0], active_rid, r[1], r[7], r[2], r[3], r[4], r[5], r[6]))
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
        if not row:
            return default
        if key in ENCRYPTED_META_KEYS:
            return self._dec_text("E", row[0])
        return row[0]

    def set_meta(self, key: str, value):
        if self.read_only:
            return  # View-Only: silently ignore incidental metadata writes.
        stored = str(value) if value is not None else None
        if stored is not None and key in ENCRYPTED_META_KEYS:
            stored = self._enc_text("E", stored)
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
                (key, stored)
            )

    def get_all_meta(self) -> dict:
        cur = self._conn.execute("SELECT key, value FROM project_meta")
        return {r[0]: (self._dec_text("E", r[1]) if r[0] in ENCRYPTED_META_KEYS else r[1])
                for r in cur.fetchall()}

    # ------------------------------------------------------------------
    # Multi-user activity broadcast (editor writes; View-Only sessions poll)
    # ------------------------------------------------------------------
    _ACTIVITY_KEY = "activity_status"

    def set_activity(self, op: str, state: str, detail: str = ""):
        """Editor broadcasts a long-running AI op ('mindmap'/'codemap'/'diff'/…)
        so other sessions can surface it. state is 'in_progress' or 'idle'. Goes
        through set_meta (skipped for read-only viewers, which never generate)."""
        import json, datetime
        from Application_Logic.Logic_File_Locking import FileLockManager
        payload = {
            "op": op, "state": state, "detail": detail,
            "user": FileLockManager.get_username(),
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        self.set_meta(self._ACTIVITY_KEY, json.dumps(payload))

    def get_activity(self):
        """Returns the current activity dict (fresh read so a poller sees the
        latest committed value), or None."""
        import json
        raw = self.get_meta(self._ACTIVITY_KEY)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # AI Part 2 — mind map (per architecture model)
    # ------------------------------------------------------------------

    def _resolve_release_id(self, release_id) -> int:
        """#2E: map None → the active release id, falling back to 0 ('no specific
        release') for projects without an active release. Explicit ids pass through
        so background workers can pin a stable release."""
        if release_id is not None:
            return release_id
        rid = self.get_active_release_id()
        return rid if rid is not None else 0

    def get_model_mindmap(self, model_id: int, release_id=None) -> Optional[dict]:
        """Return the parsed CompactMindMap dict for a model+release, or None."""
        rid = self._resolve_release_id(release_id)
        cur = self._conn.execute(
            "SELECT mindmap_json FROM ai_release_maps WHERE model_id=? AND release_id=?",
            (model_id, rid))
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(self._dec_text("C", row[0]))
        except (ValueError, TypeError):
            return None

    def get_model_ids_with_mindmap(self, release_id=None) -> set:
        """model_ids that have a non-empty mind map for the given (or active)
        release — a cheap existence check for the indexed ✓/○ markers."""
        rid = self._resolve_release_id(release_id)
        cur = self._conn.execute(
            "SELECT model_id FROM ai_release_maps "
            "WHERE release_id=? AND mindmap_json IS NOT NULL AND mindmap_json != ''",
            (rid,))
        return {r[0] for r in cur.fetchall()}

    def get_model_mindmap_meta(self, model_id: int, release_id=None) -> Optional[dict]:
        """Return provenance (source_hash/diff_hash/builder_version/char_count/
        updated_at) WITHOUT loading the large mindmap_json blob, or None."""
        rid = self._resolve_release_id(release_id)
        cur = self._conn.execute(
            "SELECT source_hash, diff_hash, builder_version, char_count, updated_at "
            "FROM ai_release_maps WHERE model_id=? AND release_id=?", (model_id, rid))
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
                           updated_at: str = "", code_map_json: Optional[str] = None,
                           release_id=None) -> None:
        """Insert or replace the mind map row for a model+release. Preserves any
        existing code_map_json when the caller doesn't supply one (and vice-versa)."""
        rid = self._resolve_release_id(release_id)
        with self._conn:
            existing = self._conn.execute(
                "SELECT code_map_json FROM ai_release_maps "
                "WHERE model_id=? AND release_id=?", (model_id, rid)).fetchone()
            # Decrypt the preserved existing value so the single _enc_text below
            # encrypts exactly once (never double-encrypts retained ciphertext).
            existing_cm = self._dec_text("C", existing[0]) if existing else None
            cm = code_map_json if code_map_json is not None else existing_cm
            self._conn.execute(
                "INSERT OR REPLACE INTO ai_release_maps "
                "(model_id, release_id, mindmap_json, source_hash, diff_hash, "
                " builder_version, char_count, updated_at, code_map_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (model_id, rid, self._enc_text("C", mindmap_json), source_hash,
                 diff_hash, builder_version, int(char_count or 0), updated_at,
                 self._enc_text("C", cm)))

    def get_model_code_map(self, model_id: int, release_id=None) -> Optional[dict]:
        """Return the parsed CodeMap dict for a model+release, or None."""
        rid = self._resolve_release_id(release_id)
        cur = self._conn.execute(
            "SELECT code_map_json FROM ai_release_maps WHERE model_id=? AND release_id=?",
            (model_id, rid))
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(self._dec_text("C", row[0]))
        except (ValueError, TypeError):
            return None

    def save_model_code_map(self, model_id: int, code_map_json: str,
                            release_id=None) -> None:
        """Save or update the CodeMap JSON for a model+release (keeps any mind map)."""
        rid = self._resolve_release_id(release_id)
        enc_cm = self._enc_text("C", code_map_json)
        with self._conn:
            cur = self._conn.execute(
                "SELECT 1 FROM ai_release_maps WHERE model_id=? AND release_id=?",
                (model_id, rid))
            if cur.fetchone():
                self._conn.execute(
                    "UPDATE ai_release_maps SET code_map_json=? "
                    "WHERE model_id=? AND release_id=?", (enc_cm, model_id, rid))
            else:
                ts = datetime.datetime.now().isoformat()
                self._conn.execute(
                    "INSERT INTO ai_release_maps "
                    "(model_id, release_id, mindmap_json, updated_at, code_map_json) "
                    "VALUES (?, ?, ?, ?, ?)", (model_id, rid, "", ts, enc_cm))

    def delete_model_mindmap(self, model_id: int, release_id=None) -> None:
        """Remove a model's map row(s) AND its code-diff rows (the diff table is not
        an FK, so its cascade is explicit). With release_id=None this clears ALL
        releases for the model (used on regenerate/model reset); pass a release_id to
        drop just that release's map."""
        with self._conn:
            if release_id is None:
                self._conn.execute(
                    "DELETE FROM ai_release_maps WHERE model_id=?", (model_id,))
            else:
                self._conn.execute(
                    "DELETE FROM ai_release_maps WHERE model_id=? AND release_id=?",
                    (model_id, release_id))
            self._conn.execute(
                "DELETE FROM ai_code_diffs WHERE model_id=?", (model_id,))

    def has_model_mindmap(self, model_id: int, release_id=None) -> bool:
        rid = self._resolve_release_id(release_id)
        cur = self._conn.execute(
            "SELECT 1 FROM ai_release_maps WHERE model_id=? AND release_id=? LIMIT 1",
            (model_id, rid))
        return cur.fetchone() is not None

    def set_model_diff_hash(self, model_id: int, diff_hash: str, release_id=None) -> None:
        """Record the latest computed diff hash for a model+release (used by the
        Change Log to find its diff rows) without disturbing the mind/code map."""
        rid = self._resolve_release_id(release_id)
        with self._conn:
            cur = self._conn.execute(
                "SELECT 1 FROM ai_release_maps WHERE model_id=? AND release_id=?",
                (model_id, rid))
            if cur.fetchone():
                self._conn.execute(
                    "UPDATE ai_release_maps SET diff_hash=? WHERE model_id=? AND release_id=?",
                    (diff_hash, model_id, rid))
            else:
                ts = datetime.datetime.now().isoformat()
                self._conn.execute(
                    "INSERT INTO ai_release_maps (model_id, release_id, diff_hash, updated_at) "
                    "VALUES (?, ?, ?, ?)", (model_id, rid, diff_hash, ts))

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
                  d.get("status", ""), self._enc_text("C", d.get("unified_diff", "")))
                 for d in diffs],
            )

    def get_code_diffs(self, model_id: int, diff_hash: str) -> list:
        cur = self._conn.execute(
            "SELECT file_path, status, unified_diff FROM ai_code_diffs "
            "WHERE model_id=? AND diff_hash=? ORDER BY file_path",
            (model_id, diff_hash))
        return [{"file_path": r[0], "status": r[1],
                 "unified_diff": self._dec_text("C", r[2])}
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
    # Column layout
    # ------------------------------------------------------------------

    def save_column_layout(self, layout: list):
        # Visibility is tri-state: True=Show (1), False=Hide (0), None=Auto (2).
        # "Auto" is used by Init/Cyclic columns whose effective visibility is
        # computed from row content at render time.
        with self._conn:
            self._conn.execute("DELETE FROM column_layout")
            rows = []
            for i, col in enumerate(layout):
                name = col[0]
                col_type = col[1]
                vis = col[2] if len(col) > 2 else True
                visible = 2 if vis is None else (1 if vis else 0)
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
        return [(r[0], r[1], _decode_visible(r[2]), r[3]) for r in cur.fetchall()]

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
        if self.read_only:
            return  # View-Only: silently ignore incidental UI-state writes.
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
            return [json.loads(self._dec_text("A", r[0])) for r in cur.fetchall()]

    def get_row_count(self, model_id: int) -> int:
        """Row count for a model without deserialising any row payloads."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM architecture_rows WHERE model_id=?", (model_id,)
        )
        return int(cur.fetchone()[0])

    def get_model_row(self, model_id: int, row_index: int) -> dict:
        cur = self._conn.execute(
            "SELECT row_data FROM architecture_rows"
            " WHERE model_id=? AND row_index=?",
            (model_id, row_index)
        )
        row = cur.fetchone()
        return json.loads(self._dec_text("A", row[0])) if row else {}

    def save_model_rows(self, model_id: int, rows: list):
        with _timed("save_model_rows", model_id=model_id, rows=len(rows)):
            with self._conn:
                self._conn.execute(
                    "DELETE FROM architecture_rows WHERE model_id=?", (model_id,)
                )
                self._conn.executemany(
                    "INSERT INTO architecture_rows (model_id, row_index, row_data) VALUES (?,?,?)",
                    [(model_id, i, self._enc_text("A", json.dumps(row)))
                     for i, row in enumerate(rows)]
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
                    (model_id, row_index, self._enc_text("A", json.dumps(row_data)))
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
                    [(model_id, idx, self._enc_text("A", json.dumps(data)))
                     for idx, data in rows.items()]
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
        return {r[0]: json.loads(self._dec_text("A", r[1])) if r[1] else None
                for r in cur.fetchall()}

    def save_model_metadata(self, model_id: int, metadata: dict):
        with self._conn:
            self._conn.execute("DELETE FROM model_metadata WHERE model_id=?", (model_id,))
            if metadata:
                self._conn.executemany(
                    "INSERT INTO model_metadata (model_id, key, value) VALUES (?,?,?)",
                    [(model_id, k, self._enc_text("A", json.dumps(v)))
                     for k, v in metadata.items()]
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
            # #2E: ai_release_maps has no FK on release_id (the 0 sentinel has no
            # matching row), so clean its per-release maps explicitly. Source blobs
            # and release_rows cascade via their FKs.
            self._conn.execute(
                "DELETE FROM ai_release_maps WHERE release_id=?", (release_id,))
            self._conn.execute("DELETE FROM releases WHERE id=?", (release_id,))

    # ------------------------------------------------------------------
    # #2E — release-keyed source code store (gzip blobs, lazy reads)
    # ------------------------------------------------------------------

    def save_release_source_files(self, release_id: int, files, progress=None,
                                  batch: int = 200) -> int:
        """Replace the stored source for a release with ``files``.

        ``files`` is an iterable of ``(rel_path, text)`` pairs. Each file is
        gzip-compressed and inserted in batches so peak RAM stays at ~one batch.
        ``progress(rel_path, idx, total_or_None)`` is called per file for the
        loading window's per-file log. Returns the number of files stored.
        """
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_source_files WHERE release_id=?", (release_id,))
            rows = []
            count = 0
            for rel_path, text in files:
                data = (text or "").encode("utf-8", errors="replace")
                blob = self._enc_blob("B", gzip.compress(data))
                content_hash = hashlib.sha256(data).hexdigest()
                ext = os.path.splitext(rel_path)[1].lower()
                rows.append((release_id, rel_path, blob, len(data), content_hash, ext))
                count += 1
                if progress is not None:
                    progress(rel_path, count, None)
                if len(rows) >= batch:
                    self._conn.executemany(
                        "INSERT OR REPLACE INTO release_source_files "
                        "(release_id, rel_path, content_gzip, size, content_hash, ext) "
                        "VALUES (?,?,?,?,?,?)", rows)
                    rows = []
            if rows:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO release_source_files "
                    "(release_id, rel_path, content_gzip, size, content_hash, ext) "
                    "VALUES (?,?,?,?,?,?)", rows)
        return count

    def list_release_source_files(self, release_id: int) -> list:
        """Return [{rel_path, size, content_hash, ext}] WITHOUT decompressing —
        a cheap listing for build_index / diff stat-gating."""
        cur = self._conn.execute(
            "SELECT rel_path, size, content_hash, ext FROM release_source_files "
            "WHERE release_id=? ORDER BY rel_path", (release_id,))
        return [{"rel_path": r[0], "size": r[1], "content_hash": r[2], "ext": r[3]}
                for r in cur.fetchall()]

    def read_release_source_file(self, release_id: int, rel_path: str) -> Optional[str]:
        """Decompress and return a SINGLE stored file's text, or None if absent."""
        cur = self._conn.execute(
            "SELECT content_gzip FROM release_source_files "
            "WHERE release_id=? AND rel_path=?", (release_id, rel_path))
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        try:
            return gzip.decompress(self._dec_blob("B", row[0])).decode("utf-8", errors="replace")
        except (OSError, EOFError):
            return None

    def has_release_source(self, release_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM release_source_files WHERE release_id=? LIMIT 1", (release_id,))
        return cur.fetchone() is not None

    def get_release_source_total_size(self, release_id: int) -> int:
        """Sum of uncompressed sizes (for the UI's stored-size display)."""
        cur = self._conn.execute(
            "SELECT COALESCE(SUM(size), 0), COUNT(*) FROM release_source_files "
            "WHERE release_id=?", (release_id,))
        row = cur.fetchone()
        return int(row[0] or 0)

    def get_release_ids_with_source(self) -> set:
        """release_ids that have at least one stored source file (for ✓/○ markers)."""
        cur = self._conn.execute(
            "SELECT DISTINCT release_id FROM release_source_files")
        return {r[0] for r in cur.fetchall()}

    def delete_release_source(self, release_id: int) -> None:
        """#2E Unload: drop ONLY the source blobs for a release; mind/code maps stay."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_source_files WHERE release_id=?", (release_id,))

    # ------------------------------------------------------------------
    # Source-Level Test Code Injection — test projects, helper files, hooks
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    # -- test projects --------------------------------------------------
    def create_test_project(self, name: str) -> int:
        """Create a new test project and return its id."""
        ts = self._now_iso()
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO test_projects (name, created_at) VALUES (?, ?)",
                (name, ts))
            return int(cur.lastrowid)

    def list_test_projects(self) -> list:
        """All test projects (newest first) with their file/injection counts."""
        cur = self._conn.execute(
            "SELECT p.id, p.name, p.created_at, "
            "  (SELECT COUNT(*) FROM test_project_files f WHERE f.test_project_id=p.id), "
            "  (SELECT COUNT(*) FROM test_code_injections i WHERE i.test_project_id=p.id) "
            "FROM test_projects p ORDER BY p.id DESC")
        return [{"id": r[0], "name": r[1], "created_at": r[2],
                 "file_count": r[3], "injection_count": r[4]}
                for r in cur.fetchall()]

    def rename_test_project(self, test_project_id: int, name: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE test_projects SET name=? WHERE id=?", (name, test_project_id))

    def delete_test_project(self, test_project_id: int) -> None:
        """Delete a test project; ON DELETE CASCADE drops its files + injections."""
        with self._conn:
            self._conn.execute(
                "DELETE FROM test_projects WHERE id=?", (test_project_id,))

    # -- test helper files (gzip blobs) ---------------------------------
    def import_test_project_files(self, test_project_id: int, files,
                                  progress=None, batch: int = 200) -> int:
        """Import ``(rel_path, text)`` helper files, gzip-compressing each.

        Inserts/replaces in batches so peak RAM stays at ~one batch. Returns the
        number of files stored. Existing files with the same rel_path are
        overwritten (re-import).
        """
        rows = []
        count = 0
        with self._conn:
            for rel_path, text in files:
                data = (text or "").encode("utf-8", errors="replace")
                blob = self._enc_blob("D", gzip.compress(data))
                ext = os.path.splitext(rel_path)[1].lower()
                rows.append((test_project_id, rel_path, blob, len(data), ext))
                count += 1
                if progress is not None:
                    progress(rel_path, count, None)
                if len(rows) >= batch:
                    self._conn.executemany(
                        "INSERT OR REPLACE INTO test_project_files "
                        "(test_project_id, rel_path, content_gzip, size, ext) "
                        "VALUES (?,?,?,?,?)", rows)
                    rows = []
            if rows:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO test_project_files "
                    "(test_project_id, rel_path, content_gzip, size, ext) "
                    "VALUES (?,?,?,?,?)", rows)
        return count

    def list_test_project_files(self, test_project_id: int) -> list:
        """[{rel_path, size, ext}] WITHOUT decompressing (cheap listing)."""
        cur = self._conn.execute(
            "SELECT rel_path, size, ext FROM test_project_files "
            "WHERE test_project_id=? ORDER BY rel_path", (test_project_id,))
        return [{"rel_path": r[0], "size": r[1], "ext": r[2]}
                for r in cur.fetchall()]

    def read_test_project_file(self, test_project_id: int,
                               rel_path: str) -> Optional[str]:
        """Decompress and return a single helper file's text, or None."""
        cur = self._conn.execute(
            "SELECT content_gzip FROM test_project_files "
            "WHERE test_project_id=? AND rel_path=?", (test_project_id, rel_path))
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        try:
            return gzip.decompress(self._dec_blob("D", row[0])).decode("utf-8", errors="replace")
        except (OSError, EOFError):
            return None

    def delete_test_project_file(self, test_project_id: int, rel_path: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM test_project_files "
                "WHERE test_project_id=? AND rel_path=?", (test_project_id, rel_path))

    # -- injection hooks ------------------------------------------------
    def add_injection(self, test_project_id: int, src_file_path: str,
                      function_name: str = "", line_above_code: str = "",
                      line_below_code: str = "", injected_code: str = "",
                      offset_lines: int = 0) -> int:
        """Insert a new injection hook and return its id."""
        ts = self._now_iso()
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO test_code_injections "
                "(test_project_id, src_file_path, function_name, line_above_code, "
                " line_below_code, injected_code, offset_lines, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (test_project_id, src_file_path, function_name,
                 self._enc_text("D", line_above_code),
                 self._enc_text("D", line_below_code),
                 self._enc_text("D", injected_code), int(offset_lines), ts))
            return int(cur.lastrowid)

    def update_injection(self, injection_id: int, **fields) -> None:
        """Update any subset of {function_name, src_file_path, line_above_code,
        line_below_code, injected_code, offset_lines} on an injection row."""
        allowed = {"function_name", "src_file_path", "line_above_code",
                   "line_below_code", "injected_code", "offset_lines"}
        encrypted = {"line_above_code", "line_below_code", "injected_code"}
        sets, params = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                if k == "offset_lines":
                    params.append(int(v))
                elif k in encrypted:
                    params.append(self._enc_text("D", v))
                else:
                    params.append(v)
        if not sets:
            return
        params.append(injection_id)
        with self._conn:
            self._conn.execute(
                f"UPDATE test_code_injections SET {', '.join(sets)} WHERE id=?",
                params)

    def update_injection_anchors(self, injection_id: int, line_above_code: str,
                                 line_below_code: str,
                                 offset_lines: Optional[int] = None) -> None:
        """Re-anchor an injection after the surrounding code shifted."""
        above = self._enc_text("D", line_above_code)
        below = self._enc_text("D", line_below_code)
        if offset_lines is None:
            with self._conn:
                self._conn.execute(
                    "UPDATE test_code_injections "
                    "SET line_above_code=?, line_below_code=? WHERE id=?",
                    (above, below, injection_id))
        else:
            with self._conn:
                self._conn.execute(
                    "UPDATE test_code_injections "
                    "SET line_above_code=?, line_below_code=?, offset_lines=? "
                    "WHERE id=?",
                    (above, below, int(offset_lines), injection_id))

    def remove_injection(self, injection_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM test_code_injections WHERE id=?", (injection_id,))

    def get_injection(self, injection_id: int) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT id, test_project_id, src_file_path, function_name, "
            "line_above_code, line_below_code, injected_code, offset_lines, created_at "
            "FROM test_code_injections WHERE id=?", (injection_id,))
        row = cur.fetchone()
        return self._injection_dict(row) if row else None

    def list_injections(self, test_project_id: int,
                        src_file_path: Optional[str] = None) -> list:
        """All injection hooks for a test project, optionally filtered to one file."""
        if src_file_path is None:
            cur = self._conn.execute(
                "SELECT id, test_project_id, src_file_path, function_name, "
                "line_above_code, line_below_code, injected_code, offset_lines, created_at "
                "FROM test_code_injections WHERE test_project_id=? ORDER BY id",
                (test_project_id,))
        else:
            cur = self._conn.execute(
                "SELECT id, test_project_id, src_file_path, function_name, "
                "line_above_code, line_below_code, injected_code, offset_lines, created_at "
                "FROM test_code_injections WHERE test_project_id=? AND src_file_path=? "
                "ORDER BY id", (test_project_id, src_file_path))
        return [self._injection_dict(r) for r in cur.fetchall()]

    def _injection_dict(self, row) -> dict:
        return {
            "id": row[0],
            "test_project_id": row[1],
            "src_file_path": row[2],
            "function_name": row[3],
            "line_above_code": self._dec_text("D", row[4]),
            "line_below_code": self._dec_text("D", row[5]),
            "injected_code": self._dec_text("D", row[6]),
            "offset_lines": row[7],
            "created_at": row[8],
        }

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
        return [json.loads(self._dec_text("A", r[0])) for r in cur.fetchall()]

    def save_release_rows(self, release_id: int, rows: list, _allow_frozen: bool = False):
        self._guard_release_writable(release_id, _allow_frozen)
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_rows WHERE release_id=?", (release_id,)
            )
            self._conn.executemany(
                "INSERT INTO release_rows (release_id, row_index, row_data) VALUES (?,?,?)",
                [(release_id, i, self._enc_text("A", json.dumps(row)))
                 for i, row in enumerate(rows)]
            )

    def copy_release_rows(self, src_id: int, dst_id: int):
        rows = self.get_release_rows(src_id)
        self.save_release_rows(dst_id, rows)

    def get_release_column_metadata(self, release_id: int) -> dict:
        cur = self._conn.execute(
            "SELECT col_name, metadata FROM release_column_metadata WHERE release_id=?",
            (release_id,)
        )
        return {r[0]: json.loads(self._dec_text("A", r[1])) for r in cur.fetchall()}

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
                [(release_id, k, self._enc_text("A", json.dumps(v)))
                 for k, v in metadata.items()]
            )

    def get_release_results(self, release_id: int) -> dict:
        cur = self._conn.execute(
            "SELECT col_name, results FROM release_results WHERE release_id=?",
            (release_id,)
        )
        return {r[0]: json.loads(self._dec_text("A", r[1])) for r in cur.fetchall()}

    def save_release_results(self, release_id: int, results: dict,
                             _allow_frozen: bool = False):
        self._guard_release_writable(release_id, _allow_frozen)
        with self._conn:
            self._conn.execute(
                "DELETE FROM release_results WHERE release_id=?", (release_id,)
            )
            self._conn.executemany(
                "INSERT INTO release_results (release_id, col_name, results) VALUES (?,?,?)",
                [(release_id, k, self._enc_text("A", json.dumps(v)))
                 for k, v in results.items()]
            )

    def get_release_linked_column(self, release_id: int) -> Optional[str]:
        cur = self._conn.execute(
            "SELECT metadata FROM release_column_metadata"
            " WHERE release_id=? AND col_name='__linked_release_column__'",
            (release_id,)
        )
        row = cur.fetchone()
        if row:
            return json.loads(self._dec_text("A", row[0])).get("value")
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
                    (release_id, "__linked_release_column__",
                     self._enc_text("A", json.dumps({"value": col_name})))
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
        # Drop compiler-internal / assembler-label symbols (.L*, _*, __*) at the
        # single DB-insert chokepoint so the elf_functions table — what the Code Map
        # reads — is clean regardless of which parser backend or path produced it.
        from core.elf_parser import keep_function_name
        BATCH = 2000
        with self._conn:
            batch = []
            for function in functions:
                name = function.get("name", "") if isinstance(function, dict) else getattr(function, "name", "")
                if not keep_function_name(name):
                    continue
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
                      self._enc_text("A", json.dumps(f.get("parameters", []) if isinstance(f, dict) else f.parameters)),
                      self._enc_text("A", f.get("return_type") if isinstance(f, dict) else f.return_type))
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
                      self._enc_text("A", json.dumps(f.get("parameters", []) if isinstance(f, dict) else f.parameters)),
                      self._enc_text("A", f.get("return_type") if isinstance(f, dict) else f.return_type))
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
                    [(elf_hash, name, self._enc_text("A", json.dumps(fields)))
                     for name, fields in batch]
                )

    def bulk_insert_global_vars(self, elf_hash: str, global_vars: dict):
        BATCH = 2000
        items = list(global_vars.items())
        with self._conn:
            for i in range(0, len(items), BATCH):
                batch = items[i:i + BATCH]
                self._conn.executemany(
                    "INSERT INTO elf_global_vars (elf_hash, name, var_type) VALUES (?,?,?)",
                    [(elf_hash, name, self._enc_text("A", var_type))
                     for name, var_type in batch]
                )

    def update_function_params(self, elf_hash: str, name: str,
                               parameters: list, return_type=None):
        with self._conn:
            self._conn.execute(
                "UPDATE elf_functions SET parameters=?, return_type=?"
                " WHERE elf_hash=? AND name=?",
                (self._enc_text("A", json.dumps(parameters)),
                 self._enc_text("A", return_type), elf_hash, name)
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
            dec_params = self._dec_text("A", r[3])
            results.append({
                "name": r[0], "address": r[1], "size": r[2],
                "parameters": json.loads(dec_params) if dec_params else [],
                "return_type": self._dec_text("A", r[4])
            })
        results.sort(key=lambda f: f["name"] != name)
        return results

    def get_all_structures(self, elf_hash: str) -> dict:
        cur = self._conn.execute(
            "SELECT name, fields FROM elf_structures WHERE elf_hash=?", (elf_hash,)
        )
        return {r[0]: json.loads(self._dec_text("A", r[1])) for r in cur.fetchall()}

    def get_all_global_vars(self, elf_hash: str) -> dict:
        cur = self._conn.execute(
            "SELECT name, var_type FROM elf_global_vars WHERE elf_hash=?", (elf_hash,)
        )
        return {r[0]: self._dec_text("A", r[1]) for r in cur.fetchall()}

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
        # Encrypt under category A when a project cipher is attached; otherwise
        # fall back to the legacy app-key obfuscation so plaintext/legacy projects
        # still store an obfuscated description (and the test suite's cipher-less
        # fixtures keep their existing "enc:" behavior).
        stored_desc = (self._enc_text("A", description) if self._cipher
                       else _obfuscate_history(description))
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
             "description": self._read_history_desc(r[3])}
            for r in cur.fetchall()
        ]

    def _read_history_desc(self, stored: str) -> str:
        """Decode a stored description: category-A ciphertext (``fb1:``) via the
        project cipher, legacy app-key obfuscation (``enc:``) otherwise."""
        if self._cipher and isinstance(stored, str) and stored.startswith("fb1:"):
            return self._dec_text("A", stored)
        return _deobfuscate_history(stored)

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
