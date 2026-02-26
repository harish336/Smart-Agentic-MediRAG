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


# ============================================================
# CREATE FLASK APP
# ============================================================

def create_app():

    app = Flask(__name__)

    # --------------------------------------------------------
    # Enable CORS (Allow Postman / Frontend calls)
    # --------------------------------------------------------
    CORS(app)

    # --------------------------------------------------------
    # Basic Logging Configuration
    # --------------------------------------------------------
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    # --------------------------------------------------------
    # Register Routes
    # --------------------------------------------------------
    from api.routes import register_routes
    register_routes(app)

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