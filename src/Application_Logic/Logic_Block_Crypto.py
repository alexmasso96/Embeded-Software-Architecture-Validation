"""
Per-block (per-category) content encryption for the ``.arch`` project file.
=========================================================================

The ``.arch`` is a *plaintext* SQLite file on disk; only sensitive CONTENT
columns are encrypted, each under its own per-category key. This replaces the
old whole-file encryption (decrypt-to-temp on open, re-encrypt the whole file on
save) so open/save are fast and only the blocks actually accessed are decrypted —
structural columns (names, ids, hashes, addresses, timestamps, counts) stay
plaintext so indexes / symbol-matching keep working.

Key hierarchy
-------------
``password + per-project salt`` --PBKDF2-HMAC-SHA256(200k)--> 32-byte master key
``master key`` --HKDF-SHA256(info=<category label>)--> one 32-byte subkey per
category, wrapped in a Fernet. PBKDF2 runs ONCE (the deliberately-slow,
brute-force-resistant step); HKDF derivation of the six subkeys is ~microseconds,
so open stays fast while each category remains independently keyed.

On-blob markers
---------------
Encrypted values carry a marker so encrypted vs legacy-plaintext values are
distinguishable: this makes reads during migration safe (an unmarked legacy value
is returned untouched) and ``decrypt`` idempotent. BLOB columns get a leading
``\\x01`` byte; TEXT columns get a ``fb1:`` ascii prefix (Fernet tokens are
urlsafe-base64, so the result is valid SQLite TEXT).

Wrong-password / tamper detection reuses ``Logic_Crypto.PasswordInvalid`` (Fernet
authenticates its payload), so the canary check below drives the existing 401/403
mapping with no router changes.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .Logic_Crypto import PBKDF2_ITERS, PasswordInvalid

ENC_SCHEME = "per-block-v1"
SALT_LEN = 16

# Category labels — STABLE strings used as HKDF `info`. Never change once shipped
# (changing a label re-keys that category and orphans existing ciphertext).
CATEGORIES = {
    "A": "elf_table_history",
    "B": "source",
    "C": "app_generated",
    "D": "test",
    "E": "prefs",
    "F": "user_content",
}

_BLOB_MARKER = b"\x01"      # prefix on encrypted BLOB (bytes) columns
_TEXT_MARKER = "fb1:"       # prefix on encrypted TEXT (str) columns
_CANARY = "arch-canary-v1"  # known plaintext; encrypting it lets us verify the pw


class BlockCipher:
    """Holds one Fernet per category, derived from the master password.

    Immutable after construction (the per-category Fernet cache is populated
    eagerly), so a single instance is safe to share across worker threads.
    """

    def __init__(self, master_key: bytes):
        if len(master_key) != 32:
            raise ValueError("master_key must be 32 bytes")
        self._master_key = master_key
        self._fernets = {cat: Fernet(self._subkey(label))
                         for cat, label in CATEGORIES.items()}

    # -- construction -------------------------------------------------------
    @classmethod
    def from_password(cls, password: str, kdf_salt: bytes) -> "BlockCipher":
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=kdf_salt,
                         iterations=PBKDF2_ITERS)
        return cls(kdf.derive(password.encode("utf-8")))

    @staticmethod
    def new_salt() -> bytes:
        return os.urandom(SALT_LEN)

    def _subkey(self, label: str) -> bytes:
        raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                   info=("arch-block::" + label).encode("ascii")).derive(self._master_key)
        return base64.urlsafe_b64encode(raw)

    def _fernet(self, category: str) -> Fernet:
        try:
            return self._fernets[category]
        except KeyError as e:
            raise ValueError(f"Unknown encryption category: {category!r}") from e

    # -- BLOB columns (bytes in, bytes out) ---------------------------------
    def encrypt(self, category: str, plaintext: bytes) -> bytes:
        return _BLOB_MARKER + self._fernet(category).encrypt(plaintext)

    def decrypt(self, category: str, blob: bytes) -> bytes:
        if not blob or not blob.startswith(_BLOB_MARKER):
            return blob  # legacy / already-plaintext — pass through
        try:
            return self._fernet(category).decrypt(blob[len(_BLOB_MARKER):])
        except InvalidToken as e:
            raise PasswordInvalid("Cannot decrypt project content.") from e

    # -- TEXT columns (str in, str out) -------------------------------------
    def encrypt_text(self, category: str, s: str) -> str:
        if s is None or s == "":
            return s
        token = self._fernet(category).encrypt(s.encode("utf-8")).decode("ascii")
        return _TEXT_MARKER + token

    def decrypt_text(self, category: str, s: str) -> str:
        if not s or not isinstance(s, str) or not s.startswith(_TEXT_MARKER):
            return s  # legacy / already-plaintext — pass through
        try:
            return self._fernet(category).decrypt(
                s[len(_TEXT_MARKER):].encode("ascii")).decode("utf-8")
        except InvalidToken as e:
            raise PasswordInvalid("Cannot decrypt project content.") from e

    # -- password canary ----------------------------------------------------
    def make_canary(self) -> str:
        return self.encrypt_text("A", _CANARY)

    def verify_canary(self, stored: Optional[str]) -> None:
        """Raise PasswordInvalid if `stored` doesn't decrypt to the canary."""
        if not stored:
            return  # no canary recorded (defensive) — nothing to verify
        if self.decrypt_text("A", stored) != _CANARY:
            raise PasswordInvalid("Incorrect master password.")


def is_marked_blob(value) -> bool:
    return isinstance(value, (bytes, bytearray)) and bytes(value).startswith(_BLOB_MARKER)


def is_marked_text(value) -> bool:
    return isinstance(value, str) and value.startswith(_TEXT_MARKER)


