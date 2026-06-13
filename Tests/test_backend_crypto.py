"""
At-rest project encryption tests (master-password protected .arch).

Covers the crypto primitives and the AppState lifecycle: encrypted round-trip
(new → save → reopen with password), wrong/missing password, the plaintext
test-bypass, dual-mode open of legacy plaintext files, and that no plaintext
SQLite is left on disk at the encrypted path.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic import Logic_Crypto as crypto

TOKEN = "arch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PW = "Sup3r-Secret-Pass!"


# --------------------------------------------------------------------------
# crypto primitives
# --------------------------------------------------------------------------
def test_encrypt_decrypt_roundtrip():
    data = b"SQLite format 3\x00 ... pretend db bytes ..."
    blob = crypto.encrypt_bytes(data, PW)
    assert blob[:8] == crypto.ENC_MAGIC
    assert blob != data
    assert crypto.decrypt_bytes(blob, PW) == data


def test_wrong_password_raises():
    blob = crypto.encrypt_bytes(b"secret", PW)
    with pytest.raises(crypto.PasswordInvalid):
        crypto.decrypt_bytes(blob, "wrong-password")


def test_bypass_and_blacklist():
    assert crypto.bypasses_encryption(None)
    assert crypto.bypasses_encryption("master123")
    assert not crypto.bypasses_encryption(PW)
    assert crypto.is_blacklisted("master123")
    assert not crypto.is_blacklisted(PW)


# --------------------------------------------------------------------------
# AppState lifecycle via the API
# --------------------------------------------------------------------------
@pytest.fixture()
def client():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        yield c


def test_encrypted_project_roundtrip(client):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "Secret.arch")
        r = client.post("/api/project/new", json={"path": path, "password": PW}, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["encrypted"] is True

        # On disk it must be ciphertext, not a plaintext SQLite header.
        assert crypto.is_encrypted_file(path)
        assert not crypto.is_plaintext_sqlite(path)

        client.post("/api/project/save", headers=AUTH)
        client.post("/api/project/close", headers=AUTH)
        # Still ciphertext after a save.
        assert crypto.is_encrypted_file(path)

        # Reopen needs the password.
        assert client.post("/api/project/open",
                           json={"path": path, "mode": "exclusive"},
                           headers=AUTH).status_code == 401
        assert client.post("/api/project/open",
                           json={"path": path, "mode": "exclusive", "password": "nope"},
                           headers=AUTH).status_code == 403
        ok = client.post("/api/project/open",
                         json={"path": path, "mode": "exclusive", "password": PW}, headers=AUTH)
        assert ok.status_code == 200 and ok.json()["encrypted"] is True
        client.post("/api/project/close", headers=AUTH)


def test_no_password_is_plaintext(client):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "Demo.arch")
        r = client.post("/api/project/new", json={"path": path}, headers=AUTH)
        assert r.status_code == 200 and r.json()["encrypted"] is False
        assert crypto.is_plaintext_sqlite(path)
        client.post("/api/project/close", headers=AUTH)
        # Reopens with no password.
        assert client.post("/api/project/open",
                           json={"path": path, "mode": "view"}, headers=AUTH).status_code == 200


def test_test_bypass_password_is_plaintext(client):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "Bypass.arch")
        r = client.post("/api/project/new",
                        json={"path": path, "password": "master123"}, headers=AUTH)
        assert r.status_code == 200 and r.json()["encrypted"] is False
        assert crypto.is_plaintext_sqlite(path)


def test_unrecognized_format_rejected(client):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "junk.arch")
        with open(path, "wb") as f:
            f.write(b"not a database at all")
        r = client.post("/api/project/open", json={"path": path, "mode": "view"}, headers=AUTH)
        assert r.status_code == 409
