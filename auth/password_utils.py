"""
SmartChunk-RAG — Password Utilities

Responsibilities:
- Hash passwords securely
- Verify passwords safely
- Use bcrypt (recommended for production)
"""

import bcrypt


# ============================================================
# HASH PASSWORD
# ============================================================

def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.
    Returns hashed password as string.
    """

    if not password:
        raise ValueError("Password cannot be empty")

    # Generate salt automatically
    salt = bcrypt.gensalt()

    # Hash password
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)

    return hashed.decode("utf-8")


# ============================================================
# VERIFY PASSWORD
# ============================================================

def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify plaintext password against stored hash.
    """

    if not password or not password_hash:
        return False

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8")
        )
    except Exception:
        return False