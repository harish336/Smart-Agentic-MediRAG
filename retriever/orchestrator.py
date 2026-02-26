"""
SmartChunk-RAG — Retriever Orchestrator (Enhanced)

Enhancements:
- Structural enrichment for all results
- Consistent metadata format
- Hybrid-safe merging
- Production-ready

Author: SmartChunk-RAG System
"""

from typing import List, Dict, Optional

from retriever.vector_retriever import VectorRetriever
from retriever.graph_retriever import GraphRetriever
from retriever.reranking import CrossEncoderReranker
from config.system_loader import get_system_config


class RetrieverOrchestrator:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        print("=" * 80)
        print("[RETRIEVER ORCHESTRATOR] Initializing...")
        print("=" * 80)

        self.vector_retriever = VectorRetriever()
        self.graph_retriever = GraphRetriever()
        self.reranker = CrossEncoderReranker()

        system_config = get_system_config()
        self.fail_soft = system_config["project"].get("fail_soft", True)

        print("[RETRIEVER ORCHESTRATOR] Ready")
        print("=" * 80)

    # =====================================================
    # MAIN ENTRY
    # =====================================================

    def retrieve(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 5,
        initial_k: int = 20,
        filters: Optional[Dict] = None
    ) -> List[Dict]:

        try:

            # ---------------------------
            # Step 1: Initial Retrieval
            # ---------------------------

            if mode == "vector":
                candidates = self.vector_retriever.retrieve(
                    query, top_k=initial_k, filters=filters
                )

            elif mode == "graph":
                candidates = self.graph_retriever.retrieve(
                    query, top_k=initial_k, filters=filters
                )

            else:  # HYBRID
                candidates = self._hybrid_retrieve(
                    query, initial_k, filters
                )

            if not candidates:
                return []

            # ---------------------------
            # Step 2: Structural Enrichment
            # ---------------------------

            candidates = self._ensure_structure(candidates)

            # ---------------------------
            # Step 3: Rerank
            # ---------------------------

            reranked = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k
            )

            return reranked

        except Exception as e:

            print("[RETRIEVER ORCHESTRATOR ERROR]", e)

            if not self.fail_soft:
                raise e

            return []

    # =====================================================
    # HYBRID RETRIEVAL
    # =====================================================

    def _hybrid_retrieve(
        self,
        query: str,
        initial_k: int,
        filters: Optional[Dict]
    ) -> List[Dict]:

        vector_results = self.vector_retriever.retrieve(
            query,
            top_k=initial_k,
            filters=filters
        )

        graph_expanded = []

        for r in vector_results:
            expanded = self.graph_retriever.expand_chunk_context(
                r["chunk_id"]
            )
            graph_expanded.extend(expanded)

        graph_keyword = self.graph_retriever.retrieve(
            query,
            top_k=initial_k // 2,
            filters=filters
        )

        merged = (
            vector_results +
            graph_expanded +
            graph_keyword
        )

        return self._deduplicate(merged)

    # =====================================================
    # STRUCTURAL ENRICHMENT
    # =====================================================

    def _ensure_structure(self, results: List[Dict]) -> List[Dict]:
        """
        Ensures chapter and subheading always exist.
        If missing, fetch from graph.
        """

        enriched = []

        for r in results:

            metadata = r.get("metadata", {})

            if metadata.get("chapter") and metadata.get("subheading"):
                enriched.append(r)
                continue

            # Fetch from graph if missing
            structure = self.graph_retriever.get_structure(
                r["chunk_id"]
            )

            if structure:
                metadata["chapter"] = structure.get("chapter")
                metadata["subheading"] = structure.get("subheading")

            r["metadata"] = metadata
            enriched.append(r)

        return enriched

    # =====================================================
    # DEDUPLICATION
    # =====================================================

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:

        best = {}

        for r in results:
            cid = r["chunk_id"]

            if cid not in best:
                best[cid] = r
            else:
                if r.get("score", 0) > best[cid].get("score", 0):
                    best[cid] = r

        return list(best.values())
    
    def retrieve(
    self,
    query: str,
    mode: str = "hybrid",
    top_k: int = 5,
    initial_k: int = 20,
    filters: Optional[Dict] = None
) -> List[Dict]:

        try:

            if mode == "vector":
                candidates = self.vector_retriever.retrieve(
                    query, top_k=initial_k, filters=filters
                )

            elif mode == "graph":
                candidates = self.graph_retriever.retrieve(
                    query, top_k=initial_k, filters=filters
                )

            else:
                candidates = self._hybrid_retrieve(
                    query, initial_k, filters
                )

            if not candidates:
                return []

            reranked = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k
            )

            return reranked

        except Exception as e:

            print("[RETRIEVER ORCHESTRATOR ERROR]", e)

            if not self.fail_soft:
                raise e

            return []