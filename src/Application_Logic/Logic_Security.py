"""
Security logic — password hashing and verification only.
The master-password dialogs live in UI/Dialog_Master_Password.py (Phase 0:
logic never creates widgets).
"""
import bcrypt


class SecurityManager:
    @staticmethod
    def hash_password(plain: str) -> str:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(plain.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        if not hashed:
            return False
        try:
            return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
        except Exception:
            return False
