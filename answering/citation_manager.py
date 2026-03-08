"""
SmartChunk-RAG — Citation Manager (Production Version)

Features:
- Semantic deduplication (doc_id + page + chapter + subheading)
- Supports vector + graph merged results
- Limits to MAX_CITATIONS
- Removes null fields
- Maps doc_id → document_name
- Windows-safe path handling
"""

import os
import hashlib
import re

from core.utils.logging_utils import get_component_logger


logger = get_component_logger("CitationManager", component="answering")


class CitationManager:

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

    MAX_CITATIONS = 15

    # ============================================================
    # PUBLIC METHOD
    # ============================================================

    def build(self, retrieved_chunks):

        citations = []
        seen_keys = set()
        input_count = len(retrieved_chunks or [])

        for r in retrieved_chunks:

            if len(citations) >= self.MAX_CITATIONS:
                break

            metadata = r.get("metadata", {})

            citation = {}

            # ----------------------------------------------------
            # Collect fields from retriever result
            # ----------------------------------------------------

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

            # ----------------------------------------------------
            # Remove null / empty fields
            # ----------------------------------------------------

            for key, value in combined.items():
                if key in self.ALLOWED_FIELDS and value not in [None, "", "None"]:
                    citation[key] = value

            if not citation:
                continue

            # ----------------------------------------------------
            # 🔥 Semantic Deduplication Key
            # ----------------------------------------------------

            unique_key = (
                citation.get("doc_id"),
                citation.get("page_physical"),
                self._normalize(citation.get("chapter")),
                self._normalize(citation.get("subheading"))
            )

            if unique_key in seen_keys:
                continue

            seen_keys.add(unique_key)

            # ----------------------------------------------------
            # Map doc_id → document_name
            # ----------------------------------------------------

            doc_id = citation.get("doc_id")

            if doc_id and self._is_hex(doc_id):
                document_name = self._map_docid_to_filename(doc_id)
                if document_name:
                    citation["document_name"] = document_name

            citations.append(citation)

        logger.info(
            "Citation build summary | input_chunks=%d output_citations=%d dedup_keys=%d",
            input_count,
            len(citations),
            len(seen_keys),
        )
        return citations

    # ============================================================
    # NORMALIZATION (for stable dedup)
    # ============================================================

    def _normalize(self, value):
        if not value:
            return None
        return str(value).strip().lower()

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

        except Exception:
            logger.exception("Citation doc_id -> filename mapping failed | doc_id=%s", doc_id)

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
