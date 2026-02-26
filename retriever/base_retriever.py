"""
SmartChunk-RAG — Base Retriever

Responsibilities:
- Define unified retriever interface
- Enforce standardized output schema
- Provide optional LRU caching
- Provide fail-soft safety wrapper
- Support performance config
- Enable future async support

Author: SmartChunk-RAG System
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from functools import lru_cache
import hashlib

from config.system_loader import get_system_config


class BaseRetriever(ABC):
    """
    Abstract base retriever class.

    All retrievers (Vector, Graph, Hybrid) must inherit from this.

    Enforces:
        - Standard output format
        - Caching support
        - Fail-soft compatibility
    """

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        system_config = get_system_config()

        self.fail_soft = system_config["project"].get("fail_soft", True)

        performance_cfg = system_config.get("performance", {})

        self.enable_cache = performance_cfg.get("enable_caching", False)
        self.cache_size = performance_cfg.get("cache_size", 512)

    # =====================================================
    # PUBLIC RETRIEVE ENTRY
    # =====================================================

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Public safe wrapper for retrieval.

        Applies:
            - Input validation
            - Optional caching
            - Fail-soft handling
        """

        if not query:
            return []

        try:
            if self.enable_cache:
                return self._cached_retrieve(
                    self._cache_key(query, top_k, filters)
                )

            return self._retrieve_internal(query, top_k, filters)

        except Exception as e:

            print(f"[{self.__class__.__name__}] Retrieval error:", e)

            if not self.fail_soft:
                raise e

            print(
                f"[{self.__class__.__name__}] "
                "Fail-soft enabled — returning empty list"
            )
            return []

    # =====================================================
    # INTERNAL RETRIEVE (Must be implemented)
    # =====================================================

    @abstractmethod
    def _retrieve_internal(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[Dict]:
        """
        Core retrieval logic implemented by child classes.
        Must return standardized output format.
        """
        pass

    # =====================================================
    # STANDARD OUTPUT VALIDATION
    # =====================================================

    def _validate_output(self, results: List[Dict]) -> List[Dict]:
        """
        Ensures output matches required schema.

        Required keys:
            - chunk_id
            - doc_id
            - score
            - source
            - text
            - metadata
        """

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

            if not required_keys.issubset(set(r.keys())):
                continue

            # Ensure numeric score
            try:
                r["score"] = float(r["score"])
            except Exception:
                continue

            validated.append(r)

        # Sort by score descending
        validated.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return validated

    # =====================================================
    # CACHING SYSTEM
    # =====================================================

    def _cache_key(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> str:
        """
        Generate deterministic cache key.
        """

        key_string = f"{query}|{top_k}|{filters}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    @lru_cache(maxsize=1024)
    def _cached_retrieve(self, cache_key: str) -> Tuple[Dict]:
        """
        Cached wrapper around internal retrieval.
        """

        # Decode cache key not needed — only used as identifier
        # We recompute actual retrieval without decoding.
        # Caching is based on key uniqueness.

        # Extract parameters by calling internal retrieve again
        # We cannot reverse the key — so we re-call with stored parameters
        # Instead, override in child if needed for advanced caching

        raise NotImplementedError(
            "Child retriever must override caching logic "
            "if enable_cache=True"
        )

    # =====================================================
    # PERFORMANCE OPTIMIZATION HELPERS
    # =====================================================

    def deduplicate(self, results: List[Dict]) -> List[Dict]:
        """
        Remove duplicate chunk_ids.
        Keeps highest score.
        """

        seen = {}
        for r in results:
            cid = r["chunk_id"]
            if cid not in seen or r["score"] > seen[cid]["score"]:
                seen[cid] = r

        return list(seen.values())

    # =====================================================
    # OPTIONAL ASYNC SUPPORT (Future Extension)
    # =====================================================

    async def retrieve_async(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Async-ready interface for future scalability.
        """
        return self.retrieve(query, top_k, filters)