import logging
import requests
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import Tuple, Dict, List

# Setup standard logging for production
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

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

        logger.info("[INTENT ROUTER] Initializing embedding model (all-MiniLM-L6-v2)...")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")

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

        # Precompute and normalize embeddings for fast dot-product/cosine comparison
        self.prototype_embeddings = {
            intent: self.embedder.encode(texts, normalize_embeddings=True)
            for intent, texts in self.intent_prototypes.items()
        }

        self.valid_intents = list(self.intent_prototypes.keys())
        logger.info("[INTENT ROUTER] Ready.")

    # ============================================================
    # PUBLIC CLASSIFY METHOD
    # ============================================================

    def classify(self, query: str) -> str:
        if not query or not query.strip():
            return "general"

        # Step 1: Fast Embedding Similarity
        intent, confidence = self._classify_cosine(query)
        logger.debug(f"Cosine classification: {intent} (Score: {confidence:.2f})")

        # Step 2: High Confidence Threshold Check
        if confidence >= self.similarity_threshold:
            return intent

        # Step 3: LLM Fallback for ambiguous queries
        logger.info(f"[INTENT ROUTER] Low confidence ({confidence:.2f}). Falling back to LLM...")
        return self._classify_llm(query)

    # ============================================================
    # COSINE SIMILARITY CLASSIFICATION
    # ============================================================

    def _classify_cosine(self, query: str) -> Tuple[str, float]:
        query_embedding = self.embedder.encode(
            [query], 
            normalize_embeddings=True
        )

        best_intent = "general"
        best_score = 0.0

        for intent, proto_embeds in self.prototype_embeddings.items():
            # Calculate similarity against all prototypes for this intent
            similarities = cosine_similarity(query_embedding, proto_embeds)
            
            # OPTIMIZATION: Use .max() instead of .mean() 
            # We want to know if the query strongly matches AT LEAST ONE prototype
            max_similarity = similarities.max()

            if max_similarity > best_score:
                best_score = max_similarity
                best_intent = intent

        return best_intent, float(best_score)

    # ============================================================
    # LLM FALLBACK CLASSIFICATION
    # ============================================================

    def _classify_llm(self, query: str) -> str:
        # Optimized prompt to force categorization
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
                        "temperature": 0.0, # Zero temperature for deterministic classification
                        "num_predict": 5    # Prevent long hallucinated responses
                    }
                },
                timeout=10 # Fail fast if Ollama is down
            )
            response.raise_for_status() # Catch HTTP errors safely
            
            result_text = response.json().get("response", "").strip().lower()

            # Robust fuzzy parsing: Check if the valid label is *anywhere* in the response
            for intent in self.valid_intents:
                if intent in result_text:
                    return intent

            # If LLM outputs garbage, default to general
            logger.warning(f"LLM returned unrecognized intent: '{result_text}'. Defaulting to general.")
            return "general"

        except requests.exceptions.RequestException as e:
            logger.error(f"[INTENT ROUTER] LLM Fallback failed: {e}. Defaulting to general.")
            return "general"