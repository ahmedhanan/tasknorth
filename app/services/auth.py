import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _make_token(user_id: uuid.UUID, token_type: str, expire_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expire_delta
    payload = {"sub": str(user_id), "type": token_type, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID) -> str:
    return _make_token(
        user_id, "access", timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _make_token(
        user_id, "refresh", timedelta(days=settings.jwt_refresh_token_expire_days)
    )


def decode_refresh_token(token: str) -> uuid.UUID:
    from jose import JWTError

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            raise ValueError("not a refresh token")
        return uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise ValueError("invalid refresh token") from exc


def generate_mcp_api_key() -> str:
    return secrets.token_urlsafe(32)
