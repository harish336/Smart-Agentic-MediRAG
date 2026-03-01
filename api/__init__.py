"""
SmartChunk-RAG — API Initialization

Creates Flask application instance.
Registers routes and middleware.

Usage:
    from api import create_app
    app = create_app()
"""

from flask import Flask, jsonify
from flask_cors import CORS
import logging
import os
import atexit

from database.app_store import init_db, upsert_admin_user
from core.utils.logging_utils import shutdown_logging


# ============================================================
# CREATE FLASK APP
# ============================================================

def create_app():

    app = Flask(__name__)

    # --------------------------------------------------------
    # Register Shutdown Handler for Graceful Logging Cleanup
    # --------------------------------------------------------
    atexit.register(shutdown_logging)

    # --------------------------------------------------------
    # Enable CORS
    # --------------------------------------------------------
    cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
    cors_origins = (
        [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
        if cors_origins_raw != "*"
        else "*"
    )
    CORS(app, resources={r"/*": {"origins": cors_origins}})

    # --------------------------------------------------------
    # Basic Logging Configuration
    # --------------------------------------------------------
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # --------------------------------------------------------
    # Initialize DB
    # --------------------------------------------------------
    init_db()
    _bootstrap_admin_user()

    # --------------------------------------------------------
    # Register Routes
    # --------------------------------------------------------
    from api.routes import register_routes
    register_routes(app)

    from api.auth import auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix="/auth")

    # --------------------------------------------------------
    # Global Error Handler (JSON-safe)
    # --------------------------------------------------------
    @app.errorhandler(Exception)
    def handle_exception(e):
        logging.exception("Unhandled Exception:")
        return jsonify({
            "error": "Internal Server Error",
            "message": str(e)
        }), 500

    # --------------------------------------------------------
    # Health Endpoint (Quick Ping)
    # --------------------------------------------------------
    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "service": "SmartChunk-RAG API",
            "status": "running"
        })

    return app


def _bootstrap_admin_user() -> None:
    username = (os.getenv("ADMIN_NAME") or "").strip()
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""

    if not any([username, email, password]):
        return

    if not username or not email or not password:
        logging.warning(
            "Skipping admin bootstrap: set ADMIN_NAME, ADMIN_EMAIL, and ADMIN_PASSWORD together."
        )
        return

    try:
        from api.auth.password_utils import hash_password

        user = upsert_admin_user(
            username=username,
            email=email,
            password_hash=hash_password(password),
        )
        logging.info("Admin bootstrap complete for %s", user.get("email"))
    except Exception:
        logging.exception("Admin bootstrap failed.")
