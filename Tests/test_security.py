"""
Tests for Logic_Security: bcrypt password hashing/verification and the
master-password dialogs (validation branches, no real user interaction).
"""
import os
import sys

sys.path.append(os.path.abspath("src"))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from Application_Logic.Logic_Security import (
    SecurityManager,
    MasterPasswordSetupDialog,
    MasterPasswordPromptDialog,
)


# --------------------------------------------------------------------------
# SecurityManager
# --------------------------------------------------------------------------

def test_hash_password_is_verifiable():
    h = SecurityManager.hash_password("hunter2")
    assert isinstance(h, str)
    assert h != "hunter2"  # never store plaintext
    assert SecurityManager.verify_password("hunter2", h) is True


def test_hash_password_uses_random_salt():
    h1 = SecurityManager.hash_password("samepass")
    h2 = SecurityManager.hash_password("samepass")
    assert h1 != h2  # different salts
    assert SecurityManager.verify_password("samepass", h1)
    assert SecurityManager.verify_password("samepass", h2)


def test_verify_password_wrong_password():
    h = SecurityManager.hash_password("correct")
    assert SecurityManager.verify_password("incorrect", h) is False


def test_verify_password_empty_hash():
    assert SecurityManager.verify_password("anything", "") is False
    assert SecurityManager.verify_password("anything", None) is False


def test_verify_password_malformed_hash_returns_false():
    # checkpw raises on a non-bcrypt string; should be swallowed -> False
    assert SecurityManager.verify_password("pw", "not-a-bcrypt-hash") is False


# --------------------------------------------------------------------------
# MasterPasswordSetupDialog validation branches
# --------------------------------------------------------------------------

def test_setup_dialog_empty_password():
    dlg = MasterPasswordSetupDialog()
    dlg.txt_password.setText("")
    dlg.txt_confirm.setText("")
    dlg.validate_and_accept()
    assert "empty" in dlg.lbl_error.text().lower()
    assert dlg.result() != dlg.DialogCode.Accepted.value


def test_setup_dialog_too_short():
    dlg = MasterPasswordSetupDialog()
    dlg.txt_password.setText("abc")
    dlg.txt_confirm.setText("abc")
    dlg.validate_and_accept()
    assert "6 characters" in dlg.lbl_error.text()


def test_setup_dialog_mismatch():
    dlg = MasterPasswordSetupDialog()
    dlg.txt_password.setText("longenough")
    dlg.txt_confirm.setText("different")
    dlg.validate_and_accept()
    assert "match" in dlg.lbl_error.text().lower()


def test_setup_dialog_success():
    dlg = MasterPasswordSetupDialog()
    dlg.txt_password.setText("goodpassword")
    dlg.txt_confirm.setText("goodpassword")
    dlg.validate_and_accept()
    assert dlg.result() == dlg.DialogCode.Accepted.value
    assert dlg.get_password() == "goodpassword"


# --------------------------------------------------------------------------
# MasterPasswordPromptDialog
# --------------------------------------------------------------------------

def test_prompt_dialog_get_password():
    dlg = MasterPasswordPromptDialog(prompt_text="Unlock:")
    dlg.txt_password.setText("secret")
    assert dlg.get_password() == "secret"


def test_prompt_dialog_accept_reject():
    dlg = MasterPasswordPromptDialog()
    dlg.accept()
    assert dlg.result() == dlg.DialogCode.Accepted.value


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
