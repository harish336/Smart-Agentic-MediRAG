"""
SmartChunk-RAG  Answering Agent (Pure RAG Production Version)

This agent:
- Performs intent detection
- Performs hybrid retrieval for medical/book queries
- Supports companion mode for normal conversation
- Builds grounded prompts
- Calls LLM
- Formats response
- Adds citations for evidence-mode answers
"""

import os
import requests
from typing import Dict, Optional

from retriever.orchestrator import RetrieverOrchestrator
from answering.intent_router import IntentRouter
from answering.prompt_builder import PromptBuilder
from answering.citation_manager import CitationManager
from answering.response_formatter import ResponseFormatter
from core.utils.logging_utils import get_component_logger


logger = get_component_logger("AnsweringAgent", component="answering")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_MODEL)
KNOWLEDGE_MODEL = os.getenv("OLLAMA_KNOWLEDGE_MODEL", DEFAULT_MODEL)
MEDICAL_RERANK_THRESHOLD = float(os.getenv("MEDICAL_RERANK_THRESHOLD", "0.18"))
BOOK_RERANK_THRESHOLD = float(os.getenv("BOOK_RERANK_THRESHOLD", "0.05"))

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

    def answer(self, query: str, retrieval_query: Optional[str] = None) -> Dict:
        if not query or not query.strip():
            return {"response": "", "citations": [], "follow_up": ""}

        try:
            if self.router is None:
                self.router = get_router()
            if self.prompt_builder is None:
                self.prompt_builder = get_prompt_builder()
            if self.formatter is None:
                self.formatter = get_formatter()

            # Use clean user query for routing when memory/context has been injected.
            intent_input = retrieval_query or query
            intent = self.router.classify(intent_input)
            logger.info("Intent detected: %s", intent)

            # Companion mode: normal conversation without forced retrieval.
            if intent == "general":
                prompt = self.prompt_builder.build_companion(query=query)
                llm_response = self._call_llm(
                    prompt=prompt,
                    model=self.chat_model,
                    generation_mode="creative_chat",
                )
                formatted_response = self.formatter.format(llm_response, intent="general")

                if not formatted_response:
                    formatted_response = "I'm here with you. Tell me a bit more so I can help properly."

                return {
                    "response": formatted_response,
                    "citations": [],
                    "follow_up": ""
                }

            # Evidence mode for medical/book intents.
            if self.retriever is None:
                self.retriever = get_retriever()
            if self.citation_manager is None:
                self.citation_manager = get_citation_manager()

            search_query = retrieval_query or query
            results = self.retriever.retrieve(
                query=search_query,
                mode="hybrid",
                top_k=8,
                initial_k=25
            )

            if not results:
                return {
                    "response": "dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent)
                }

            max_rerank_score = max(float(r.get("rerank_score", 0.0) or 0.0) for r in results)
            rerank_threshold = MEDICAL_RERANK_THRESHOLD if intent == "medical" else BOOK_RERANK_THRESHOLD
            logger.info(
                "Rerank gate check | intent=%s max_rerank_score=%.4f threshold=%.4f",
                intent,
                max_rerank_score,
                rerank_threshold,
            )
            if max_rerank_score < rerank_threshold:
                return {
                    "response": "Dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent)
                }

            context_chunks = results[:6]

            prompt = self.prompt_builder.build(
                query=query,
                context_chunks=context_chunks,
                intent=intent
            )

            llm_response = self._call_llm(prompt)
            if not llm_response:
                return {
                    "response": "Dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent)
                }

            formatted_response = self.formatter.format(llm_response, intent=intent)
            if self._needs_follow_up(formatted_response):
                return {
                    "response": "Dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent)
                }

            citations = self.citation_manager.build(context_chunks)
            if not citations:
                return {
                    "response": "Dont have an answer",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent)
                }

            return {
                "response": formatted_response,
                "citations": citations,
                "follow_up": ""
            }

        except Exception:
            logger.exception("Unhandled exception inside answer()")
            return {
                "response": "",
                "citations": [],
                "follow_up": self._build_follow_up(query, "general")
            }

    def _call_llm(self, prompt: str, model: Optional[str] = None, generation_mode: str = "grounded") -> str:
        selected_model = model or self.knowledge_model or self.model
        options = {
            "temperature": 0.1,
            "top_p": 0.2,
            "top_k": 30,
            "repeat_penalty": 1.1,
            "seed": 42,
            "num_predict": 700
        }

        if generation_mode == "creative_chat":
            options = {
                "temperature": 0.8,
                "top_p": 0.9,
                "top_k": 60,
                "repeat_penalty": 1.05,
                "num_predict": 700
            }

        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "options": options
        }

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                logger.error("LLM error: %s body=%s", response.status_code, response.text[:500])
                return ""

            payload_json = response.json()
            llm_response = (payload_json.get("response", "") or "").strip()

            # Persist raw LLM output in answering.log for traceability/debugging.
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
        return response_text.strip().lower() == "dont have an answer"

    def _build_follow_up(self, query: str, intent: str) -> str:
        if intent == "medical":
            return "Can you share symptoms, duration, severity, and relevant history so I can answer accurately?"
        if intent == "book":
            return "Please share the chapter, section, or key term you want me to focus on."
        return "Can you clarify your question with a bit more detail?"
