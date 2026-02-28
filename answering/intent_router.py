import requests
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Tuple, Dict, List, Optional
from core.utils.logging_utils import get_component_logger

# ============================================================
# Logger Setup
# ============================================================

logger = get_component_logger("IntentRouter", component="answering")


# ============================================================
# Lazy Singleton for Embedding Model (LOAD ONLY ONCE)
# ============================================================

_embedder_instance: Optional[SentenceTransformer] = None


def get_embedder() -> SentenceTransformer:
    global _embedder_instance
    if _embedder_instance is None:
        try:
            logger.info("Loading SentenceTransformer model (all-MiniLM-L6-v2)...")
            _embedder_instance = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded successfully.")
        except Exception:
            logger.exception("Failed to load SentenceTransformer model")
            raise
    return _embedder_instance


class IntentRouter:
    """
    Intelligent Intent Router for Hybrid RAG Systems.
    Uses fast cosine similarity with SentenceTransformers, 
    falling back to a local Ollama LLM if confidence is low.
    """

    def __init__(
        self, 
        ollama_url: str = "http://localhost:11434/api/generate",
        llm_model: str = "mistral:7b-instruct",
        similarity_threshold: float = 0.55
    ):
        self.ollama_url = ollama_url
        self.llm_model = llm_model
        self.similarity_threshold = similarity_threshold

        try:
            # Lazy loaded embedder (ONLY FIRST TIME GLOBALLY)
            self.embedder = get_embedder()
        except Exception:
            logger.exception("IntentRouter initialization failed during embedder load")
            raise

        # Intent prototypes
        self.intent_prototypes: Dict[str, List[str]] = {
            "medical": [
                "medical diagnosis",
                "clinical treatment",
                "disease symptoms",
                "therapy and disorder"
            ],
            "book": [
                "chapter explanation",
                "from the textbook",
                "section summary",
                "explain from the book"
            ],
            "general": [
                "casual conversation",
                "general knowledge question",
                "simple explanation",
                "friendly chat",
                "hello, how are you"
            ]
        }

        try:
            # Precompute normalized embeddings
            self.prototype_embeddings = {
                intent: self.embedder.encode(texts, normalize_embeddings=True)
                for intent, texts in self.intent_prototypes.items()
            }
        except Exception:
            logger.exception("Failed to compute prototype embeddings")
            raise

        self.valid_intents = list(self.intent_prototypes.keys())

        logger.info("IntentRouter initialized successfully.")

    # ============================================================
    # PUBLIC CLASSIFY METHOD
    # ============================================================

    def classify(self, query: str) -> str:
        if not query or not query.strip():
            logger.warning("Empty query received. Defaulting to general.")
            return "general"

        try:
            # Step 1: Fast Embedding Similarity
            intent, confidence = self._classify_cosine(query)
            logger.debug(f"Cosine classification: {intent} (Score: {confidence:.2f})")

            # Step 2: High Confidence Threshold Check
            if confidence >= self.similarity_threshold:
                return intent

            # Step 3: LLM Fallback
            logger.info(f"Low confidence ({confidence:.2f}). Falling back to LLM.")
            return self._classify_llm(query)

        except Exception:
            logger.exception("Unhandled exception during classify(). Defaulting to general.")
            return "general"

    # ============================================================
    # COSINE SIMILARITY CLASSIFICATION
    # ============================================================

    def _classify_cosine(self, query: str) -> Tuple[str, float]:
        try:
            query_embedding = self.embedder.encode(
                [query],
                normalize_embeddings=True
            )

            best_intent = "general"
            best_score = 0.0

            for intent, proto_embeds in self.prototype_embeddings.items():
                similarities = cosine_similarity(query_embedding, proto_embeds)
                max_similarity = similarities.max()

                if max_similarity > best_score:
                    best_score = max_similarity
                    best_intent = intent

            return best_intent, float(best_score)

        except Exception:
            logger.exception("Cosine similarity classification failed")
            return "general", 0.0

    # ============================================================
    # LLM FALLBACK CLASSIFICATION
    # ============================================================

    def _classify_llm(self, query: str) -> str:

        prompt = f"""
You are a strict query routing system. 
Categorize the following user query into exactly ONE of these labels:
- general
- medical
- book

Respond with ONLY the exact label word. No explanations. No punctuation.

Query: "{query}"
Label:"""

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.llm_model,
                    "prompt": prompt.strip(),
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 5
                    }
                },
                timeout=10
            )

            response.raise_for_status()

            result_text = response.json().get("response", "").strip().lower()

            for intent in self.valid_intents:
                if intent in result_text:
                    return intent

            logger.warning(f"LLM returned unrecognized intent: '{result_text}'. Defaulting to general.")
            return "general"

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM fallback failed: {e}. Defaulting to general.")
            return "general"

        except Exception:
            logger.exception("Unexpected error during LLM fallback")
            return "general"
