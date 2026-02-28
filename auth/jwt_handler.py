"""
SmartChunk-RAG — JWT Handler

Responsibilities:
- Create access tokens
- Verify and decode tokens
- Handle expiration
- Secure signing

Uses:
- HS256 symmetric signing
"""

import os
import time
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_THIS_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", 30))


# ============================================================
# CREATE ACCESS TOKEN
# ============================================================

def create_access_token(user_id: str, username: str, role: str) -> str:
    """
    Generate JWT access token.
    """

    expiration = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)

    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": expiration
    }

    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )

    return token


# ============================================================
# VERIFY TOKEN
# ============================================================

def verify_token(token: str) -> dict:
    """
    Decode and verify JWT token.
    Returns payload if valid.
    Raises exception if invalid.
    """

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")

    except jwt.InvalidTokenError:
        raise Exception("Invalid token")