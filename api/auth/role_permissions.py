"""
SmartChunk-RAG — Role Permissions

Defines:
- Available roles
- Role hierarchy
- Allowed access mapping
- Permission validation helpers
"""

# ============================================================
# ROLE HIERARCHY
# ============================================================

"""
Hierarchy principle:
Higher roles inherit lower role permissions.

admin > user > guest
"""

ROLE_HIERARCHY = {
    "admin": 3,
    "user": 2,
    "guest": 1
}


# ============================================================
# ROUTE ACCESS RULES
# ============================================================

"""
Define minimum role required per access level.
"""

ROLE_PERMISSIONS = {
    "admin": ["admin"],                 # Only admin
    "user": ["admin", "user"],          # Admin + User
    "guest": ["admin", "user", "guest"] # Everyone authenticated
}


# ============================================================
# PERMISSION CHECK HELPER
# ============================================================

def has_permission(user_role: str, required_role: str) -> bool:
    """
    Check if user's role satisfies required role.
    """

    if user_role not in ROLE_HIERARCHY:
        return False

    if required_role not in ROLE_HIERARCHY:
        return False

    return ROLE_HIERARCHY[user_role] >= ROLE_HIERARCHY[required_role]