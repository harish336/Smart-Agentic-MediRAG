"""
SmartChunk-RAG - Vector Embedder
"""

from typing import Dict, Tuple

from sentence_transformers import SentenceTransformer

from config.system_loader import get_model_config


_MODEL_CACHE: Dict[Tuple[str, str], SentenceTransformer] = {}


class VectorEmbedder:
    """
    Generates embeddings using sentence-transformers.
    Fully config-driven with process-local model reuse.
    """

    def __init__(self):
        print("=" * 70)
        print("[VECTOR EMBEDDER] Initializing...")

        model_config = get_model_config()
        embedding_cfg = model_config.get("embedding", {})
        perf_cfg = model_config.get("performance", {})

        self.enabled = embedding_cfg.get("enabled", True)
        self.model_name = embedding_cfg.get("model", "all-MiniLM-L6-v2")
        self.device = embedding_cfg.get("device", "cpu")
        self.normalize = embedding_cfg.get("normalize", True)
        self.encode_batch_size = int(perf_cfg.get("batch_size", 32))

        print(f"[CONFIG] Enabled    : {self.enabled}")
        print(f"[CONFIG] Model      : {self.model_name}")
        print(f"[CONFIG] Device     : {self.device}")
        print(f"[CONFIG] Normalize  : {self.normalize}")
        print(f"[CONFIG] Batch Size : {self.encode_batch_size}")

        if not self.enabled:
            print("[VECTOR EMBEDDER] Embedding disabled in config")
            self.model = None
            return

        try:
            cache_key = (self.model_name, self.device)
            if cache_key not in _MODEL_CACHE:
                _MODEL_CACHE[cache_key] = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                )
            self.model = _MODEL_CACHE[cache_key]
            print("[VECTOR EMBEDDER] Model ready")
        except Exception as e:
            print("[VECTOR EMBEDDER] ERROR loading model:", e)
            self.model = None

        print("=" * 70)

    def embed(self, texts):
        print("[VECTOR EMBEDDER] Generating embeddings...")

        single_input = False
        if isinstance(texts, str):
            texts = [texts]
            single_input = True

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
            batch_size=self.encode_batch_size,
        )

        print("[VECTOR EMBEDDER] Embedding generation completed")
        print(f"[VECTOR DIMENSION] {len(embeddings[0])}")

        if single_input:
            return embeddings[0]
        return embeddings

    def embed_one(self, text: str):
        if not self.enabled:
            print("[VECTOR EMBEDDER] Skipped - embedding disabled")
            return None

        if self.model is None:
            raise RuntimeError("Embedding model not initialized")

        embedding = self.model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
            batch_size=1,
        )[0]
        return embedding

    def get_model_info(self):
        if self.model is None:
            return {
                "model": self.model_name,
                "device": self.device,
                "dimension": None,
                "normalize": self.normalize,
                "enabled": self.enabled,
            }

        return {
            "model": self.model_name,
            "device": self.device,
            "dimension": self.model.get_sentence_embedding_dimension(),
            "normalize": self.normalize,
            "enabled": self.enabled,
        }
