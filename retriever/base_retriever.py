"""
SmartChunk-RAG — Base Retriever (Corrected Core Version)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import hashlib

from config.system_loader import get_system_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("BaseRetriever", component="retrieval")


class BaseRetriever(ABC):
    """
    Abstract base retriever.
    Enforces:
        - Validation
        - Sorting
        - Deduplication
        - Top-k trimming
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        try:
            system_config = get_system_config()

            self.fail_soft = system_config["project"].get("fail_soft", True)

            performance_cfg = system_config.get("performance", {})
            self.enable_cache = performance_cfg.get("enable_caching", False)
            self.cache_size = performance_cfg.get("cache_size", 512)

            logger.info(
                f"{self.__class__.__name__} initialized "
                f"(fail_soft={self.fail_soft}, caching={self.enable_cache})"
            )

        except Exception:
            logger.exception("Failed to initialize BaseRetriever")
            raise

    # =====================================================
    # PUBLIC RETRIEVE ENTRY (UNIFIED PIPELINE)
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

            # Raw retrieval
            results = self._retrieve_internal(query, top_k, filters)

            if not results:
                return []

            # Validate schema
            results = self._validate_output(results)

            if not results:
                return []

            # Deduplicate
            results = self.deduplicate(results)

            # Sort by score (safety)
            results.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            # Trim to top_k
            return results[:top_k]

        except Exception as e:

            logger.exception(
                f"{self.__class__.__name__} retrieval error"
            )

            if not self.fail_soft:
                raise e

            return []

    # =====================================================
    # INTERNAL RETRIEVE (Child must implement)
    # =====================================================

    @abstractmethod
    def _retrieve_internal(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[Dict]:
        pass

    # =====================================================
    # OUTPUT VALIDATION
    # =====================================================

    def _validate_output(self, results: List[Dict]) -> List[Dict]:

        validated = []

        for r in results:

            if not isinstance(r, dict):
                continue

            required_keys = {
                "chunk_id",
                "doc_id",
                "score",
                "source",
                "text",
                "metadata"
            }

            if not required_keys.issubset(r.keys()):
                continue

            try:
                r["score"] = float(r["score"])
            except Exception:
                continue

            validated.append(r)

        return validated

    # =====================================================
    # HYBRID-SAFE DEDUPLICATION
    # =====================================================

    def deduplicate(self, results: List[Dict]) -> List[Dict]:

        best = {}

        for r in results:
            unique_key = (r["doc_id"], r["chunk_id"])

            if unique_key not in best:
                best[unique_key] = r
            else:
                if r["score"] > best[unique_key]["score"]:
                    best[unique_key] = r

        return list(best.values())

    # =====================================================
    # CACHE KEY (Optional future use)
    # =====================================================

    def _cache_key(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> str:

        key_string = f"{query}|{top_k}|{filters}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    # =====================================================
    # OPTIONAL ASYNC SUPPORT
    # =====================================================

    async def retrieve_async(
        self,
        query: str,
        top_k: int = 15,
        filters: Optional[Dict] = None
    ) -> List[Dict]:

        return self.retrieve(query, top_k, filters)
