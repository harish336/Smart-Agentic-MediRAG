"""
Smart MediRAG — Production Graph Retriever
Emotion-aware + Multi-hop + Orchestrator Compatible
"""

from typing import List, Dict, Optional
import re
import spacy

from retriever.base_retriever import BaseRetriever
from core.graph.store import GraphStore
from core.graph.emotion_extractor import EmotionExtractor
from config.system_loader import get_system_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("GraphRetriever", component="retrieval")


class GraphRetriever(BaseRetriever):

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):
        super().__init__()

        self.store = GraphStore()
        self.emotion_extractor = EmotionExtractor()
        self.nlp = spacy.load(
            "en_core_web_sm",
            disable=["parser", "lemmatizer"]
        )
        self.max_hops = 2
        self.max_expanded = 50
        self._concept_cache = {}
        self._concept_cache_limit = 512

        system_config = get_system_config()
        self.fail_soft = system_config["project"].get("fail_soft", True)
        self.max_expanded = system_config.get("retriever", {}).get(
            "graph_max_expanded",
            self.max_expanded
        )

        logger.info("GraphRetriever initialized successfully.")

    # =====================================================
    # REQUIRED ABSTRACT METHOD
    # =====================================================

    def _retrieve_internal(
    self,
    query: str,
    top_k: int,
    filters: Optional[Dict]
) -> List[Dict]:

        try:

            # OPTIONAL doc_id filter
            doc_id = None
            if filters and "doc_id" in filters:
                doc_id = filters["doc_id"]

            # 1️⃣ Extract concepts
            concepts = self._extract_concepts(query)

            if not concepts:
                return []

            # 2️⃣ Detect emotion
            query_emotion = self.emotion_extractor.extract(query)
            if query_emotion == "Neutral":
                query_emotion = None

            # 3️⃣ Primary search
            primary_results = self._keyword_search(
                doc_id=doc_id,
                concepts=concepts,
                emotion=query_emotion,
                top_k=top_k
            )

            # 4️⃣ Multi-hop expansion
            expanded_results = self._expand_multihop(
                primary_results,
                doc_id
            )

            combined = self._deduplicate(primary_results + expanded_results)

            ranked = self._rank_results(
                combined,
                query=query,
                emotion=query_emotion
            )

            return ranked[:top_k]

        except Exception:
            logger.exception("Graph retrieval failed")

            if not self.fail_soft:
                raise

            return []

    # =====================================================
    # CONCEPT EXTRACTION
    # =====================================================

    def _extract_concepts(self, query: str) -> List[str]:

        cached = self._concept_cache.get(query)
        if cached is not None:
            return cached

        doc = self.nlp(query)
        concepts = set()

        for ent in doc.ents:
            if len(ent.text) > 2:
                concepts.add(ent.text.lower())

        for token in doc:
            if token.pos_ in ["NOUN", "PROPN"] and len(token.text) > 3:
                concepts.add(token.text.lower())

        result = list(concepts)

        if len(self._concept_cache) >= self._concept_cache_limit:
            self._concept_cache.pop(next(iter(self._concept_cache)))
        self._concept_cache[query] = result

        return result

    def _build_fulltext_query(self, concepts: List[str]) -> str:

        if not concepts:
            return ""

        terms = []
        for term in concepts:
            cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", term)
            if cleaned:
                terms.append(f"\"{cleaned}\"")

        return " OR ".join(terms)

    # =====================================================
    # PRIMARY GRAPH SEARCH
    # =====================================================

    def _keyword_search(
    self,
    doc_id: Optional[str],
    concepts: List[str],
    emotion: Optional[str],
    top_k: int
) -> List[Dict]:

        fulltext_query = self._build_fulltext_query(concepts)
        records = []

        if fulltext_query:
            records = self.store.fulltext_query_chunks(
                query=fulltext_query,
                limit=top_k * 3,
                doc_id=doc_id,
                emotion=emotion
            )

        if not records:
            cypher = """
            MATCH (c:Chunk)
            OPTIONAL MATCH (c)-[:HAS_EMOTION]->(e:Emotion)
            WHERE
                ($doc_id IS NULL OR c.doc_id = $doc_id)
                AND any(term IN $concepts WHERE toLower(c.text) CONTAINS term)
                AND ($emotion IS NULL OR e.name = $emotion)

            RETURN
                c.chunk_id AS chunk_id,
                c.doc_id AS doc_id,
                c.text AS text,
                e.name AS emotion
            LIMIT $limit
            """

            records = self.store.run_query(
                cypher,
                {
                    "doc_id": doc_id,
                    "concepts": concepts,
                    "emotion": emotion,
                    "limit": top_k
                }
            )

        results = []

        for r in records:
            base_score = r.get("score")
            if base_score is None:
                base_score = 0.6
            else:
                base_score = min(1.0, 0.4 + (base_score / 10.0))

            results.append({
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "text": r.get("text"),
                "score": base_score,
                "graph_score": 1.0,
                "source": "graph_fulltext" if r.get("score") is not None else "graph_keyword",
                "metadata": {
                    "emotion": r.get("emotion")
                }
            })

        return results

    # =====================================================
    # MULTI-HOP EXPANSION
    # =====================================================

    def _expand_multihop(
        self,
        primary_results: List[Dict],
        doc_id: str
    ) -> List[Dict]:

        expanded = []

        seed_ids = [r["chunk_id"] for r in primary_results[:5]]
        if not seed_ids:
            return expanded

        cypher = f"""
        UNWIND $seed_ids AS seed_id
        MATCH (c:Chunk {{chunk_id: seed_id}})
        WHERE ($doc_id IS NULL OR c.doc_id = $doc_id)

        OPTIONAL MATCH (c)-[:NEXT*1..{self.max_hops}]-(neighbor:Chunk)

        WHERE neighbor IS NOT NULL
        AND neighbor.chunk_id <> seed_id
        AND ($doc_id IS NULL OR neighbor.doc_id = $doc_id)

        RETURN DISTINCT
            neighbor.chunk_id AS chunk_id,
            neighbor.doc_id AS doc_id,
            neighbor.text AS text
        LIMIT $limit
        """

        records = self.store.run_query(
            cypher,
            {
                "seed_ids": seed_ids,
                "doc_id": doc_id,
                "limit": self.max_expanded
            }
        )

        for r in records:
            expanded.append({
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "text": r.get("text"),
                "score": 0.7,
                "source": "graph_multihop",
                "metadata": {}
            })

        return expanded

    # =====================================================
    # DEDUPLICATION
    # =====================================================

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:

        seen = set()
        unique = []

        for r in results:
            cid = r["chunk_id"]
            if cid not in seen:
                seen.add(cid)
                unique.append(r)

        return unique

    # =====================================================
    # RANKING
    # =====================================================

    def _rank_results(
    self,
    results: List[Dict],
    query: str,
    emotion: Optional[str]
) -> List[Dict]:

        q = query.lower()

        cleaned_results = []

        for r in results:

            text = r.get("text")

            # 🔥 Skip invalid text rows
            if not text or not isinstance(text, str):
                continue

            text_lower = text.lower()

            # Direct phrase boost
            if q in text_lower:
                r["score"] += 0.5

            # Emotion boost
            if emotion and r.get("metadata", {}).get("emotion") == emotion:
                r["score"] += 0.6

            cleaned_results.append(r)

        cleaned_results.sort(key=lambda x: x["score"], reverse=True)

        return cleaned_results

    # =====================================================
    # REQUIRED BY ORCHESTRATOR
    # =====================================================

    def expand_chunk_context(
        self,
        chunk_id: str,
        doc_id: Optional[str] = None
    ) -> List[Dict]:

        try:
            # Auto resolve doc_id if not provided
            if not doc_id:
                lookup = """
                MATCH (c:Chunk {chunk_id: $chunk_id})
                RETURN c.doc_id AS doc_id
                LIMIT 1
                """

                result = self.store.run_query(
                    lookup,
                    {"chunk_id": chunk_id}
                )

                if not result:
                    return []

                doc_id = result[0]["doc_id"]

            return self._expand_multihop(
                [{"chunk_id": chunk_id}],
                doc_id
            )

        except Exception:
            logger.exception("expand_chunk_context failed")

            if not self.fail_soft:
                raise

            return []
