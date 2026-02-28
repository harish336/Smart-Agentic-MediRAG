"""
SmartChunk-RAG — Retriever Orchestrator (Clean Production Version)
"""

from typing import List, Dict, Optional

from retriever.vector_retriever import VectorRetriever
from retriever.graph_retriever import GraphRetriever
from retriever.reranking import CrossEncoderReranker
from config.system_loader import get_system_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("RetrieverOrchestrator", component="retrieval")


class RetrieverOrchestrator:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        logger.info("=" * 80)
        logger.info("Initializing RetrieverOrchestrator...")
        logger.info("=" * 80)

        try:
            self.vector_retriever = VectorRetriever()
            self.graph_retriever = GraphRetriever()
            self.reranker = CrossEncoderReranker()

            system_config = get_system_config()
            self.fail_soft = system_config["project"].get("fail_soft", True)

            logger.info("RetrieverOrchestrator Ready")
            logger.info("=" * 80)

        except Exception:
            logger.exception("Failed to initialize RetrieverOrchestrator")
            raise

    # =====================================================
    # MAIN RETRIEVE ENTRY (SINGLE VERSION)
    # =====================================================

    def retrieve(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 8,
        initial_k: int = 15,
        filters: Optional[Dict] = None
    ) -> List[Dict]:

        try:
            logger.info(
                "Retrieval request | query=%r mode=%s top_k=%d initial_k=%d filters=%s",
                query,
                mode,
                top_k,
                initial_k,
                filters
            )

            # ---------------------------------------------
            # Retrieve Candidates
            # ---------------------------------------------

            if mode == "vector":
                candidates = self.vector_retriever.retrieve(
                    query, top_k=initial_k, filters=filters
                )
                logger.info(
                    "Vector candidates: %d | preview=%s",
                    len(candidates),
                    self._summarize_results(candidates)
                )

            elif mode == "graph":
                candidates = self.graph_retriever.retrieve(
                    query, top_k=initial_k, filters=filters
                )
                logger.info(
                    "Graph candidates: %d | preview=%s",
                    len(candidates),
                    self._summarize_results(candidates)
                )

            else:
                candidates = self._hybrid_retrieve(
                    query, initial_k, filters
                )
                logger.info(
                    "Hybrid candidates: %d | preview=%s",
                    len(candidates),
                    self._summarize_results(candidates)
                )

            if not candidates:
                logger.info("No candidates returned for query=%r", query)
                return []

            # ---------------------------------------------
            # Deduplicate (doc_id + chunk_id)
            # ---------------------------------------------

            candidates = self._deduplicate(candidates)
            logger.info(
                "Deduplicated candidates: %d | preview=%s",
                len(candidates),
                self._summarize_results(candidates)
            )

            # ---------------------------------------------
            # Optional Structure Enrichment
            # ---------------------------------------------

            candidates = self._ensure_structure(candidates)

            # ---------------------------------------------
            # Rerank
            # ---------------------------------------------

            reranked = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k
            )
            logger.info(
                "Reranked results: %d | preview=%s",
                len(reranked),
                self._summarize_results(reranked, include_rerank=True)
            )

            return reranked

        except Exception:
            logger.exception("RetrieverOrchestrator retrieve() failed")

            if not self.fail_soft:
                raise

            logger.warning("Fail-soft enabled — returning empty list")
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

        try:

            vector_results = self.vector_retriever.retrieve(
                query,
                top_k=initial_k,
                filters=filters
            )

            graph_keyword = self.graph_retriever.retrieve(
                query,
                top_k=initial_k,
                filters=filters
            )

            graph_expanded = []

            for r in vector_results[:10]:
                expanded = self.graph_retriever.expand_chunk_context(
                    r["chunk_id"]
                )
                graph_expanded.extend(expanded)

            merged = (
                vector_results +
                graph_keyword +
                graph_expanded
            )

            logger.info(
                "Hybrid breakdown | vector=%d graph_keyword=%d graph_expanded=%d total=%d",
                len(vector_results),
                len(graph_keyword),
                len(graph_expanded),
                len(merged)
            )

            return merged

        except Exception:
            logger.exception("Hybrid retrieval failed")

            if not self.fail_soft:
                raise

            return []

    # =====================================================
    # STRUCTURAL ENRICHMENT
    # =====================================================

    def _ensure_structure(self, results: List[Dict]) -> List[Dict]:

        enriched = []

        for r in results:

            metadata = r.get("metadata", {})

            if metadata.get("chapter") and metadata.get("subheading"):
                enriched.append(r)
                continue

            try:
                if hasattr(self.graph_retriever, "get_structure"):
                    structure = self.graph_retriever.get_structure(
                        r["chunk_id"]
                    )

                    if structure:
                        metadata["chapter"] = structure.get("chapter")
                        metadata["subheading"] = structure.get("subheading")

                        r["metadata"] = metadata

            except Exception:
                logger.debug(
                    f"Structure enrichment failed for {r.get('chunk_id')}"
                )

            enriched.append(r)

        return enriched

    # =====================================================
    # DEDUPLICATION
    # =====================================================

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:

        best = {}

        for r in results:

            unique_key = (r.get("doc_id"), r.get("chunk_id"))

            if unique_key not in best:
                best[unique_key] = r
            else:
                if r.get("score", 0) > best[unique_key].get("score", 0):
                    best[unique_key] = r

        return list(best.values())

    # =====================================================
    # LOGGING HELPERS
    # =====================================================

    def _summarize_results(
        self,
        results: List[Dict],
        limit: int = 10,
        include_rerank: bool = False
    ) -> List[Dict]:

        summary = []

        for r in results[:limit]:
            item = {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "source": r.get("source"),
                "score": round(float(r.get("score", 0.0)), 4)
            }
            if include_rerank and "rerank_score" in r:
                item["rerank_score"] = round(
                    float(r.get("rerank_score", 0.0)),
                    4
                )
            summary.append(item)

        return summary
