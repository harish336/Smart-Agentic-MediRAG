"""
SmartChunk-RAG — Vector Store (Chroma)

Responsibilities:
- Initialize persistent Chroma DB
- Respect database.yaml configuration
- Upsert vectors in batches
- Support deletion by document_id
- Respect distance metric
- Fail-soft compatible

Config Source:
- config/database.yaml → vector_db
- config/system.yaml → project + performance

Author: SmartChunk-RAG System
"""

import chromadb
from chromadb.config import Settings

from config.system_loader import (
    get_database_config,
    get_system_config
)

import os



class ChromaStore:

    def __init__(self):

        print("=" * 70)
        print("[VECTOR STORE] Initializing...")

        db_config = get_database_config()
        system_config = get_system_config()

        vector_cfg = db_config.get("vector_db", {})

        self.enabled = vector_cfg.get("enabled", True)
        self.persist = vector_cfg.get("persist", True)
        self.persist_path = vector_cfg.get("persist_path", "./vector_store")

        collection_cfg = vector_cfg.get("collection", {})
        self.collection_name = collection_cfg.get("name", "smart_chunks")
        self.distance_metric = collection_cfg.get("distance_metric", "cosine")

        self.fail_soft = system_config["project"].get("fail_soft", True)
        # Normalize path safely for Windows
        self.persist_path = os.path.abspath(self.persist_path)

        print(f"[CONFIG] Enabled         : {self.enabled}")
        print(f"[CONFIG] Persist         : {self.persist}")
        print(f"[CONFIG] Persist Path    : {self.persist_path}")
        print(f"[CONFIG] Collection Name : {self.collection_name}")
        print(f"[CONFIG] Distance Metric : {self.distance_metric}")

        if not self.enabled:
            print("[VECTOR STORE] Disabled via config")
            self.client = None
            self.collection = None
            return

        try:
            self.client = chromadb.PersistentClient(
    path=self.persist_path
)

            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": self.distance_metric}
            )

            print("[VECTOR STORE] Collection ready")

        except Exception as e:
            print("[VECTOR STORE] Initialization error:", e)

            if not self.fail_soft:
                raise e

            print("[VECTOR STORE] Fail-soft enabled — store unavailable")
            self.client = None
            self.collection = None

        print("=" * 70)

    # -------------------------------------------------
    # Upsert Vectors
    # -------------------------------------------------

    def upsert(self, ids, embeddings, documents, metadatas):

        if not self.enabled or self.collection is None:
            print("[VECTOR STORE] Skipped upsert — store disabled")
            return

        try:
            print(f"[VECTOR STORE] Upserting {len(ids)} vectors")

            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

            print("[VECTOR STORE] Upsert completed")

        except Exception as e:
            print("[VECTOR STORE] Upsert failed:", e)

            if not self.fail_soft:
                raise e

            print("[VECTOR STORE] Fail-soft enabled — continuing")

    # -------------------------------------------------
    # Delete by Document ID
    # -------------------------------------------------

    def delete_document(self, doc_id: str):

        if not self.enabled or self.collection is None:
            print("[VECTOR STORE] Skipped delete — store disabled")
            return

        try:
            print(f"[VECTOR STORE] Deleting vectors for doc_id={doc_id}")

            self.collection.delete(
                where={"doc_id": doc_id}
            )

            print("[VECTOR STORE] Deletion completed")

        except Exception as e:
            print("[VECTOR STORE] Delete failed:", e)

            if not self.fail_soft:
                raise e

            print("[VECTOR STORE] Fail-soft enabled — continuing")

    # -------------------------------------------------
    # Query
    # -------------------------------------------------

    def query(self, query_embedding, top_k=5):

        if not self.enabled or self.collection is None:
            print("[VECTOR STORE] Query skipped — store disabled")
            return None

        try:
            print(f"[VECTOR STORE] Running similarity search (top_k={top_k})")

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )

            return results

        except Exception as e:
            print("[VECTOR STORE] Query failed:", e)

            if not self.fail_soft:
                raise e

            print("[VECTOR STORE] Fail-soft enabled — returning None")
            return None