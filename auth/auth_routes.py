"""
SmartChunk-RAG — Auth Routes

Endpoints:
- POST /auth/register
- POST /auth/login
"""

import time
from flask import request, jsonify
from api.auth import auth_blueprint
from api.auth.jwt_handler import create_access_token
from api.auth.password_utils import hash_password, verify_password
from api.database.user_store import (
    create_user,
    get_user_by_username
)


# ============================================================
# REGISTER USER
# ============================================================

@auth_blueprint.route("/register", methods=["POST"])
def register():

    start_time = time.time()
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "user")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    # Check if user already exists
    existing = get_user_by_username(username)
    if existing:
        return jsonify({"error": "User already exists"}), 400

    # Hash password
    hashed = hash_password(password)

    # Create user
    create_user(
        username=username,
        password_hash=hashed,
        role=role
    )

    latency = round(time.time() - start_time, 4)

    return jsonify({
        "status": "registered",
        "username": username,
        "role": role,
        "latency_seconds": latency
    }), 201


# ============================================================
# LOGIN
# ============================================================

@auth_blueprint.route("/login", methods=["POST"])
def login():

    start_time = time.time()
    data = request.get_json()

    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    user = get_user_by_username(username)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    if not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    # Create JWT
    token = create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"]
    )

    latency = round(time.time() - start_time, 4)

    return jsonify({
        "access_token": token,
        "role": user["role"],
        "latency_seconds": latency
    }), 200