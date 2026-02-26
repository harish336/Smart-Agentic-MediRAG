"""
SmartChunk-RAG — Vector Embedder

Responsibilities:
- Load embedding configuration from model.yaml
- Initialize sentence-transformer model
- Support CPU / CUDA device selection
- Respect normalization flag
- Batch-safe embedding generation
- Fail-soft compatible

Config Sources:
- config/model.yaml → embedding
- config/system.yaml → performance (optional future use)

Author: SmartChunk-RAG System
"""

from typing import List
from sentence_transformers import SentenceTransformer
from config.system_loader import get_model_config


class VectorEmbedder:
    """
    Generates embeddings using sentence-transformers.
    Fully config-driven.
    """

    def __init__(self):

        print("=" * 70)
        print("[VECTOR EMBEDDER] Initializing...")

        model_config = get_model_config()
        embedding_cfg = model_config.get("embedding", {})

        self.enabled = embedding_cfg.get("enabled", True)
        self.model_name = embedding_cfg.get("model", "all-MiniLM-L6-v2")
        self.device = embedding_cfg.get("device", "cpu")
        self.normalize = embedding_cfg.get("normalize", True)

        print(f"[CONFIG] Enabled    : {self.enabled}")
        print(f"[CONFIG] Model      : {self.model_name}")
        print(f"[CONFIG] Device     : {self.device}")
        print(f"[CONFIG] Normalize  : {self.normalize}")

        if not self.enabled:
            print("[VECTOR EMBEDDER] Embedding disabled in config")
            self.model = None
            return

        try:
            self.model = SentenceTransformer(
                self.model_name,
                device=self.device
            )
            print("[VECTOR EMBEDDER] Model loaded successfully")
        except Exception as e:
            print("[VECTOR EMBEDDER] ERROR loading model:", e)
            self.model = None

        print("=" * 70)

    # -------------------------------------------------
    # Batch Embedding
    # -------------------------------------------------

    def embed(self, texts):

        print("[VECTOR EMBEDDER] Generating embeddings...")

        single_input = False

        # If single string → convert to list
        if isinstance(texts, str):
            texts = [texts]
            single_input = True

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=self.normalize
        )

        print("[VECTOR EMBEDDER] Embedding generation completed")

        print(f"[VECTOR DIMENSION] {len(embeddings[0])}")

        # If original input was single → return single vector
        if single_input:
            return embeddings[0]

        return embeddings
    # -------------------------------------------------
    # Single Embedding
    # -------------------------------------------------

    def embed_one(self, text: str):

        if not self.enabled:
            print("[VECTOR EMBEDDER] Skipped — embedding disabled")
            return None

        if self.model is None:
            raise RuntimeError("Embedding model not initialized")

        embedding = self.model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=self.normalize
        )[0]

        return embedding

    # -------------------------------------------------
    # Model Info
    # -------------------------------------------------

    def get_model_info(self):

        if self.model is None:
            return {
                "model": self.model_name,
                "device": self.device,
                "dimension": None,
                "normalize": self.normalize,
                "enabled": self.enabled
            }

        return {
            "model": self.model_name,
            "device": self.device,
            "dimension": self.model.get_sentence_embedding_dimension(),
            "normalize": self.normalize,
            "enabled": self.enabled
        }