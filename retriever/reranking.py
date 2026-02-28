"""
SmartChunk-RAG — Cross-Encoder Reranker (Production Hybrid Version)
"""

import torch
from typing import List, Dict, Optional
from sentence_transformers import CrossEncoder

from core.utils.logging_utils import get_component_logger

# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("CrossEncoderReranker", component="retrieval")


# =====================================================
# LAZY SINGLETON MODEL
# =====================================================

_cross_encoder_instance: Optional[CrossEncoder] = None


def get_cross_encoder(model_name: str, device: str) -> CrossEncoder:
    global _cross_encoder_instance

    if _cross_encoder_instance is None:
        try:
            logger.info("Loading CrossEncoder model (lazy load)...")

            _cross_encoder_instance = CrossEncoder(
                model_name,
                device=device
            )

            logger.info("CrossEncoder model loaded successfully.")

        except Exception:
            logger.exception("Failed to load CrossEncoder model")
            raise

    return _cross_encoder_instance


# =====================================================
# MAIN RERANKER CLASS
# =====================================================

class CrossEncoderReranker:
    """
    Hybrid-aware Cross-Encoder reranker.
    Designed for production RAG systems.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        batch_size: int = 16,
        max_text_length: int = 800
    ):

        logger.info("=" * 80)
        logger.info("Initializing Cross-Encoder Reranker")
        logger.info("=" * 80)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.batch_size = batch_size
        self.max_text_length = max_text_length

        logger.info(f"Device     : {self.device}")
        logger.info(f"Batch Size : {self.batch_size}")
        logger.info(f"Model      : {model_name}")

        try:
            self.model = get_cross_encoder(model_name, self.device)
        except Exception:
            logger.exception("Reranker initialization failed")
            raise

        self.use_fp16 = self.device == "cuda"

        logger.info("Cross-Encoder Reranker Ready")
        logger.info("=" * 80)

    # =====================================================
    # MAIN RERANK FUNCTION
    # =====================================================

    def rerank(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int = 15
    ) -> List[Dict]:

        if not candidates:
            logger.debug("No candidates provided for reranking.")
            return []

        try:

            # --------------------------------------------------
            # 1️⃣ Clean + Truncate Candidates
            # --------------------------------------------------

            clean_candidates = []

            for c in candidates:

                text = c.get("text")

                if not text or not isinstance(text, str):
                    continue

                # Truncate overly long text
                c["text"] = text[:self.max_text_length]

                clean_candidates.append(c)

            if not clean_candidates:
                logger.warning("All candidates invalid after filtering.")
                return []

            # --------------------------------------------------
            # 2️⃣ Build Query-Document Pairs
            # --------------------------------------------------

            pairs = [
                (query, c["text"])
                for c in clean_candidates
            ]

            # --------------------------------------------------
            # 3️⃣ Predict Scores
            # --------------------------------------------------

            scores = self._predict_scores(pairs)

            # --------------------------------------------------
            # 4️⃣ Attach Scores
            # --------------------------------------------------

            for idx, score in enumerate(scores):
                clean_candidates[idx]["rerank_score"] = float(score)

            # --------------------------------------------------
            # 5️⃣ Sort by Rerank Score
            # --------------------------------------------------

            clean_candidates.sort(
                key=lambda x: x["rerank_score"],
                reverse=True
            )

            return clean_candidates[:top_k]

        except Exception:
            logger.exception("Reranking failed — returning original order")
            return candidates[:top_k]

    # =====================================================
    # INTERNAL SCORE PREDICTION
    # =====================================================

    def _predict_scores(self, pairs):

        try:

            if self.use_fp16:
                with torch.cuda.amp.autocast():
                    scores = self.model.predict(
                        pairs,
                        batch_size=self.batch_size,
                        convert_to_numpy=True
                    )
            else:
                scores = self.model.predict(
                    pairs,
                    batch_size=self.batch_size,
                    convert_to_numpy=True
                )

            return scores

        except Exception:
            logger.exception("Score prediction failed")
            raise
