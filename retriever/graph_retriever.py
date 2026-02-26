"""
Smart Medirag — Advanced Graph Retriever

Features:
- Keyword-based search
- Multi-hop expansion via NEXT
- Structured metadata return
- Emotion-aware
- Production-safe
- Orchestrator compatible

Author: Smart Medirag System
"""

from typing import List, Dict, Optional
from retriever.base_retriever import BaseRetriever
from core.graph.store import GraphStore
from config.system_loader import get_system_config


class GraphRetriever(BaseRetriever):

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        super().__init__()

        print("=" * 70)
        print("[GRAPH RETRIEVER] Initializing...")
        print("=" * 70)

        self.store = GraphStore()
        self.max_hops = 2

        system_config = get_system_config()
        self.fail_soft = system_config["project"].get("fail_soft", True)

        print("[GRAPH RETRIEVER] Ready")
        print("=" * 70)

    # =====================================================
    # MAIN RETRIEVE ENTRY
    # =====================================================

    def _retrieve_internal(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[Dict]:

        try:

            results = self._keyword_search(query, top_k)

            if filters:
                results = self._apply_filters(results, filters)

            results = self.deduplicate(results)

            return self._validate_output(results)

        except Exception as e:

            print("[GRAPH RETRIEVER ERROR]", e)

            if not self.fail_soft:
                raise e

            return []

    # =====================================================
    # KEYWORD SEARCH
    # =====================================================

    def _keyword_search(self, query: str, top_k: int) -> List[Dict]:

        cypher = """
        MATCH (c:Chunk)
        WHERE toLower(c.text) CONTAINS toLower($query)

        OPTIONAL MATCH (s:Subheading)-[:HAS_CHUNK]->(c)
        OPTIONAL MATCH (ch:Chapter)-[:HAS_SUBHEADING]->(s)
        OPTIONAL MATCH (c)-[:HAS_EMOTION]->(e:Emotion)

        RETURN
            c.chunk_id AS chunk_id,
            c.doc_id AS doc_id,
            c.text AS text,
            c.page_label AS page_label,
            c.page_physical AS page_physical,
            ch.name AS chapter,
            s.name AS subheading,
            e.name AS emotion
        LIMIT $limit
        """

        records = self.store.run_query(
            cypher,
            {"query": query, "limit": top_k}
        )

        results = []

        for r in records:

            results.append({
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "score": 1.0,
                "source": "graph_keyword",
                "text": r.get("text"),
                "metadata": {
                    "chapter": r.get("chapter"),
                    "subheading": r.get("subheading"),
                    "page_label": r.get("page_label"),
                    "page_physical": r.get("page_physical"),
                    "emotion": r.get("emotion")
                }
            })

        return results

    # =====================================================
    # MULTI-HOP CONTEXT EXPANSION
    # =====================================================

    def expand_chunk_context(self, chunk_id: str) -> List[Dict]:
        """
        Expands context using NEXT relationships.
        Used by Hybrid Retrieval.
        """

        cypher = f"""
        MATCH (c:Chunk {{chunk_id: $chunk_id}})
        OPTIONAL MATCH (c)-[:NEXT*1..{self.max_hops}]-(neighbor:Chunk)

        OPTIONAL MATCH (s:Subheading)-[:HAS_CHUNK]->(neighbor)
        OPTIONAL MATCH (ch:Chapter)-[:HAS_SUBHEADING]->(s)
        OPTIONAL MATCH (neighbor)-[:HAS_EMOTION]->(e:Emotion)

        RETURN DISTINCT
            neighbor.chunk_id AS chunk_id,
            neighbor.doc_id AS doc_id,
            neighbor.text AS text,
            neighbor.page_label AS page_label,
            neighbor.page_physical AS page_physical,
            ch.name AS chapter,
            s.name AS subheading,
            e.name AS emotion
        """

        records = self.store.run_query(
            cypher,
            {"chunk_id": chunk_id}
        )

        results = []

        for r in records:

            if not r.get("chunk_id"):
                continue

            results.append({
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "score": 0.8,
                "source": "graph_multihop",
                "text": r.get("text"),
                "metadata": {
                    "chapter": r.get("chapter"),
                    "subheading": r.get("subheading"),
                    "page_label": r.get("page_label"),
                    "page_physical": r.get("page_physical"),
                    "emotion": r.get("emotion")
                }
            })

        return results

    # =====================================================
    # OPTIONAL FILTER
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