# ---------------------------------------------------------------------------
# One-time migration: legacy whole-file-encrypted (already decrypted to a
# plaintext temp DB) → per-block. Encrypts every target column IN PLACE and
# records the scheme/salt/canary, then the caller writes the plaintext SQLite
# back over the user-facing ``.arch``. Idempotent: values already marked are
# skipped, so a re-run (e.g. after an interrupted migration) is safe.
# ---------------------------------------------------------------------------

# (category, table, pk_columns, value_column, is_blob)
_MIGRATION_TARGETS = [
    ("A", "architecture_rows", ("model_id", "row_index"), "row_data", False),
    ("A", "release_rows", ("release_id", "row_index"), "row_data", False),
    ("A", "release_results", ("release_id", "col_name"), "results", False),
    ("A", "release_column_metadata", ("release_id", "col_name"), "metadata", False),
    ("A", "model_metadata", ("model_id", "key"), "value", False),
    ("A", "elf_functions", ("id",), "parameters", False),
    ("A", "elf_functions", ("id",), "return_type", False),
    ("A", "elf_structures", ("id",), "fields", False),
    ("A", "elf_global_vars", ("id",), "var_type", False),
    ("B", "release_source_files", ("release_id", "rel_path"), "content_gzip", True),
    ("C", "ai_release_maps", ("model_id", "release_id"), "mindmap_json", False),
    ("C", "ai_release_maps", ("model_id", "release_id"), "code_map_json", False),
    ("C", "ai_code_diffs", ("id",), "unified_diff", False),
    ("C", "ai_model_mindmaps", ("model_id",), "mindmap_json", False),
    ("C", "ai_model_mindmaps", ("model_id",), "code_map_json", False),
    ("D", "test_project_files", ("test_project_id", "rel_path"), "content_gzip", True),
    ("D", "test_code_injections", ("id",), "line_above_code", False),
    ("D", "test_code_injections", ("id",), "line_below_code", False),
    ("D", "test_code_injections", ("id",), "injected_code", False),
]


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def migrate_to_per_block(db, password: str, meta_keys=None) -> "BlockCipher":
    """Encrypt all content columns of an already-open plaintext DB in place and
    stamp it as per-block-v1. Returns the BlockCipher for the caller to attach.

    `db` is a ProjectDatabase whose cipher is NOT yet attached (so reads return
    legacy plaintext). `meta_keys` is the category-E project_meta allowlist
    (encrypted under key E); pass None to skip meta encryption.
    """
    conn = db._conn
    salt = BlockCipher.new_salt()
    cipher = BlockCipher.from_password(password, salt)

    for category, table, pk_cols, col, is_blob in _MIGRATION_TARGETS:
        if not _table_exists(conn, table):
            continue
        pk_sql = ", ".join(pk_cols)
        rows = conn.execute(
            f"SELECT {pk_sql}, {col} FROM {table}").fetchall()
        updates = []
        for r in rows:
            keys = tuple(r[i] for i in range(len(pk_cols)))
            value = r[len(pk_cols)]
            if value is None or value == "":
                continue
            if is_blob:
                if is_marked_blob(value):
                    continue
                enc = cipher.encrypt(category, bytes(value))
            else:
                if is_marked_text(value):
                    continue
                enc = cipher.encrypt_text(category, value)
            updates.append((enc,) + keys)
        if updates:
            where = " AND ".join(f"{c}=?" for c in pk_cols)
            conn.executemany(
                f"UPDATE {table} SET {col}=? WHERE {where}", updates)

    _migrate_history(conn, cipher)

    if meta_keys:
        _migrate_meta(conn, cipher, meta_keys)

    # Stamp scheme/salt/canary via raw SQL (bypasses the set_meta E-allowlist so
    # these control rows are never themselves encrypted).
    for key, val in (
        ("enc_scheme", ENC_SCHEME),
        ("enc_kdf_salt", base64.urlsafe_b64encode(salt).decode("ascii")),
        ("enc_canary", cipher.make_canary()),
        ("schema_version", str(_schema_version())),
    ):
        conn.execute(
            "INSERT OR REPLACE INTO project_meta (key, value) VALUES (?, ?)",
            (key, val))
    conn.commit()
    return cipher


def _schema_version() -> int:
    from .Logic_Database import DB_SCHEMA_VERSION
    return DB_SCHEMA_VERSION


def _migrate_history(conn, cipher: "BlockCipher") -> None:
    """Re-encrypt history.description from the legacy app-key obfuscation to
    category A and rebuild the HMAC chain over the new stored ciphertext."""
    from .Logic_Database import _deobfuscate_history, _history_row_hmac
    rows = conn.execute(
        "SELECT id, timestamp, username, model_name, description, release_id "
        "FROM history ORDER BY id").fetchall()
    prev = ""
    updates = []
    for _id, ts, user, model, desc, rid in rows:
        if is_marked_text(desc):
            # already per-block — keep chaining over the stored value
            new_desc = desc
        else:
            plain = _deobfuscate_history(desc)         # "enc:" or legacy plaintext
            new_desc = cipher.encrypt_text("A", plain) if plain else plain
        new_hmac = _history_row_hmac(prev, ts, user, model, new_desc, rid)
        updates.append((new_desc, new_hmac, _id))
        prev = new_hmac
    if updates:
        conn.executemany(
            "UPDATE history SET description=?, entry_hmac=? WHERE id=?", updates)


def _migrate_meta(conn, cipher: "BlockCipher", meta_keys) -> None:
    for key in meta_keys:
        row = conn.execute(
            "SELECT value FROM project_meta WHERE key=?", (key,)).fetchone()
        if not row or not row[0] or is_marked_text(row[0]):
            continue
        conn.execute(
            "UPDATE project_meta SET value=? WHERE key=?",
            (cipher.encrypt_text("E", row[0]), key))
