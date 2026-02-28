"""
SmartChunk-RAG — Auth Middleware

Provides:
- require_auth decorator
- require_role decorator
- Automatic Bearer token validation
- Role-based access control
"""

from functools import wraps
from flask import request, jsonify, g
from api.auth.jwt_handler import verify_token
from api.auth.role_permissions import ROLE_PERMISSIONS


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
# REQUIRE AUTH
# ============================================================

def require_auth(f):
    """
    Ensures user is authenticated.
    """

    @wraps(f)
    def decorated(*args, **kwargs):

        token = _extract_token()

        if not token:
            return jsonify({"error": "Authorization token required"}), 401

        try:
            payload = verify_token(token)

            # Attach user info to global context
            g.user = {
                "user_id": payload.get("user_id"),
                "username": payload.get("username"),
                "role": payload.get("role")
            }

        except Exception as e:
            return jsonify({"error": str(e)}), 401

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

            token = _extract_token()

            if not token:
                return jsonify({"error": "Authorization token required"}), 401

            try:
                payload = verify_token(token)

                user_role = payload.get("role")

                if not user_role:
                    return jsonify({"error": "Invalid token payload"}), 403

                # Check role permissions
                allowed_roles = ROLE_PERMISSIONS.get(required_role, [])

                if user_role not in allowed_roles:
                    return jsonify({"error": "Insufficient permissions"}), 403

                # Attach user info
                g.user = {
                    "user_id": payload.get("user_id"),
                    "username": payload.get("username"),
                    "role": user_role
                }

            except Exception as e:
                return jsonify({"error": str(e)}), 401

            return f(*args, **kwargs)

        return decorated

    return decorator