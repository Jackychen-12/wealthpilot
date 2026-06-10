"""认证服务 — JWT + 密码哈希。"""

import hashlib
import secrets
from datetime import datetime, timedelta

import jwt

from wealthpilot.settings import get_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72


def _get_secret() -> str:
    return get_settings().jwt_secret


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(plain: str, hashed: str) -> bool:
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
