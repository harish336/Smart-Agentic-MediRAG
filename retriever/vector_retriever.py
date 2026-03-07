"""
SmartChunk-RAG — Optimized Vector Retriever (Clean Version)
"""

from typing import List, Dict, Optional
import hashlib

from retriever.base_retriever import BaseRetriever
from core.vector.embedder import VectorEmbedder
from core.vector.store import ChromaStore
from config.system_loader import get_database_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("VectorRetriever", component="retrieval")


class VectorRetriever(BaseRetriever):

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        super().__init__()

        logger.info("=" * 70)
        logger.info("Initializing VectorRetriever...")
        logger.info("=" * 70)

        try:
            self.embedder = VectorEmbedder()
            self.store = ChromaStore()
            self.user_stores = {}

            db_config = get_database_config()
            vector_cfg = db_config.get("vector_db", {})

            self.distance_metric = (
                vector_cfg.get("collection", {})
                .get("distance_metric", "cosine")
            )

            self.min_score_threshold = vector_cfg.get(
                "min_similarity_score", 0.0
            )

            logger.info(f"Distance metric: {self.distance_metric}")
            logger.info("=" * 70)

        except Exception:
            logger.exception("Failed to initialize VectorRetriever")
            raise

    # =====================================================
    # CORE RETRIEVAL
    # =====================================================

    def _retrieve_internal(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[Dict]:

        try:
            # Embed query
            query_embedding = self.embedder.embed_one(query)

            owner_user_id = None
            if filters and filters.get("owner_user_id"):
                owner_user_id = str(filters.get("owner_user_id")).strip()

            # Query base/global store first
            all_formatted = []
            raw_results = self.store.query(query_embedding=query_embedding, top_k=top_k)
            if raw_results:
                all_formatted.extend(self._format_results(raw_results))

            # Query user-private store when owner filter is present.
            if owner_user_id:
                user_store = self._get_user_store(owner_user_id)
                raw_user_results = user_store.query(query_embedding=query_embedding, top_k=top_k)
                if raw_user_results:
                    all_formatted.extend(self._format_results(raw_user_results))

            if not all_formatted:
                return []

            formatted = all_formatted

            # Apply similarity threshold
            if self.min_score_threshold > 0:
                formatted = [
                    r for r in formatted
                    if r["score"] >= self.min_score_threshold
                ]

            # Apply metadata filtering
            if filters:
                filtered_copy = {k: v for k, v in filters.items() if k != "owner_user_id"}
                if filtered_copy:
                    formatted = self._apply_filters(formatted, filtered_copy)

            # IMPORTANT:
            # Do NOT deduplicate or validate here.
            # BaseRetriever handles that.

            return formatted

        except Exception:
            logger.exception("Vector retrieval failed")

            if not self.fail_soft:
                raise

            return []

    def _get_user_store(self, owner_user_id: str) -> ChromaStore:
        cached = self.user_stores.get(owner_user_id)
        if cached is not None:
            return cached
        store = ChromaStore(collection_name=f"smart_chunks_user_{owner_user_id}")
        self.user_stores[owner_user_id] = store
        return store

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
                    "page_type": metadata.get("page_type"),
                    "page_label": metadata.get("page_label"),
                    "page_physical": metadata.get("page_physical")
                }
            })

        return formatted_results

    # =====================================================
    # DISTANCE → SIMILARITY
    # =====================================================

    def _convert_distance_to_score(self, distance: float) -> float:

        try:
            if self.distance_metric == "cosine":
                return 1 - distance

            if self.distance_metric == "l2":
                return 1 / (1 + distance)

            if self.distance_metric == "ip":
                return float(distance)

            return 1 - distance

        except Exception:
            logger.exception("Distance conversion failed")
            return 0.0

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
    # LIGHTWEIGHT CACHE (OPTIONAL)
    # =====================================================

    def retrieve(
        self,
        query: str,
        top_k: int = 15,
        filters: Optional[Dict] = None
    ) -> List[Dict]:

        if not query:
            return []

        try:
            if self.enable_cache:

                cache_key = hashlib.sha256(
                    f"{query}|{top_k}|{filters}".encode()
                ).hexdigest()

                if not hasattr(self, "_local_cache"):
                    self._local_cache = {}

                if cache_key in self._local_cache:
                    return self._local_cache[cache_key]

                results = super().retrieve(query, top_k, filters)

                if len(self._local_cache) >= self.cache_size:
                    self._local_cache.pop(next(iter(self._local_cache)))

                self._local_cache[cache_key] = results
                return results

            return super().retrieve(query, top_k, filters)

        except Exception:
            logger.exception("VectorRetriever retrieve() failed")

            if not self.fail_soft:
                raise

            return []
