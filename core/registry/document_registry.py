"""
SmartChunk-RAG — Document Registry
"""

import sqlite3
import os
from datetime import datetime
from config.system_loader import get_database_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("DocumentRegistry", component="ingestion")


class DocumentRegistry:

    def __init__(self):

        try:
            db_config = get_database_config()
            metadata_cfg = db_config.get("metadata_store", {})

            self.db_path = os.path.abspath(metadata_cfg.get("path"))

            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            self._create_table()

            logger.info(f"Registry initialized at: {self.db_path}")

        except Exception:
            logger.exception("Failed to initialize DocumentRegistry")
            raise

    # =====================================================
    # CREATE TABLE
    # =====================================================

    def _create_table(self):

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        doc_id TEXT PRIMARY KEY,
                        title TEXT,
                        source_path TEXT,
                        total_pages INTEGER,
                        created_at TEXT
                    )
                """)

                conn.commit()

        except Exception:
            logger.exception("Failed creating documents table")
            raise

    # =====================================================
    # REGISTER DOCUMENT
    # =====================================================

    def register(self, doc_id, title, source_path, total_pages):

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO documents
                    (doc_id, title, source_path, total_pages, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    doc_id,
                    title,
                    source_path,
                    total_pages,
                    datetime.utcnow().isoformat()
                ))

                conn.commit()

            logger.info(f"Registered document: {doc_id}")

        except Exception:
            logger.exception(f"Failed registering document: {doc_id}")
            raise

    # =====================================================
    # FETCH ALL
    # =====================================================

    def fetch_all(self):

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM documents")
                rows = cursor.fetchall()

            logger.info(f"Fetched {len(rows)} documents")
            return rows

        except Exception:
            logger.exception("Failed fetching documents")
            raise
