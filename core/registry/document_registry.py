"""
SmartChunk-RAG — Document Registry

Stores:
- doc_id
- title
- source_path
- total_pages
- created_at

This is the permanent mapping layer.
"""

import sqlite3
import os
from datetime import datetime
from config.system_loader import get_database_config


class DocumentRegistry:

    def __init__(self):

        db_config = get_database_config()
        metadata_cfg = db_config.get("metadata_store", {})

        self.db_path = os.path.abspath(metadata_cfg.get("path"))

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self._create_table()

    def _create_table(self):

        conn = sqlite3.connect(self.db_path)
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
        conn.close()

    # =====================================================
    # REGISTER DOCUMENT
    # =====================================================

    def register(self, doc_id, title, source_path, total_pages):

        conn = sqlite3.connect(self.db_path)
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
        conn.close()

    # =====================================================
    # FETCH ALL
    # =====================================================

    def fetch_all(self):

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM documents")
        rows = cursor.fetchall()

        conn.close()
        return rows