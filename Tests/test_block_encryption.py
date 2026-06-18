"""
Per-block (per-category) content encryption tests.

Covers the BlockCipher primitive (round-trip, marker idempotency, legacy
passthrough, per-category key isolation, canary), the ProjectDatabase column
wiring (content stored as ciphertext, reads decrypt), worker-thread key
propagation, category-E meta encryption, and the one-time legacy whole-file
(ARCHENC1) → per-block migration through the AppState/API open path.
"""
import base64
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from fastapi.testclient import TestClient

from backend.app import create_app
from Application_Logic import Logic_Crypto as crypto
from Application_Logic.Logic_Block_Crypto import (
    BlockCipher, ENC_SCHEME, is_marked_blob, is_marked_text, migrate_to_per_block,
)
from Application_Logic.Logic_Database import ProjectDatabase, ENCRYPTED_META_KEYS
from Tests.test_helpers import make_project_db

PW = "Sup3r-Secret-Pass!"
TOKEN = "arch-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


# --------------------------------------------------------------------------
# BlockCipher primitive
# --------------------------------------------------------------------------
def test_blob_and_text_roundtrip():
    c = BlockCipher.from_password(PW, BlockCipher.new_salt())
    blob = c.encrypt("B", b"int main(){}")
    assert is_marked_blob(blob) and blob != b"int main(){}"
    assert c.decrypt("B", blob) == b"int main(){}"
    txt = c.encrypt_text("A", "cell value")
    assert is_marked_text(txt) and c.decrypt_text("A", txt) == "cell value"


def test_legacy_passthrough_and_idempotency():
    c = BlockCipher.from_password(PW, BlockCipher.new_salt())
    # Unmarked legacy values are returned untouched.
    assert c.decrypt("B", b"plain gzip bytes") == b"plain gzip bytes"
    assert c.decrypt_text("A", "plain text") == "plain text"
    # Empty / None pass through both ways.
    assert c.encrypt_text("A", "") == ""
    assert c.encrypt_text("A", None) is None


def test_per_category_key_isolation():
    c = BlockCipher.from_password(PW, BlockCipher.new_salt())
    tok = c.encrypt("A", b"x")
    with pytest.raises(crypto.PasswordInvalid):
        c.decrypt("B", tok)  # wrong category key cannot decrypt


def test_canary_verifies_correct_and_rejects_wrong_password():
    salt = BlockCipher.new_salt()
    canary = BlockCipher.from_password(PW, salt).make_canary()
    BlockCipher.from_password(PW, salt).verify_canary(canary)  # no raise
    with pytest.raises(crypto.PasswordInvalid):
        BlockCipher.from_password("wrong", salt).verify_canary(canary)


# --------------------------------------------------------------------------
# ProjectDatabase column wiring
# --------------------------------------------------------------------------
def _encrypted_db(path):
    """A ProjectDatabase opened with a fresh per-block cipher (mirrors what
    AppState.new_project sets up). Returns (db, cipher)."""
    db = make_project_db(
        path,
        layout=[("Port", "PortSearchColumn", True)],
        models=[{"name": "M", "status": "In Work", "rows": []}],
        releases=[{"name": "R1"}],
    )
    salt = BlockCipher.new_salt()
    cipher = BlockCipher.from_password(PW, salt)
    db.set_block_cipher(cipher)
    db.set_meta("enc_scheme", ENC_SCHEME)
    db.set_meta("enc_kdf_salt", base64.urlsafe_b64encode(salt).decode("ascii"))
    db.set_meta("enc_canary", cipher.make_canary())
    return db, cipher


def test_source_and_rows_stored_as_ciphertext(tmp_path):
    path = str(tmp_path / "p.arch")
    db, _ = _encrypted_db(path)
    rid = db.get_all_releases()[0]["id"]
    mid = db.get_all_models()[0]["id"]
    db.save_release_source_files(rid, [("src/main.c", "int main(void){return 0;}\n")])
    db.save_model_rows(mid, [{"Port": {"text": "PROPRIETARY_PORT"}}])
    db.add_history_entry("edited cell A1", model_name="M", username="alice")
    db.commit()
    db.close()

    # Read the raw on-disk columns — they must be ciphertext, not plaintext.
    conn = sqlite3.connect(path)
    blob = conn.execute("SELECT content_gzip FROM release_source_files").fetchone()[0]
    row_data = conn.execute("SELECT row_data FROM architecture_rows").fetchone()[0]
    desc = conn.execute("SELECT description FROM history").fetchone()[0]
    conn.close()
    assert is_marked_blob(blob)
    assert is_marked_text(row_data) and "PROPRIETARY_PORT" not in row_data
    assert is_marked_text(desc) and "edited cell A1" not in desc

    # Reopen WITH the right cipher → content decrypts.
    salt = base64.urlsafe_b64decode(_meta(path, "enc_kdf_salt").encode("ascii"))
    db2 = ProjectDatabase(); db2.open(path)
    db2.set_block_cipher(BlockCipher.from_password(PW, salt))
    assert db2.read_release_source_file(rid, "src/main.c") == "int main(void){return 0;}\n"
    assert db2.get_model_rows(mid)[0]["Port"]["text"] == "PROPRIETARY_PORT"
    assert db2.get_history(None)[0]["description"] == "edited cell A1"
    assert db2.verify_history_chain() is True
    db2.close()


