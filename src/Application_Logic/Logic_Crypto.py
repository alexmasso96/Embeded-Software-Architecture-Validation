"""At-rest project encryption (master-password protected .arch).

Projects are encrypted at rest with a master-password-derived key
(PBKDF2-HMAC-SHA256 → Fernet). During an authenticated session the DB is
*decrypted into a private temp file* so the existing file-backed SQLite
architecture is unchanged — WAL journaling, the worker's per-job "own
connection to the same path" crash-safety pattern, and file locking all keep
working. On save the temp file is re-encrypted back to the ``.arch``. No
SQLCipher (which needs a custom SQLite binary and risks EDR blocking) — this
uses the already-trusted ``cryptography`` library (same as Logic_History's
Fernet usage).

Dual-mode, so dev/legacy data and the test suite keep working:
  * A plaintext SQLite file (magic ``SQLite format 3\\x00``) opens directly with
    no password.
  * An encrypted file (magic ``ARCHENC1``) requires the master password.
  * A few **test bypass passwords** intentionally skip encryption and save as
    plaintext, so the suite's plaintext fixtures don't need rewriting. These are
    blacklisted from production password setup (see ``is_blacklisted``) so a real
    user can never select one.

Encrypted file layout::

    ENC_MAGIC (8 bytes) | salt (16 bytes) | Fernet token (rest)

Fernet authenticates its payload (HMAC), so a wrong password or any tampering
fails decryption — that doubles as the integrity check for encrypted projects.
"""
from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SQLITE_MAGIC = b"SQLite format 3\x00"   # 16 bytes
ENC_MAGIC = b"ARCHENC1"                  # 8 bytes
SALT_LEN = 16
PBKDF2_ITERS = 200_000

# Passwords that intentionally bypass encryption (tests + demo databases).
# Blacklisted from production password setup so a user can't pick the bypass.
TEST_BYPASS_PASSWORDS = frozenset({"master123"})


class PasswordRequired(Exception):
    """Raised when opening an encrypted project without a password."""


class PasswordInvalid(Exception):
    """Raised when the supplied master password fails to decrypt the project."""


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------
def file_head(path: str, n: int = 16) -> bytes:
    with open(path, "rb") as f:
        return f.read(n)


def is_plaintext_sqlite(path: str) -> bool:
    return file_head(path, len(SQLITE_MAGIC)) == SQLITE_MAGIC


def is_encrypted_file(path: str) -> bool:
    return file_head(path, len(ENC_MAGIC)) == ENC_MAGIC


def bypasses_encryption(password: str | None) -> bool:
    """A project is stored plaintext when there's no password, or the password
    is one of the test-bypass values."""
    return password is None or password in TEST_BYPASS_PASSWORDS


def is_blacklisted(password: str) -> bool:
    """True for passwords reserved as test bypasses — rejected in production setup."""
    return password in TEST_BYPASS_PASSWORDS


# ---------------------------------------------------------------------------
# Crypto primitives
# ---------------------------------------------------------------------------
def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=PBKDF2_ITERS)
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def encrypt_bytes(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_LEN)
    token = Fernet(_derive_key(password, salt)).encrypt(plaintext)
    return ENC_MAGIC + salt + token


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    if blob[: len(ENC_MAGIC)] != ENC_MAGIC:
        raise ValueError("Not an encrypted .arch file.")
    salt = blob[len(ENC_MAGIC): len(ENC_MAGIC) + SALT_LEN]
    token = blob[len(ENC_MAGIC) + SALT_LEN:]
    try:
        return Fernet(_derive_key(password, salt)).decrypt(token)
    except InvalidToken as e:
        raise PasswordInvalid("Incorrect master password.") from e


# ---------------------------------------------------------------------------
# File helpers (atomic write)
# ---------------------------------------------------------------------------
def encrypt_file(src_db_path: str, dst_arch_path: str, password: str) -> None:
    """Encrypt the plaintext SQLite at ``src_db_path`` to the ``.arch`` at
    ``dst_arch_path`` (atomic replace)."""
    with open(src_db_path, "rb") as f:
        data = f.read()
    blob = encrypt_bytes(data, password)
    tmp = dst_arch_path + ".enc.tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dst_arch_path)


def decrypt_file(src_arch_path: str, dst_db_path: str, password: str) -> None:
    """Decrypt the ``.arch`` at ``src_arch_path`` to a plaintext SQLite file at
    ``dst_db_path``. Raises ``PasswordInvalid`` on a wrong password."""
    with open(src_arch_path, "rb") as f:
        blob = f.read()
    data = decrypt_bytes(blob, password)
    with open(dst_db_path, "wb") as f:
        f.write(data)
