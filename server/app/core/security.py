"""Security utilities: password hashing, JWT generation/validation, token hashing, and pairing code generation."""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
import string
from typing import Any, Dict, Optional
import uuid

import bcrypt
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# Character set for pairing codes (unambiguous uppercase alphanumeric)
PAIRING_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def hash_password(password: str) -> str:
    """Hash plaintext password using bcrypt with work factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning("Password verification error: %s", exc)
        return False


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of refresh token or secret for indexed DB storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_pairing_code(length: int = 6) -> str:
    """Generate cryptographically secure one-time pairing code."""
    return "".join(secrets.choice(PAIRING_CHARSET) for _ in range(length))


def hash_pairing_code(code: str) -> str:
    """Hash pairing code (case-insensitive) for secure DB lookup."""
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def generate_refresh_token() -> str:
    """Generate high-entropy random refresh token string."""
    return secrets.token_urlsafe(48)


def create_access_token(
    user_id: str,
    device_id: Optional[str] = None,
    device_type: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "device_id": str(device_id) if device_id else None,
        "device_type": device_type or "USER",
        "token_type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        if payload.get("token_type") != "access":
            logger.warning("Decoded token is not an access token.")
            return None
        return payload
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid access token: %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error decoding token: %s", exc)
        return None
