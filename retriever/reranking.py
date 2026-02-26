"""
SmartChunk-RAG — Cross-Encoder Reranker

Model:
    cross-encoder/ms-marco-MiniLM-L-12-v2

Features:
- GPU optimized (RTX compatible)
- Mixed precision (FP16 auto if CUDA available)
- Batch processing
- Fail-soft compatible
- Hybrid ready
- Standardized output format preserved
- High accuracy ranking

Author: SmartChunk-RAG System
"""

import torch
from typing import List, Dict
from sentence_transformers import CrossEncoder


class CrossEncoderReranker:
    """
    High-accuracy reranker using Cross-Encoder MiniLM-L-12-v2.
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        batch_size: int = 32
    ):

        print("=" * 80)
        print("[RERANKER] Initializing Cross-Encoder Reranker")
        print("=" * 80)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.batch_size = batch_size

        print(f"[RERANKER] Device     : {self.device}")
        print(f"[RERANKER] Batch Size : {self.batch_size}")
        print(f"[RERANKER] Model      : {model_name}")

        self.model = CrossEncoder(
            model_name,
            device=self.device
        )

        # Enable mixed precision automatically if GPU
        self.use_fp16 = self.device == "cuda"

        print("[RERANKER] Ready")
        print("=" * 80)

    # =====================================================
    # MAIN RERANK FUNCTION
    # =====================================================

    def rerank(
        self,
        query: str,
        candidates: List[Dict],
        top_k: int = 5
    ) -> List[Dict]:
        """
        Rerank candidate chunks based on semantic relevance.

        Args:
            query: User query
            candidates: List of retrieved chunks
            top_k: Number of final results to return

        Returns:
            Reranked top_k results
        """

        if not candidates:
            return []

        # Prepare query-passage pairs
        pairs = [
            (query, c["text"])
            for c in candidates
        ]

        # Batch scoring
        scores = self._predict_scores(pairs)

        # Attach scores
        for idx, score in enumerate(scores):
            candidates[idx]["rerank_score"] = float(score)

        # Sort by rerank score
        candidates.sort(
            key=lambda x: x["rerank_score"],
            reverse=True
        )

        # Keep top_k
        reranked = candidates[:top_k]

        return reranked

    # =====================================================
    # INTERNAL PREDICTION
    # =====================================================

    def _predict_scores(self, pairs):

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