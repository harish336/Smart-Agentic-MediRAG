"""
SmartChunk-RAG — Authentication Module

Provides:
- JWT creation & verification
- Role-based access control
- Auth middleware
- Auth routes blueprint

Usage:
    from api.auth import auth_blueprint, require_role
"""

from flask import Blueprint

# Blueprint
auth_blueprint = Blueprint("auth", __name__)

# Import submodules so they register automatically
from . import auth_routes  # noqa: F401
from .jwt_handler import create_access_token, verify_token  # noqa: F401
from .middleware import require_auth, require_role  # noqa: F401
from .password_utils import hash_password, verify_password  # noqa: F401
from .role_permissions import ROLE_PERMISSIONS  # noqa: F401

__all__ = [
    "auth_blueprint",
    "create_access_token",
    "verify_token",
    "require_auth",
    "require_role",
    "hash_password",
    "verify_password",
    "ROLE_PERMISSIONS",
]