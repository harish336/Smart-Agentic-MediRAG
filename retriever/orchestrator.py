"""
SmartChunk-RAG - Retriever Orchestrator
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from config.system_loader import get_system_config
from core.utils.logging_utils import get_component_logger
from retriever.graph_retriever import GraphRetriever
from retriever.reranking import CrossEncoderReranker
from retriever.vector_retriever import VectorRetriever


logger = get_component_logger("RetrieverOrchestrator", component="retrieval")


class RetrieverOrchestrator:
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
            self.max_query_variants = int(
                system_config.get("retrieval", {}).get("query_variants", 1)
            )

            logger.info("RetrieverOrchestrator Ready")
            logger.info("=" * 80)
        except Exception:
            logger.exception("Failed to initialize RetrieverOrchestrator")
            raise

    def retrieve(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 8,
        initial_k: int = 15,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        try:
            logger.info(
                "Retrieval request | query=%r mode=%s top_k=%d initial_k=%d filters=%s",
                query,
                mode,
                top_k,
                initial_k,
                filters,
            )

            if mode == "vector":
                candidates = self._retrieve_with_variants(
                    retriever="vector",
                    query=query,
                    initial_k=initial_k,
                    filters=filters,
                )
            elif mode == "graph":
                candidates = self._retrieve_with_variants(
                    retriever="graph",
                    query=query,
                    initial_k=initial_k,
                    filters=filters,
                )
            else:
                candidates = self._hybrid_retrieve(query, initial_k, filters)

            logger.info(
                "%s candidates: %d | preview=%s",
                mode.capitalize(),
                len(candidates),
                self._summarize_results(candidates),
            )

            if not candidates:
                logger.info("No candidates returned for query=%r", query)
                return []

            candidates = self._deduplicate(candidates)
            candidates = self._ensure_structure(candidates)
            candidates = self._apply_doc_scope(candidates, filters)
            candidates = self._boost_lexical_alignment(query, candidates)
            candidates = self._boost_chunk_structure(query, candidates)

            reranked = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k,
            )

            logger.info(
                "Reranked results: %d | preview=%s",
                len(reranked),
                self._summarize_results(reranked, include_rerank=True),
            )
            return reranked

        except Exception:
            logger.exception("RetrieverOrchestrator retrieve() failed")
            if not self.fail_soft:
                raise
            logger.warning("Fail-soft enabled - returning empty list")
            return []

    def _retrieve_with_variants(
        self,
        retriever: str,
        query: str,
        initial_k: int,
        filters: Optional[Dict],
    ) -> List[Dict]:
        queries = self._expand_query_variants(query)
        if not queries:
            return []

        results: List[Dict] = []

        max_workers = min(4, len(queries))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for q in queries:
                if retriever == "vector":
                    futures.append(
                        executor.submit(
                            self.vector_retriever.retrieve,
                            q,
                            initial_k,
                            filters,
                        )
                    )
                else:
                    futures.append(
                        executor.submit(
                            self.graph_retriever.retrieve,
                            q,
                            initial_k,
                            filters,
                        )
                    )

            for fut in as_completed(futures):
                results.extend(fut.result() or [])

        return self._deduplicate(results)

    def _hybrid_retrieve(
        self,
        query: str,
        initial_k: int,
        filters: Optional[Dict],
    ) -> List[Dict]:
        try:
            queries = self._expand_query_variants(query)
            vector_results: List[Dict] = []
            graph_keyword: List[Dict] = []

            with ThreadPoolExecutor(max_workers=min(6, len(queries) * 2)) as executor:
                future_source = {}
                for q in queries:
                    fut_vec = executor.submit(
                        self.vector_retriever.retrieve,
                        q,
                        initial_k,
                        filters,
                    )
                    fut_graph = executor.submit(
                        self.graph_retriever.retrieve,
                        q,
                        initial_k,
                        filters,
                    )
                    future_source[fut_vec] = "vector"
                    future_source[fut_graph] = "graph"

                for fut in as_completed(future_source):
                    output = fut.result() or []
                    if future_source[fut] == "vector":
                        vector_results.extend(output)
                    else:
                        graph_keyword.extend(output)

            vector_results = self._deduplicate(vector_results)
            graph_keyword = self._deduplicate(graph_keyword)

            expansion_seed = self._deduplicate(vector_results + graph_keyword)[:8]
            graph_expanded: List[Dict] = []

            if expansion_seed:
                owner_user_id = None
                if filters and filters.get("owner_user_id"):
                    owner_user_id = str(filters.get("owner_user_id")).strip() or None
                with ThreadPoolExecutor(max_workers=min(4, len(expansion_seed))) as executor:
                    expand_jobs = [
                        executor.submit(
                            self.graph_retriever.expand_chunk_context,
                            seed["chunk_id"],
                            seed.get("doc_id"),
                            owner_user_id,
                        )
                        for seed in expansion_seed
                        if seed.get("chunk_id")
                    ]
                    for fut in as_completed(expand_jobs):
                        graph_expanded.extend(fut.result() or [])

            merged = vector_results + graph_keyword + graph_expanded
            merged = self._apply_source_weights(merged)
            merged = self._deduplicate(merged)

            logger.info(
                "Hybrid breakdown | vector=%d graph_keyword=%d graph_expanded=%d total=%d",
                len(vector_results),
                len(graph_keyword),
                len(graph_expanded),
                len(merged),
            )
            return merged
        except Exception:
            logger.exception("Hybrid retrieval failed")
            if not self.fail_soft:
                raise
            return []

    def _apply_source_weights(self, results: List[Dict]) -> List[Dict]:
        source_weights = {
            "vector": 1.0,
            "graph_keyword": 1.03,
            "graph_fulltext": 1.06,
            "graph_multihop": 0.96,
        }

        boosted = []
        for r in results:
            item = dict(r)
            source = item.get("source", "vector")
            base = float(item.get("score", 0.0))
            item["score"] = base * source_weights.get(source, 1.0)
            boosted.append(item)
        return boosted

    def _apply_doc_scope(self, results: List[Dict], filters: Optional[Dict]) -> List[Dict]:
        if not results or not filters:
            return results

        raw_doc_ids = filters.get("doc_ids")
        if not isinstance(raw_doc_ids, list):
            return results

        allowed = {str(doc_id).strip() for doc_id in raw_doc_ids if str(doc_id).strip()}
        if not allowed:
            return results

        scoped = [item for item in results if str(item.get("doc_id") or "").strip() in allowed]
        logger.info("Doc scope filter applied | before=%d after=%d", len(results), len(scoped))
        return scoped

    def _boost_lexical_alignment(self, query: str, results: List[Dict]) -> List[Dict]:
        query_terms = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
        if not query_terms:
            return results

        boosted = []
        for r in results:
            text = self._normalize_text_for_scoring(r.get("text"))
            if not text:
                boosted.append(r)
                continue

            overlap = 0
            for token in query_terms:
                if token in text:
                    overlap += 1

            if overlap > 0:
                item = dict(r)
                item["score"] = float(item.get("score", 0.0)) + min(0.18, overlap * 0.02)
                boosted.append(item)
            else:
                boosted.append(r)

        return boosted

    def _boost_chunk_structure(self, query: str, results: List[Dict]) -> List[Dict]:
        q = (query or "").strip().lower()
        if not q:
            return results

        chapter_match = re.search(r"\bchapter\s+(\d+)\b", q)
        chapter_num = chapter_match.group(1) if chapter_match else None

        query_terms = set(re.findall(r"[a-zA-Z0-9]+", q))
        lightweight_stop = {
            "what", "which", "where", "when", "how", "why", "is", "are", "the", "a",
            "an", "of", "in", "on", "for", "to", "with", "about", "and", "or", "from"
        }
        query_terms = {t for t in query_terms if t not in lightweight_stop and len(t) > 2}

        type_keywords = {
            "appendix": "appendix",
            "index": "index",
            "reference": "references",
            "references": "references",
            "glossary": "glossary",
            "toc": "toc",
            "contents": "toc",
            "preface": "front_matter",
        }
        requested_types = {v for k, v in type_keywords.items() if k in q}

        boosted = []
        for r in results:
            item = dict(r)
            score = float(item.get("score", 0.0))
            metadata = item.get("metadata") or {}

            chapter = (metadata.get("chapter") or "").strip().lower()
            subheading = (metadata.get("subheading") or "").strip().lower()
            page_type = (metadata.get("page_type") or "").strip().lower()

            if chapter_num and chapter:
                chapter_num_match = re.search(r"\bchapter\s+(\d+)\b", chapter)
                if chapter_num_match and chapter_num_match.group(1) == chapter_num:
                    score += 0.22

            section_overlap = 0
            if query_terms:
                for token in query_terms:
                    if token in chapter or token in subheading:
                        section_overlap += 1
            if section_overlap:
                score += min(0.16, section_overlap * 0.03)

            if requested_types and page_type in requested_types:
                score += 0.12
            elif not requested_types and page_type == "toc":
                # Demote TOC blocks for general semantic questions to avoid LLM hallucinating summaries
                score -= 0.15

            item["score"] = score
            boosted.append(item)

        return boosted

    def _normalize_text_for_scoring(self, text: Optional[str]) -> str:
        source = (text or "").strip()
        if not source:
            return ""

        lines = source.splitlines()
        cleaned_lines = []
        for line in lines:
            if line.strip().startswith("[TOC]"):
                continue
            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines).strip()
        return cleaned.lower()

    def _expand_query_variants(self, query: str) -> List[str]:
        q = (query or "").strip()
        if not q:
            return []

        variants = [q]

        normalized = re.sub(r"\s+", " ", q).strip()
        if normalized and normalized not in variants:
            variants.append(normalized)

        no_punct = re.sub(r"[^\w\s]", " ", normalized)
        no_punct = re.sub(r"\s+", " ", no_punct).strip()
        if no_punct and no_punct not in variants:
            variants.append(no_punct)

        return variants[: self.max_query_variants]

    def _ensure_structure(self, results: List[Dict]) -> List[Dict]:
        enriched = []

        for r in results:
            metadata = r.get("metadata", {})
            if metadata.get("chapter") and metadata.get("subheading"):
                enriched.append(r)
                continue

            try:
                if hasattr(self.graph_retriever, "get_structure"):
                    structure = self.graph_retriever.get_structure(r["chunk_id"])
                    if structure:
                        metadata["chapter"] = structure.get("chapter")
                        metadata["subheading"] = structure.get("subheading")
                        r["metadata"] = metadata
            except Exception:
                logger.debug("Structure enrichment failed for %s", r.get("chunk_id"))

            enriched.append(r)

        return enriched

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:
        best = {}
        for r in results:
            if not isinstance(r, dict):
                continue

            doc_id = r.get("doc_id")
            chunk_id = r.get("chunk_id")
            if not doc_id or not chunk_id:
                continue

            unique_key = (doc_id, chunk_id)
            if unique_key not in best:
                best[unique_key] = r
                continue

            try:
                current_score = float(r.get("score", 0))
                existing_score = float(best[unique_key].get("score", 0))
                if current_score > existing_score:
                    best[unique_key] = r
            except (TypeError, ValueError):
                pass

        return list(best.values())

    def _summarize_results(
        self,
        results: List[Dict],
        limit: int = 10,
        include_rerank: bool = False,
    ) -> List[Dict]:
        summary = []
        for r in results[:limit]:
            item = {
                "chunk_id": r.get("chunk_id"),
                "doc_id": r.get("doc_id"),
                "source": r.get("source"),
                "score": round(float(r.get("score", 0.0)), 4),
            }
            if include_rerank and "rerank_score" in r:
                item["rerank_score"] = round(float(r.get("rerank_score", 0.0)), 4)
            summary.append(item)
        return summary
