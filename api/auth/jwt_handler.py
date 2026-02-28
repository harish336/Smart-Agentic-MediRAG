"""
SmartChunk-RAG — JWT Handler (PRODUCTION READY)

Responsibilities:
- Create access tokens
- Verify and decode tokens
- Handle expiration
- Secure signing

Uses:
- HS256 symmetric signing
"""

import os
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", 15))
JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", 7))

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set in environment variables.")


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================

class TokenExpiredError(Exception):
    """Raised when JWT token has expired."""
    pass


class InvalidTokenError(Exception):
    """Raised when JWT token is invalid."""
    pass


# ============================================================
# CREATE ACCESS TOKEN
# ============================================================

def _encode_token(payload: dict) -> str:
    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    if isinstance(token, bytes):
        token = token.decode("utf-8")

    return token


def create_access_token(user_id: str, username: str, role: str) -> str:
    """
    Generate signed JWT access token.
    """

    now = datetime.utcnow()
    expiration = now + timedelta(minutes=JWT_EXPIRATION_MINUTES)

    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "token_type": "access",
        "iat": now,
        "exp": expiration
    }
    return _encode_token(payload)


def create_refresh_token(user_id: str, username: str, role: str) -> str:
    now = datetime.utcnow()
    expiration = now + timedelta(days=JWT_REFRESH_EXPIRATION_DAYS)
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "token_type": "refresh",
        "iat": now,
        "exp": expiration
    }
    return _encode_token(payload)


# ============================================================
# VERIFY TOKEN
# ============================================================

def verify_token(token: str, expected_type: str | None = None) -> dict:
    """
    Decode and verify JWT token.
    Returns payload if valid.
    Raises custom exceptions if invalid.
    """

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        if expected_type and payload.get("token_type") != expected_type:
            raise InvalidTokenError("Invalid token type.")

        return payload

    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired.")

    except jwt.InvalidTokenError:
        raise InvalidTokenError("Invalid token.")
