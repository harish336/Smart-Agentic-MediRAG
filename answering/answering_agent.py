"""
SmartChunk-RAG - Answering Agent
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import requests

from answering.citation_manager import CitationManager
from answering.intent_router import IntentRouter
from answering.prompt_builder import PromptBuilder
from answering.response_formatter import ResponseFormatter
from core.utils.logging_utils import get_component_logger
from retriever.orchestrator import RetrieverOrchestrator


logger = get_component_logger("AnsweringAgent", component="answering")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_MODEL)
KNOWLEDGE_MODEL = os.getenv("OLLAMA_KNOWLEDGE_MODEL", DEFAULT_MODEL)
MEDICAL_RERANK_THRESHOLD = float(os.getenv("MEDICAL_RERANK_THRESHOLD", "0.18"))
BOOK_RERANK_THRESHOLD = float(os.getenv("BOOK_RERANK_THRESHOLD", "0.05"))
MAX_CONTEXT_CHUNKS = int(os.getenv("ANSWER_MAX_CONTEXT_CHUNKS", "8"))

_router_instance: Optional[IntentRouter] = None
_retriever_instance: Optional[RetrieverOrchestrator] = None
_prompt_builder_instance: Optional[PromptBuilder] = None
_citation_manager_instance: Optional[CitationManager] = None
_formatter_instance: Optional[ResponseFormatter] = None


def get_router():
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter()
    return _router_instance


def get_retriever():
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = RetrieverOrchestrator()
    return _retriever_instance


def get_prompt_builder():
    global _prompt_builder_instance
    if _prompt_builder_instance is None:
        _prompt_builder_instance = PromptBuilder()
    return _prompt_builder_instance


def get_citation_manager():
    global _citation_manager_instance
    if _citation_manager_instance is None:
        _citation_manager_instance = CitationManager()
    return _citation_manager_instance


def get_formatter():
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = ResponseFormatter()
    return _formatter_instance


class AnsweringAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        logger.info("=" * 80)
        logger.info("Initializing AnsweringAgent (Companion + Evidence RAG)")
        logger.info("=" * 80)

        self.model = model
        self.chat_model = CHAT_MODEL
        self.knowledge_model = KNOWLEDGE_MODEL
        self.router = None
        self.retriever = None
        self.prompt_builder = None
        self.citation_manager = None
        self.formatter = None

        logger.info("Default model: %s", self.model)
        logger.info("Chat model: %s", self.chat_model)
        logger.info("Knowledge model: %s", self.knowledge_model)
        logger.info("=" * 80)

    def answer(
        self,
        query: str,
        retrieval_query: Optional[str] = None,
        retrieval_filters: Optional[Dict] = None,
        thread_messages: Optional[List[Dict]] = None,
        retrieval_options: Optional[Dict] = None,
        supplemental_context: str = "",
        conversation_window: str = "",
    ) -> Dict:
        if not query or not query.strip():
            return {"response": "", "citations": [], "follow_up": ""}

        try:
            if self.router is None:
                self.router = get_router()
            if self.prompt_builder is None:
                self.prompt_builder = get_prompt_builder()
            if self.formatter is None:
                self.formatter = get_formatter()

            intent_input = retrieval_query or query
            intent = self.router.classify(intent_input)
            logger.info("Intent detected: %s", intent)

            if intent == "general":
                prompt = self.prompt_builder.build_companion(query=query)
                llm_response = self._call_llm(
                    prompt=prompt,
                    model=self.chat_model,
                    generation_mode="creative_chat",
                )
                formatted_response = self.formatter.format(llm_response, intent="general")

                if not formatted_response:
                    formatted_response = (
                        "I'm here with you. Tell me a bit more so I can help properly."
                    )

                return {"response": formatted_response, "citations": [], "follow_up": ""}

            if self.retriever is None:
                self.retriever = get_retriever()
            if self.citation_manager is None:
                self.citation_manager = get_citation_manager()

            search_query = retrieval_query or query
            if intent == "book":
                search_query = self._build_thread_aware_book_query(
                    query=search_query,
                    thread_messages=thread_messages,
                )
                # Pro/book path: one focused retrieval query for lower latency.
                sub_questions = [search_query]
            else:
                sub_questions = self._decompose_compound_query(search_query)
                max_sub = int((retrieval_options or {}).get("max_sub_queries", 3) or 3)
                if max_sub > 0:
                    sub_questions = sub_questions[:max_sub]
            retrieval_results, coverage = self._retrieve_compound(
                queries=sub_questions,
                intent=intent,
                retrieval_filters=retrieval_filters,
                retrieval_options=retrieval_options,
            )
            supplemental_chunks = self._build_supplemental_chunks(supplemental_context)

            if not retrieval_results and not supplemental_chunks:
                return {
                    "response": "dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent, coverage),
                }

            if retrieval_results:
                max_rerank_score = max(
                    float(r.get("rerank_score", 0.0) or 0.0) for r in retrieval_results
                )
                rerank_threshold = (
                    MEDICAL_RERANK_THRESHOLD if intent == "medical" else BOOK_RERANK_THRESHOLD
                )
                logger.info(
                    "Rerank gate check | intent=%s max_rerank_score=%.4f threshold=%.4f supplemental_chunks=%d",
                    intent,
                    max_rerank_score,
                    rerank_threshold,
                    len(supplemental_chunks),
                )
                if max_rerank_score < rerank_threshold and not supplemental_chunks:
                    return {
                        "response": "dont have an answer",
                        "citations": [],
                        "follow_up": self._build_follow_up(query, intent, coverage),
                    }

            context_chunks = retrieval_results[:MAX_CONTEXT_CHUNKS]
            if supplemental_chunks:
                available_slots = max(0, MAX_CONTEXT_CHUNKS - len(context_chunks))
                if available_slots > 0:
                    context_chunks = context_chunks + supplemental_chunks[:available_slots]
            prompt_query = self._augment_query_for_prompt(query, sub_questions)
            if intent == "book":
                prompt_query = self._augment_book_prompt_with_thread(
                    prompt_query=prompt_query,
                    thread_messages=thread_messages,
                )

            prompt = self.prompt_builder.build(
                query=prompt_query,
                context_chunks=context_chunks,
                intent=intent,
                conversation_window=conversation_window,
            )

            citations = []
            if intent == "book":
                with ThreadPoolExecutor(max_workers=2) as executor:
                    citations_future = executor.submit(
                        self.citation_manager.build,
                        context_chunks,
                    )
                    llm_response = self._call_llm(prompt)
                    citations = citations_future.result() or []
            else:
                llm_response = self._call_llm(prompt)

            if not llm_response:
                return {
                    "response": "dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent, coverage),
                }

            formatted_response = self.formatter.format(llm_response, intent=intent)
            if self._needs_follow_up(formatted_response):
                return {
                    "response": "dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent, coverage),
                }

            if intent != "book":
                citations = self.citation_manager.build(context_chunks)
            if not citations:
                return {
                    "response": "dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent, coverage),
                }

            return {"response": formatted_response, "citations": citations, "follow_up": ""}

        except Exception:
            logger.exception("Unhandled exception inside answer()")
            return {
                "response": "",
                "citations": [],
                "follow_up": self._build_follow_up(query, "general", []),
            }

    def _build_supplemental_chunks(self, supplemental_context: str) -> List[Dict]:
        text = (supplemental_context or "").strip()
        if not text:
            return []

        sections = [part.strip() for part in re.split(r"(?=### Uploaded File:)", text) if part.strip()]
        chunks: List[Dict] = []

        for idx, section in enumerate(sections, start=1):
            header = ""
            body = section
            if section.startswith("### Uploaded File:"):
                lines = section.splitlines()
                if lines:
                    header = lines[0].replace("### Uploaded File:", "").strip()
                    body = "\n".join(lines[1:]).strip()

            cleaned_text = body.strip()
            if not cleaned_text:
                continue

            upload_name = header or f"upload-{idx}"
            chunks.append(
                {
                    "doc_id": f"uploaded_chat::{upload_name}",
                    "chunk_id": f"upload_chunk_{idx}",
                    "text": cleaned_text,
                    "source": "uploaded_document",
                    "metadata": {
                        "chapter": "Uploaded chat document",
                        "subheading": upload_name,
                        "page_label": "upload",
                        "page_physical": idx,
                    },
                    "rerank_score": 1.0,
                }
            )

        return chunks

    def _retrieve_compound(
        self,
        queries: List[str],
        intent: str,
        retrieval_filters: Optional[Dict] = None,
        retrieval_options: Optional[Dict] = None,
    ) -> Tuple[List[Dict], List[Dict]]:
        merged: List[Dict] = []
        coverage: List[Dict] = []
        retrieval_mode = str((retrieval_options or {}).get("mode", "hybrid") or "hybrid").lower()
        top_k = int((retrieval_options or {}).get("top_k", 8) or 8)
        initial_k = int((retrieval_options or {}).get("initial_k", 25) or 25)

        for q in queries:
            results = self.retriever.retrieve(
                query=q,
                mode=retrieval_mode,
                top_k=top_k,
                initial_k=initial_k,
                filters=retrieval_filters,
            )
            merged.extend(results)
            coverage.append(
                {
                    "sub_query": q,
                    "result_count": len(results),
                    "max_rerank_score": max(
                        [float(r.get("rerank_score", 0.0) or 0.0) for r in results] + [0.0]
                    ),
                }
            )

        merged = self._deduplicate_results(merged)
        merged.sort(key=lambda x: float(x.get("rerank_score", 0.0) or 0.0), reverse=True)

        logger.info(
            "Compound retrieval summary | sub_queries=%d merged_results=%d coverage=%s",
            len(queries),
            len(merged),
            coverage,
        )
        return merged, coverage

    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        best = {}
        for r in results:
            doc_id = r.get("doc_id")
            chunk_id = r.get("chunk_id")
            if not doc_id or not chunk_id:
                continue
            key = (doc_id, chunk_id)
            if key not in best:
                best[key] = r
                continue
            if float(r.get("rerank_score", 0.0) or 0.0) > float(
                best[key].get("rerank_score", 0.0) or 0.0
            ):
                best[key] = r
        return list(best.values())

    def _decompose_compound_query(self, query: str) -> List[str]:
        text = (query or "").strip()
        if not text:
            return []

        splitter = re.compile(
            r"\s*(?:\?| and | also | plus | then | additionally | along with |,)\s*",
            flags=re.IGNORECASE,
        )
        parts = [p.strip(" .") for p in splitter.split(text) if p and p.strip(" .")]
        cleaned = []
        for part in parts:
            if len(part.split()) >= 3:
                cleaned.append(part)

        if not cleaned:
            return [text]

        deduped = []
        seen = set()
        for part in cleaned:
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(part)

        return deduped[:3] if len(deduped) > 1 else [text]

    def _augment_query_for_prompt(self, query: str, sub_questions: List[str]) -> str:
        if len(sub_questions) <= 1:
            return query
        bullet_points = "\n".join([f"- {item}" for item in sub_questions])
        return f"{query}\n\nSub-questions to address:\n{bullet_points}"

    def _build_thread_aware_book_query(
        self,
        query: str,
        thread_messages: Optional[List[Dict]] = None,
    ) -> str:
        current = (query or "").strip()
        if not current:
            return ""

        user_history = [
            (m.get("content") or "").strip()
            for m in (thread_messages or [])
            if (m.get("role") or "").strip().lower() == "user" and (m.get("content") or "").strip()
        ]
        if len(user_history) < 2:
            return current

        previous_user_query = user_history[-2]
        if not previous_user_query:
            return current

        context_dependent = self._is_context_dependent_query(current)
        short_follow_up = len(current.split()) <= 8
        if not context_dependent and not short_follow_up:
            return current

        return f"{current}\n\nPrevious user context: {previous_user_query}"

    def _augment_book_prompt_with_thread(
        self,
        prompt_query: str,
        thread_messages: Optional[List[Dict]] = None,
    ) -> str:
        recent_pairs = []
        pending_user = ""
        for message in thread_messages or []:
            role = (message.get("role") or "").strip().lower()
            content = (message.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                pending_user = content
                continue
            if role == "assistant" and pending_user:
                recent_pairs.append((pending_user, content))
                pending_user = ""

        if not recent_pairs:
            return prompt_query

        tail = recent_pairs[-2:]
        context_lines = ["Conversation context:"]
        for idx, (q, a) in enumerate(tail, start=1):
            context_lines.append(f"- Turn {idx} user: {q}")
            context_lines.append(f"- Turn {idx} assistant: {a}")

        return f"{prompt_query}\n\n" + "\n".join(context_lines)

    def _is_context_dependent_query(self, query: str) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False

        markers = [
            "this",
            "that",
            "it",
            "above",
            "previous",
            "same",
            "continue",
            "more",
            "elaborate",
            "explain more",
            "summarize",
            "format",
        ]
        return any(marker in text for marker in markers)

    def _call_llm(
        self,
        prompt: str,
        model: Optional[str] = None,
        generation_mode: str = "grounded",
    ) -> str:
        selected_model = model or self.knowledge_model or self.model
        options = {
            "temperature": 0.1,
            "top_p": 0.2,
            "top_k": 30,
            "repeat_penalty": 1.1,
            "seed": 42,
            "num_predict": 700,
        }

        if generation_mode == "creative_chat":
            options = {
                "temperature": 0.8,
                "top_p": 0.9,
                "top_k": 60,
                "repeat_penalty": 1.05,
                "num_predict": 700,
            }

        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            if response.status_code != 200:
                logger.error("LLM error: %s body=%s", response.status_code, response.text[:500])
                return ""

            payload_json = response.json()
            llm_response = (payload_json.get("response", "") or "").strip()

            logger.info(
                "LLM_RESPONSE_START model=%s mode=%s chars=%d",
                selected_model,
                generation_mode,
                len(llm_response),
            )
            logger.info("%s", llm_response if llm_response else "<empty>")
            logger.info("LLM_RESPONSE_END")
            return llm_response

        except Exception:
            logger.exception("LLM connection failure")
            return ""

    def _needs_follow_up(self, response_text: str) -> bool:
        if not response_text:
            return True
        normalized = response_text.strip().lower()
        return normalized == "dont have an answer"

    def _build_follow_up(self, query: str, intent: str, coverage: List[Dict]) -> str:
        weak_parts = [c for c in coverage if c.get("result_count", 0) == 0]

        if weak_parts:
            targets = "; ".join([c.get("sub_query", "") for c in weak_parts[:2] if c.get("sub_query")])
            if targets:
                return f"I need a bit more detail for: {targets}. Can you clarify those parts?"

        if intent == "medical":
            missing = []
            lower_q = (query or "").lower()
            if "how long" not in lower_q and "duration" not in lower_q:
                missing.append("duration")
            if "severe" not in lower_q and "intensity" not in lower_q:
                missing.append("severity")
            if "history" not in lower_q:
                missing.append("relevant medical history")

            if missing:
                return f"Please share {', '.join(missing)} so I can answer accurately."
            return "Please share symptoms, duration, severity, and relevant history so I can answer accurately."

        if intent == "book":
            return "Please share the chapter, section, or key terms you want me to focus on."

        return "Can you clarify your question with a bit more detail?"
