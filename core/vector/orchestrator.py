"""
SmartChunk-RAG — Vector Orchestrator

Responsibilities:
- Generate deterministic document_id
- Validate chunks
- Batch embeddings
- Store vectors in Chroma
- Respect fail-soft behavior
- Respect batch size from config

Config Sources:
- database.yaml → vector_db
- model.yaml → embedding
- system.yaml → project + performance

Author: SmartChunk-RAG System
"""

import hashlib
from typing import List, Dict
import os
from PyPDF2 import PdfReader

from core.vector.embedder import VectorEmbedder
from core.vector.store import ChromaStore
from core.vector.validator import VectorChunkValidator
from core.registry.document_registry import DocumentRegistry

from config.system_loader import (
    get_database_config,
    get_system_config
)


class VectorOrchestrator:

    def __init__(self, pdf_path: str):

        print("=" * 80)
        print("VECTOR ORCHESTRATOR INITIALIZING")
        print("=" * 80)

        self.pdf_path = pdf_path

        # Load configs
        self.db_config = get_database_config()
        self.system_config = get_system_config()

        self.fail_soft = self.system_config["project"].get("fail_soft", True)
        self.batch_size = self.system_config["performance"].get("batch_size", 16)

        # Initialize components
        self.embedder = VectorEmbedder()
        self.store = ChromaStore()
        self.validator = VectorChunkValidator()

        # Deterministic document ID
        self.document_id = self.generate_document_id(pdf_path)

        self.registry = DocumentRegistry()

        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        title = os.path.basename(pdf_path)

        self.registry.register(
            doc_id=self.document_id,
            title=title,
            source_path=pdf_path,
            total_pages=total_pages
        )

        print(f"[VECTOR] Document ID: {self.document_id}")
        print("=" * 80)

    # -------------------------------------------------
    # Deterministic document_id
    # -------------------------------------------------

    def generate_document_id(self, path: str) -> str:

        with open(path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        return file_hash[:16]

    # -------------------------------------------------
    # Ingest Chunks
    # -------------------------------------------------

    def ingest(self, chunks: List[Dict]):

        print("=" * 80)
        print("VECTOR INGESTION STARTED")
        print("=" * 80)

        if not chunks:
            print("[VECTOR] No chunks provided")
            return None

        # Validate
        if not self.validator.validate(chunks):
            print("[VECTOR] Validation failed")

            if not self.fail_soft:
                raise ValueError("Chunk validation failed")

            print("[VECTOR] Continuing due to fail_soft=True")

        try:
            self._process_batches(chunks)

        except Exception as e:

            print("[VECTOR] ERROR during ingestion:", e)

            if not self.fail_soft:
                raise e

            print("[VECTOR] Fail-soft mode enabled — skipping vector storage")

        print("=" * 80)
        print("VECTOR INGESTION COMPLETED")
        print("=" * 80)

        return self.document_id

    # -------------------------------------------------
    # Batch Processing
    # -------------------------------------------------

    def _process_batches(self, chunks: List[Dict]):

        total = len(chunks)
        print(f"[VECTOR] Total chunks: {total}")
        print(f"[VECTOR] Batch size: {self.batch_size}")

        for i in range(0, total, self.batch_size):

            batch = chunks[i:i + self.batch_size]

            print(f"[VECTOR] Processing batch {i} → {i + len(batch)}")

            texts = [c["text"] for c in batch]

            embeddings = self.embedder.embed(texts)

            ids = []
            metadatas = []

            for chunk in batch:

                chunk_id = f"{self.document_id}_{chunk['chunk_id']}"

                ids.append(chunk_id)

                metadatas.append({
                    "doc_id": self.document_id,
                    "chunk_id": chunk["chunk_id"],
                    "chapter": chunk.get("chapter"),
                    "subheading": chunk.get("subheading"),
                    "page_label": chunk.get("page_label"),
                    "page_physical": chunk.get("page_physical"),
                })

            self.store.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas
            )

    # -------------------------------------------------
    # Delete Document Vectors
    # -------------------------------------------------

    def delete_document(self):

        print(f"[VECTOR] Deleting document vectors: {self.document_id}")

        try:
            self.store.delete_document(self.document_id)
        except Exception as e:
            print("[VECTOR] Delete failed:", e)

            if not self.fail_soft:
                raise e

            print("[VECTOR] Fail-soft enabled — continuing")