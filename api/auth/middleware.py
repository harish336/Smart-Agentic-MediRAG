"""
SmartChunk-RAG — Auth Middleware (PRODUCTION READY)

Provides:
- require_auth decorator
- require_role decorator
- Automatic Bearer token validation
- Role-based access control
"""

from functools import wraps
from flask import request, jsonify, g

from api.auth.jwt_handler import (
    verify_token,
    TokenExpiredError,
    InvalidTokenError
)

from api.auth.role_permissions import has_permission


# ============================================================
# EXTRACT TOKEN
# ============================================================

def _extract_token():
    """
    Extract Bearer token from Authorization header.
    """

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return None

    if not auth_header.startswith("Bearer "):
        return None

    return auth_header.split(" ")[1]


# ============================================================
# VERIFY + ATTACH USER
# ============================================================

def _authenticate_request():
    """
    Verifies JWT and attaches user to Flask global context.
    """

    token = _extract_token()

    if not token:
        return None, ("Authorization token required", 401)

    try:
        payload = verify_token(token, expected_type="access")

        g.user = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "role": payload.get("role")
        }

        return payload, None

    except TokenExpiredError as e:
        return None, (str(e), 401)

    except InvalidTokenError as e:
        return None, (str(e), 401)


# ============================================================
# REQUIRE AUTH
# ============================================================

def require_auth(f):
    """
    Ensures user is authenticated.
    """

    @wraps(f)
    def decorated(*args, **kwargs):

        _, error = _authenticate_request()

        if error:
            message, status_code = error
            return jsonify({"error": message}), status_code

        return f(*args, **kwargs)

    return decorated


# ============================================================
# REQUIRE ROLE
# ============================================================

def require_role(required_role):
    """
    Ensures authenticated user has required role.
    """

    def decorator(f):

        @wraps(f)
        def decorated(*args, **kwargs):

            payload, error = _authenticate_request()

            if error:
                message, status_code = error
                return jsonify({"error": message}), status_code

            user_role = payload.get("role")

            if not user_role:
                return jsonify({"error": "Invalid token payload"}), 403

            # 🔐 Use role hierarchy system
            if not has_permission(user_role, required_role):
                return jsonify({"error": "Insufficient permissions"}), 403

            return f(*args, **kwargs)

        return decorated

    return decorator
