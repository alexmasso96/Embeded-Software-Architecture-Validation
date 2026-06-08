"""
Tests for Logic_AI_Credentials — the encrypted per-user AI credential store.

The store is relocated to a temp directory via the ARCHVALIDATOR_CONFIG_DIR
override so these tests never touch the real user profile.
"""
import os
import sys
import importlib

sys.path.append(os.path.abspath("src"))

import pytest


@pytest.fixture()
def creds(tmp_path, monkeypatch):
    """Fresh credential store rooted at a temp dir, reloaded per test."""
    monkeypatch.setenv("ARCHVALIDATOR_CONFIG_DIR", str(tmp_path))
    import Application_Logic.Logic_AI_Credentials as mod
    importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_set_get_roundtrip(creds):
    creds.set_key("anthropic", "sk-ant-123")
    creds.set_key("openai", "sk-oai-456")
    assert creds.get_key("anthropic") == "sk-ant-123"
    assert creds.get_key("openai") == "sk-oai-456"


def test_get_missing_returns_none(creds):
    assert creds.get_key("gemini") is None
    assert creds.is_configured("gemini") is False


def test_update_overwrites(creds):
    creds.set_key("openai", "first")
    creds.set_key("openai", "second")
    assert creds.get_key("openai") == "second"


def test_empty_value_clears(creds):
    creds.set_key("openai", "x")
    creds.set_key("openai", "")
    assert creds.get_key("openai") is None


def test_delete_key(creds):
    creds.set_key("gemini", "g-1")
    creds.delete_key("gemini")
    assert creds.get_key("gemini") is None
    # Deleting a non-existent key is a no-op, not an error.
    creds.delete_key("gemini")


def test_list_configured(creds):
    creds.set_key("anthropic", "a")
    creds.set_key("openai", "o")
    creds.set_copilot_oauth_token("ghu_xxx")  # excluded from list
    assert creds.list_configured() == ["anthropic", "openai"]


# ---------------------------------------------------------------------------
# Copilot OAuth token
# ---------------------------------------------------------------------------

def test_copilot_token_roundtrip(creds):
    assert creds.get_copilot_oauth_token() is None
    creds.set_copilot_oauth_token("ghu_abc123")
    assert creds.get_copilot_oauth_token() == "ghu_abc123"
    creds.clear_copilot_oauth_token()
    assert creds.get_copilot_oauth_token() is None


def test_copilot_token_independent_of_keys(creds):
    creds.set_key("anthropic", "a")
    creds.set_copilot_oauth_token("tok")
    creds.delete_key("anthropic")
    # Clearing a provider key must not wipe the Copilot token.
    assert creds.get_copilot_oauth_token() == "tok"


# ---------------------------------------------------------------------------
# Encryption / robustness
# ---------------------------------------------------------------------------

def test_file_is_encrypted_not_plaintext(creds, tmp_path):
    creds.set_key("anthropic", "sk-ant-SUPERSECRET")
    raw = (tmp_path / "credentials.aikeys").read_bytes()
    # The secret must not appear anywhere in the on-disk bytes.
    assert b"sk-ant-SUPERSECRET" not in raw
    assert b"anthropic" not in raw


def test_custom_extension_and_location(creds, tmp_path):
    creds.set_key("openai", "x")
    assert (tmp_path / "credentials.aikeys").is_file()
    assert creds.credentials_path().endswith("credentials.aikeys")


def test_corrupt_file_returns_empty(creds, tmp_path):
    creds.set_key("openai", "x")
    (tmp_path / "credentials.aikeys").write_bytes(b"not a valid fernet token")
    # Corrupt store must degrade gracefully, not raise.
    assert creds.get_key("openai") is None
    assert creds.list_configured() == []


def test_clear_all(creds, tmp_path):
    creds.set_key("openai", "x")
    creds.set_copilot_oauth_token("t")
    creds.clear_all()
    assert not (tmp_path / "credentials.aikeys").exists()
    assert creds.get_key("openai") is None
    assert creds.get_copilot_oauth_token() is None


def test_persists_across_reload(creds, tmp_path, monkeypatch):
    creds.set_key("anthropic", "persisted")
    # Simulate a fresh process: reload the module, same config dir.
    import importlib
    import Application_Logic.Logic_AI_Credentials as mod
    importlib.reload(mod)
    assert mod.get_key("anthropic") == "persisted"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
