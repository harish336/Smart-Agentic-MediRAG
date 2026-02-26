"""
SmartChunk-RAG — Citation Manager (Enhanced)

Features:
- Removes null fields
- Keeps only valid fields
- Detects hex doc_id
- Maps doc_id → document_name
- Avoids duplicate citations
- Windows-safe path handling
"""

import os
import hashlib
import re


class CitationManager:

    # Your PDF folder path
    DATA_FOLDER = r"C:\Users\Harish\Downloads\Smart Medirag\data"

    ALLOWED_FIELDS = [
        "doc_id",
        "document_name",
        "chunk_id",
        "chapter",
        "subheading",
        "emotion",
        "page_label",
        "page_physical",
        "source"
    ]

    # ============================================================
    # PUBLIC METHOD
    # ============================================================

    def build(self, retrieved_chunks):

        citations = []

        for r in retrieved_chunks:

            metadata = r.get("metadata", {})

            citation = {}

            # -------------------------
            # Collect all possible fields
            # -------------------------
            combined = {
                "doc_id": r.get("doc_id"),
                "chunk_id": r.get("chunk_id"),
                "source": r.get("source"),
                "chapter": metadata.get("chapter"),
                "subheading": metadata.get("subheading"),
                "emotion": metadata.get("emotion"),
                "page_label": metadata.get("page_label"),
                "page_physical": metadata.get("page_physical"),
            }

            # -------------------------
            # Clean null values
            # -------------------------
            for key, value in combined.items():
                if key in self.ALLOWED_FIELDS and value not in [None, "", "None"]:
                    citation[key] = value

            # -------------------------
            # Map doc_id → document_name
            # -------------------------
            doc_id = citation.get("doc_id")

            if doc_id and self._is_hex(doc_id):
                document_name = self._map_docid_to_filename(doc_id)
                if document_name:
                    citation["document_name"] = document_name

            # -------------------------
            # Avoid duplicates
            # -------------------------
            if citation and citation not in citations:
                citations.append(citation)

        return citations

    # ============================================================
    # HEX CHECK
    # ============================================================

    def _is_hex(self, value: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-fA-F]+", value))

    # ============================================================
    # MAP HASH → PDF NAME
    # ============================================================

    def _map_docid_to_filename(self, doc_id: str):

        if not os.path.exists(self.DATA_FOLDER):
            return None

        try:
            for filename in os.listdir(self.DATA_FOLDER):

                if not filename.lower().endswith(".pdf"):
                    continue

                file_path = os.path.join(self.DATA_FOLDER, filename)

                file_hash = self._compute_hash(file_path)

                if file_hash.startswith(doc_id):
                    return filename

        except Exception as e:
            print("[CITATION MANAGER ERROR]", e)

        return None

    # ============================================================
    # HASH COMPUTATION
    # ============================================================

    def _compute_hash(self, file_path):

        sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)

        return sha256.hexdigest()