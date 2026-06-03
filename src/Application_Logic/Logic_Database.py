"""
Project Database
================
SQLite-backed storage for a single .arch project file.
All project state lives here: layout, models, releases, ELF data, history.
"""
import sqlite3
import os
import json
import hashlib
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

DB_SCHEMA_VERSION = 1

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
})

# project_meta keys excluded from the digest: the integrity value itself (would be
# self-referential) and volatile bookkeeping keys.
_INTEGRITY_EXCLUDED_META = frozenset({
    "integrity_hmac",
    "schema_version",
    "last_exported_elf_hash",
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
        self._conn.execute(f"PRAGMA journal_mode={_JOURNAL_MODE}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_schema()

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
        with self._conn:
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
                    description TEXT NOT NULL
                );
            """)
            cur = self._conn.execute(
                "SELECT value FROM project_meta WHERE key='schema_version'"
            )
            if not cur.fetchone():
                self._conn.execute(
                    "INSERT INTO project_meta (key, value) VALUES ('schema_version', ?)",
                    (str(DB_SCHEMA_VERSION),)
                )

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
            # Order by every column so the digest is independent of physical
            # row order / rowid churn.
            order = ", ".join(f'"{c}"' for c in cols)
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

    def delete_release_record(self, release_id: int):
        with self._conn:
            self._conn.execute("DELETE FROM releases WHERE id=?", (release_id,))

    def get_release_rows(self, release_id: int) -> list:
        cur = self._conn.execute(
            "SELECT row_data FROM release_rows"
            " WHERE release_id=? ORDER BY row_index",
            (release_id,)
        )
        return [json.loads(r[0]) for r in cur.fetchall()]

    def save_release_rows(self, release_id: int, rows: list):
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

    def save_release_column_metadata(self, release_id: int, metadata: dict):
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

    def save_release_results(self, release_id: int, results: dict):
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

    def register_elf(self, elf_hash: str, elf_path: str):
        ts = datetime.datetime.now().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO elf_index (elf_hash, elf_path, import_timestamp)"
                " VALUES (?,?,?)",
                (elf_hash, elf_path or "", ts)
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
        return {"total_symbols": sym_count, "functions": func_count, "objects": obj_count}

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

    def add_history_entry(self, description: str,
                          model_name: str = "", username: str = ""):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO history (timestamp, username, model_name, description)"
                " VALUES (?,?,?,?)",
                (ts, username, model_name, description)
            )

    def get_history(self) -> list:
        cur = self._conn.execute(
            "SELECT timestamp, username, model_name, description"
            " FROM history ORDER BY id"
        )
        return [
            {"timestamp": r[0], "user": r[1], "model": r[2], "description": r[3]}
            for r in cur.fetchall()
        ]