def test_category_e_meta_encrypted(tmp_path):
    path = str(tmp_path / "p.arch")
    db, _ = _encrypted_db(path)
    db.set_meta("ai_prompt", "MY PROPRIETARY PROMPT")  # category E (allowlisted)
    db.set_meta("operations_column_name", "Operations")  # NOT allowlisted → plain
    db.commit()
    assert db.get_meta("ai_prompt") == "MY PROPRIETARY PROMPT"  # decrypts on read
    db.close()
    raw_prompt = _meta(path, "ai_prompt")
    raw_ops = _meta(path, "operations_column_name")
    assert is_marked_text(raw_prompt) and "PROPRIETARY" not in raw_prompt
    assert raw_ops == "Operations"  # structural meta stays plaintext
    assert "ai_prompt" in ENCRYPTED_META_KEYS


def test_worker_without_cipher_cannot_read_content(tmp_path):
    """A second connection that forgets to attach the cipher must NOT silently
    return readable content — guards the worker-propagation requirement."""
    path = str(tmp_path / "p.arch")
    db, _ = _encrypted_db(path)
    rid = db.get_all_releases()[0]["id"]
    db.save_release_source_files(rid, [("a.c", "secret();\n")])
    db.commit(); db.close()

    cipherless = ProjectDatabase(); cipherless.open(path)  # no set_block_cipher
    # gzip.decompress over ciphertext fails → None (never the plaintext).
    assert cipherless.read_release_source_file(rid, "a.c") is None
    cipherless.close()


def _meta(path, key):
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM project_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# migrate_to_per_block (unit) + legacy ARCHENC1 open path (via API)
# --------------------------------------------------------------------------
def test_migrate_to_per_block_unit(tmp_path):
    path = str(tmp_path / "old.arch")
    db = make_project_db(
        path,
        layout=[("Port", "PortSearchColumn", True)],
        models=[{"name": "M", "status": "In Work", "rows": [{"Port": {"text": "P1"}}]}],
        releases=[{"name": "R1"}],
    )
    rid = db.get_all_releases()[0]["id"]
    db.save_release_source_files(rid, [("m.c", "void m(){}\n")])  # plaintext gzip
    db.add_history_entry("legacy entry", model_name="M", username="bob")
    db.commit()

    cipher = migrate_to_per_block(db, PW, meta_keys=ENCRYPTED_META_KEYS)
    db.close()

    # Raw columns are now ciphertext.
    conn = sqlite3.connect(path)
    assert is_marked_blob(
        conn.execute("SELECT content_gzip FROM release_source_files").fetchone()[0])
    assert conn.execute(
        "SELECT value FROM project_meta WHERE key='enc_scheme'").fetchone()[0] == ENC_SCHEME
    conn.close()

    # Reattach the same cipher → everything decrypts and the HMAC chain holds.
    db2 = ProjectDatabase(); db2.open(path)
    db2.set_block_cipher(cipher)
    assert db2.read_release_source_file(rid, "m.c") == "void m(){}\n"
    mid = db2.get_all_models()[0]["id"]
    assert db2.get_model_rows(mid)[0]["Port"]["text"] == "P1"
    assert db2.get_history(None)[0]["description"] == "legacy entry"
    assert db2.verify_history_chain() is True
    db2.close()


@pytest.fixture()
def client():
    app = create_app(token=TOKEN)
    with TestClient(app) as c:
        yield c


def test_legacy_archenc1_migrates_on_open(client, tmp_path):
    # Build a legacy whole-file-encrypted .arch (plaintext columns inside).
    plain = str(tmp_path / "plain.db")
    db = make_project_db(
        plain,
        layout=[("Port", "PortSearchColumn", True)],
        models=[{"name": "M", "status": "In Work", "rows": []}],
        releases=[{"name": "R1"}],
    )
    rid = db.get_all_releases()[0]["id"]
    db.save_release_source_files(rid, [("m.c", "void m(){}\n")])
    db.add_history_entry("legacy entry", username="bob")
    db.commit(); db.close()
    arch = str(tmp_path / "Legacy.arch")
    crypto.encrypt_file(plain, arch, PW)
    assert crypto.is_encrypted_file(arch)

    # Open via the API → one-time migration to per-block.
    assert client.post("/api/project/open",
                       json={"path": arch, "mode": "exclusive"},
                       headers=AUTH).status_code == 401  # needs password
    ok = client.post("/api/project/open",
                     json={"path": arch, "mode": "exclusive", "password": PW},
                     headers=AUTH)
    assert ok.status_code == 200 and ok.json()["encrypted"] is True
    client.post("/api/project/close", headers=AUTH)

    # On disk it is now plaintext SQLite stamped per-block, with ciphertext content.
    assert crypto.is_plaintext_sqlite(arch)
    assert not crypto.is_encrypted_file(arch)
    assert _meta(arch, "enc_scheme") == ENC_SCHEME
    conn = sqlite3.connect(arch)
    assert is_marked_blob(
        conn.execute("SELECT content_gzip FROM release_source_files").fetchone()[0])
    conn.close()

    # Reopening with the same password still works (canary + content readable).
    ok2 = client.post("/api/project/open",
                      json={"path": arch, "mode": "view", "password": PW}, headers=AUTH)
    assert ok2.status_code == 200
    client.post("/api/project/close", headers=AUTH)
