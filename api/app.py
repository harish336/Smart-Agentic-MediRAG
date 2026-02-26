"""
SmartChunk-RAG — Flask API Entry Point

Run:
    python -m api.app

Production:
    gunicorn api.app:app
"""

import os
from api import create_app


# ============================================================
# Create Flask App
# ============================================================

app = create_app()


# ============================================================
# Environment Config
# ============================================================

HOST = os.getenv("API_HOST", "0.0.0.0")
PORT = int(os.getenv("API_PORT", 5000))
DEBUG = os.getenv("API_DEBUG", "true").lower() == "true"


# ============================================================
# Run Server
# ============================================================

if __name__ == "__main__":

    print("\n" + "=" * 80)
    print("🚀 SmartChunk-RAG API Starting...")
    print("=" * 80)
    print(f"Host   : {HOST}")
    print(f"Port   : {PORT}")
    print(f"Debug  : {DEBUG}")
    print("Access : http://localhost:5000")
    print("=" * 80 + "\n")

    app.run(
        host=HOST,
        port=PORT,
        debug=DEBUG,
        threaded=True
    )