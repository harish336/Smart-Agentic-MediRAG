"""
SmartChunk-RAG — Optimized Vector Retriever

Responsibilities:
- Embed query using VectorEmbedder
- Perform similarity search via ChromaStore
- Convert distance → similarity score
- Apply optional metadata filtering
- Deduplicate results
- Enforce standardized output format
- Respect fail-soft mode
- Optimized for speed & accuracy

Author: SmartChunk-RAG System
"""

from typing import List, Dict, Optional
import hashlib

from retriever.base_retriever import BaseRetriever
from core.vector.embedder import VectorEmbedder
from core.vector.store import ChromaStore
from config.system_loader import get_database_config, get_system_config


class VectorRetriever(BaseRetriever):

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        super().__init__()

        print("=" * 70)
        print("[VECTOR RETRIEVER] Initializing...")
        print("=" * 70)

        self.embedder = VectorEmbedder()
        self.store = ChromaStore()

        db_config = get_database_config()
        vector_cfg = db_config.get("vector_db", {})

        self.distance_metric = (
            vector_cfg.get("collection", {})
            .get("distance_metric", "cosine")
        )

        print(f"[VECTOR RETRIEVER] Distance metric: {self.distance_metric}")
        print("=" * 70)

    # =====================================================
    # CORE RETRIEVAL
    # =====================================================

    def _retrieve_internal(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[Dict]:

        # Step 1: Embed query
        query_embedding = self.embedder.embed_one(query)

        # Step 2: Query Chroma
        raw_results = self.store.query(
            query_embedding=query_embedding,
            top_k=top_k
        )

        if not raw_results:
            return []

        # Step 3: Format results
        formatted = self._format_results(raw_results)

        # Step 4: Apply metadata filtering if provided
        if filters:
            formatted = self._apply_filters(formatted, filters)

        # Step 5: Deduplicate (safety)
        formatted = self.deduplicate(formatted)

        # Step 6: Validate output schema
        return self._validate_output(formatted)

    # =====================================================
    # FORMAT CHROMA RESULTS
    # =====================================================

    def _format_results(self, results: Dict) -> List[Dict]:

        formatted_results = []

        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        for idx in range(len(ids)):

            metadata = metadatas[idx] or {}
            document = documents[idx]
            distance = distances[idx]

            similarity = self._convert_distance_to_score(distance)

            formatted_results.append({
                "chunk_id": metadata.get("chunk_id"),
                "doc_id": metadata.get("doc_id"),
                "score": similarity,
                "source": "vector",
                "text": document,
                "metadata": {
                    "chapter": metadata.get("chapter"),
                    "subheading": metadata.get("subheading"),
                    "page_label": metadata.get("page_label"),
                    "page_physical": metadata.get("page_physical")
                }
            })

        formatted_results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return formatted_results

    # =====================================================
    # DISTANCE → SIMILARITY
    # =====================================================

    def _convert_distance_to_score(self, distance: float) -> float:

        if self.distance_metric == "cosine":
            # Since embeddings are normalized
            return 1 - distance

        if self.distance_metric == "l2":
            return 1 / (1 + distance)

        if self.distance_metric == "ip":
            return float(distance)

        return 1 - distance

    # =====================================================
    # METADATA FILTERING
    # =====================================================

    def _apply_filters(
        self,
        results: List[Dict],
        filters: Dict
    ) -> List[Dict]:

        filtered = []

        for r in results:

            metadata = r.get("metadata", {})

            match = True
            for key, value in filters.items():

                if metadata.get(key) != value:
                    match = False
                    break

            if match:
                filtered.append(r)

        return filtered

    # =====================================================
    # OPTIONAL LIGHTWEIGHT CACHE (FAST + SAFE)
    # =====================================================

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict] = None
    ) -> List[Dict]:

        if not query:
            return []

        # Lightweight hash-based caching
        if self.enable_cache:

            cache_key = hashlib.sha256(
                f"{query}|{top_k}|{filters}".encode()
            ).hexdigest()

            if not hasattr(self, "_local_cache"):
                self._local_cache = {}

            if cache_key in self._local_cache:
                return self._local_cache[cache_key]

            results = super().retrieve(query, top_k, filters)

            # Limit cache size
            if len(self._local_cache) >= self.cache_size:
                self._local_cache.pop(next(iter(self._local_cache)))

            self._local_cache[cache_key] = results
            return results

        return super().retrieve(query, top_k, filters)