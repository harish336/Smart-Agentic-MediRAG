"""
Auth Routes.

Endpoints:
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- POST /auth/logout
- POST /auth/forgot-password
- POST /auth/verify-otp
- POST /auth/reset-password
"""

import os
import re
import time
from flask import g, jsonify, request

from api.auth import auth_blueprint
from api.auth.middleware import require_auth
from api.auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from api.auth.password_reset_service import create_reset_otp, invalidate_reset_otp, verify_reset_otp
from api.auth.password_utils import hash_password, verify_password
from database.app_store import create_user, get_user_by_email, get_user_by_identity, update_user_password


EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
DEV_SHOW_OTP = os.getenv("DEV_SHOW_OTP", "true").lower() == "true"


def _is_valid_email(value: str) -> bool:
    return bool(value and EMAIL_REGEX.match(value))


def _resolve_username(data: dict) -> str:
    return (data.get("username") or data.get("name") or "").strip()


@auth_blueprint.route("/register", methods=["POST"])
def register():
    start_time = time.time()
    data = request.get_json() or {}

    username = _resolve_username(data)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"error": "username, email and password are required"}), 400
    if not _is_valid_email(email):
        return jsonify({"error": "invalid email format"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    try:
        user = create_user(
            username=username,
            email=email,
            password_hash=hash_password(password),
            role="user",
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    latency = round(time.time() - start_time, 4)
    return jsonify(
        {
            "status": "registered",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            },
            "latency_seconds": latency,
        }
    ), 201


@auth_blueprint.route("/login", methods=["POST"])
def login():
    start_time = time.time()
    data = request.get_json() or {}

    identity = (data.get("email") or data.get("username") or "").strip()
    password = data.get("password", "")
    if not identity or not password:
        return jsonify({"error": "email/username and password are required"}), 400

    user = get_user_by_identity(identity)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    access_token = create_access_token(user_id=user["id"], username=user["username"], role=user["role"])
    refresh_token = create_refresh_token(user_id=user["id"], username=user["username"], role=user["role"])

    latency = round(time.time() - start_time, 4)
    return jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            },
            "latency_seconds": latency,
        }
    ), 200


@auth_blueprint.route("/refresh", methods=["POST"])
def refresh():
    data = request.get_json() or {}
    refresh_token = (data.get("refresh_token") or "").strip()
    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 400

    try:
        payload = verify_token(refresh_token, expected_type="refresh")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 401

    access_token = create_access_token(
        user_id=payload.get("user_id"),
        username=payload.get("username"),
        role=payload.get("role"),
    )
    return jsonify({"access_token": access_token}), 200


@auth_blueprint.route("/logout", methods=["POST"])
def logout():
    return jsonify({"status": "ok"}), 200


@auth_blueprint.route("/me", methods=["GET"])
@require_auth
def me():
    return jsonify(
        {
            "user": {
                "id": g.user["user_id"],
                "username": g.user["username"],
                "role": g.user["role"],
            }
        }
    ), 200


@auth_blueprint.route("/forgot-password", methods=["POST"])
@auth_blueprint.route("/forgot-password/request-otp", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not _is_valid_email(email):
        return jsonify({"error": "valid email is required"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify(
            {
                "status": "ok",
                "message": "If this email is registered, OTP was generated.",
            }
        ), 200

    try:
        otp, expires_at = create_reset_otp(user_id=user["id"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 429
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    response = {
        "status": "ok",
        "message": "OTP generated successfully.",
        "expires_at": expires_at,
    }
    if DEV_SHOW_OTP:
        response["otp"] = otp
    return jsonify(response), 200


@auth_blueprint.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not _is_valid_email(email):
        return jsonify({"error": "valid email is required"}), 400
    if not otp:
        return jsonify({"error": "otp is required"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "OTP expired or not found"}), 400

    is_valid, result = verify_reset_otp(user_id=user["id"], otp=otp)
    if not is_valid:
        return jsonify({"error": result}), 400

    return jsonify({"status": "ok", "message": "OTP is valid."}), 200


@auth_blueprint.route("/reset-password", methods=["POST"])
@auth_blueprint.route("/forgot-password/reset", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()
    new_password = data.get("new_password", "")

    if not _is_valid_email(email):
        return jsonify({"error": "valid email is required"}), 400
    if not otp:
        return jsonify({"error": "otp is required"}), 400
    if not new_password or len(new_password) < 6:
        return jsonify({"error": "new_password must be at least 6 characters"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "User not found"}), 404

    is_valid, result = verify_reset_otp(user_id=user["id"], otp=otp)
    if not is_valid:
        return jsonify({"error": result}), 400

    updated = update_user_password(user_id=user["id"], password_hash=hash_password(new_password))
    if not updated:
        return jsonify({"error": "User not found"}), 404

    invalidate_reset_otp(result)
    return jsonify({"status": "ok", "message": "Password updated successfully."}), 200
