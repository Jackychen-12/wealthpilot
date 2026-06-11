"""认证服务 — JWT + bcrypt 密码哈希。"""

import hashlib
from datetime import datetime, timedelta

import bcrypt
import jwt

from wealthpilot.settings import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72


def _get_secret() -> str:
    return get_settings().jwt_secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith(("$2b$", "$2a$")):
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    # Legacy SHA-256 fallback: format is "salt$hash"
    if "$" not in hashed:
        return False
    salt, stored_hash = hashed.split("$", 1)
    return hashlib.sha256((salt + plain).encode()).hexdigest() == stored_hash


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
