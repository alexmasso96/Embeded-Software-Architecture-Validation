"""
AI Credentials Store
====================
Secure, per-user, at-rest-encrypted storage for AI provider secrets (API keys
and the Copilot OAuth token).

Design goals (see AI_INTEGRATION_PLAN.md, Phase 1):
  * Secrets live OUTSIDE the project — in a per-user OS config directory, never
    in the .arch project DB (which is shared/distributed). The project DB only
    ever stores non-secret preferences.
  * The on-disk file is Fernet-encrypted with a custom extension
    (``credentials.aikeys``) so it is neither human-readable nor grep-able, and
    is bound to the current machine/user (copying just the blob to another
    machine will not decrypt it).
  * "Configure once per machine" — all projects on a machine share one store.

This is real at-rest encryption (AES via Fernet), basic-but-meaningful: it
defeats casual file scanning and over-the-shoulder reading. It is not a hardware
vault — a determined attacker with code execution as this user could still
re-derive the key. That trade-off is intentional and documented.

Test/portable override: set env var ``ARCHVALIDATOR_CONFIG_DIR`` to relocate the
store (used by the test-suite to avoid touching the real user profile).
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_APP_DIR_NAME = "ArchValidator"
_CRED_FILENAME = "credentials.aikeys"
_ENV_OVERRIDE = "ARCHVALIDATOR_CONFIG_DIR"

# Fixed application salt for key derivation. The real secret is the per-machine
# id (below); this salt just domain-separates the KDF. Changing it would
# invalidate every existing store, so treat it as a frozen constant.
_APP_SALT = b"ArchValidator::ai-credentials::v1"
_KDF_ITERATIONS = 200_000

_COPILOT_OAUTH_FIELD = "__copilot_oauth__"


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    """Per-user config directory holding the encrypted store.

    Honors the ARCHVALIDATOR_CONFIG_DIR override (tests / portable installs),
    otherwise uses the OS-appropriate per-user location.
    """
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        base = Path(override)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA") or str(Path.home())
        base = Path(appdata) / _APP_DIR_NAME
    else:  # linux / other posix
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".config") / _APP_DIR_NAME
    return base


def _cred_path() -> Path:
    return _config_dir() / _CRED_FILENAME


def _ensure_dir() -> Path:
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
    return d


# ---------------------------------------------------------------------------
# Key derivation / crypto
# ---------------------------------------------------------------------------

def _machine_id() -> bytes:
    """A stable-ish per-machine/user identifier used as the KDF password.

    Combines the MAC-based node id, hostname and login name. None of these is a
    secret on their own; together they bind the encrypted blob to this
    machine+user so it cannot be trivially decrypted if copied elsewhere.
    """
    try:
        node = uuid.getnode()
    except Exception:
        node = 0
    try:
        host = platform.node()
    except Exception:
        host = ""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    return f"{node}|{host}|{user}".encode("utf-8")


def _fernet() -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_APP_SALT,
        iterations=_KDF_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(_machine_id()))
    return Fernet(key)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load() -> Dict[str, str]:
    """Decrypt and return the credential dict; {} on missing/corrupt/foreign."""
    path = _cred_path()
    if not path.is_file():
        return {}
    try:
        token = path.read_bytes()
        plaintext = _fernet().decrypt(token)
        data = json.loads(plaintext.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (InvalidToken, ValueError, OSError, json.JSONDecodeError):
        # Corrupt, tampered, or encrypted on a different machine — treat as empty
        # rather than crashing the app.
        return {}


def _save(data: Dict[str, str]) -> None:
    _ensure_dir()
    path = _cred_path()
    token = _fernet().encrypt(json.dumps(data).encode("utf-8"))
    # Write atomically-ish via a temp file in the same dir, then replace.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(token)
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Public API — provider API keys
# ---------------------------------------------------------------------------

def get_key(provider: str) -> Optional[str]:
    """Return the stored API key for a provider, or None if not configured."""
    val = _load().get(provider)
    return val if val else None


def set_key(provider: str, value: str) -> None:
    """Store (or update) the API key for a provider. Empty value clears it."""
    data = _load()
    if value:
        data[provider] = value
    else:
        data.pop(provider, None)
    _save(data)


def delete_key(provider: str) -> None:
    """Remove a provider's stored key."""
    data = _load()
    if data.pop(provider, None) is not None:
        _save(data)


def list_configured() -> List[str]:
    """Provider ids that currently have a non-empty key (excludes the Copilot
    OAuth token, which is queried separately)."""
    return sorted(
        k for k, v in _load().items()
        if k != _COPILOT_OAUTH_FIELD and v
    )


def is_configured(provider: str) -> bool:
    return bool(get_key(provider))


# ---------------------------------------------------------------------------
# Public API — Copilot OAuth token
# ---------------------------------------------------------------------------

def get_copilot_oauth_token() -> Optional[str]:
    val = _load().get(_COPILOT_OAUTH_FIELD)
    return val if val else None


def set_copilot_oauth_token(token: str) -> None:
    data = _load()
    if token:
        data[_COPILOT_OAUTH_FIELD] = token
    else:
        data.pop(_COPILOT_OAUTH_FIELD, None)
    _save(data)


def clear_copilot_oauth_token() -> None:
    data = _load()
    if data.pop(_COPILOT_OAUTH_FIELD, None) is not None:
        _save(data)


# ---------------------------------------------------------------------------
# Maintenance helpers
# ---------------------------------------------------------------------------

def credentials_path() -> str:
    """Absolute path of the encrypted store (for display in the UI/help)."""
    return str(_cred_path())


def clear_all() -> None:
    """Delete the entire store (used by 'Disconnect all' / uninstall)."""
    path = _cred_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
