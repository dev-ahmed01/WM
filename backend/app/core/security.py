"""Security primitives: Password hashing with bcrypt & JWT token management."""

import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings
from app.exceptions import TokenExpiredError, TokenInvalidError


ROLE_ALIASES = {
    "admin": "admin",
    "administrator": "admin",
    "manager": "manager",
    "supervisor": "manager",
    "employee": "employee",
    "worker": "employee",
}


def normalize_role(role: str) -> str:
    """Return the canonical application role used by route dependencies."""
    normalized = (role or "").strip().lower()
    return ROLE_ALIASES.get(normalized, normalized)


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    pw_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    pw_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pw_bytes, hash_bytes)


def create_access_token(
    user_id: str,
    role: str,
    department_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates an access JWT embedding user_id (sub), role, and department_id claims."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES))
    payload = {
        "sub": str(user_id),
        "role": normalize_role(role),
        "department_id": department_id,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a refresh JWT embedding user_id (sub) claim."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS))
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a JWT token string into its claims dictionary."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if "sub" not in payload:
            raise TokenInvalidError("Token payload missing required 'sub' claim")
        if payload.get("type") == "access":
            if not payload.get("role") or not payload.get("department_id"):
                raise TokenInvalidError("Access token is missing role or department claims")
            payload["role"] = normalize_role(payload["role"])
        return payload
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("JWT token has expired") from exc
    except JWTError as exc:
        raise TokenInvalidError(f"Invalid JWT token: {str(exc)}") from exc
    except TokenInvalidError:
        raise
    except Exception as exc:
        raise TokenInvalidError(f"Token decoding failed: {str(exc)}") from exc


# Alias for backward compatibility
decode_jwt_token = decode_token
