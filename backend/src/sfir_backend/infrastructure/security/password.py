import hashlib
import os

import bcrypt


class PasswordService:
    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=12),
        ).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8"),
        )

    @staticmethod
    def generate_token() -> str:
        return hashlib.sha256(os.urandom(64)).hexdigest()
