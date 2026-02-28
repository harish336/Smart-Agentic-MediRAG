"""
SmartChunk-RAG — Answering Agent (Pure RAG Production Version)

This agent:
- Performs intent detection
- Performs hybrid retrieval
- Builds grounded prompt
- Calls LLM
- Formats response
- Adds citations

It does NOT:
- Manage memory
- Manage threads
- Handle user_id
- Classify transformation queries

Memory logic must live in MemoryWrappedAnsweringAgent.
"""

import requests
from typing import Dict, Optional

from retriever.orchestrator import RetrieverOrchestrator
from answering.intent_router import IntentRouter
from answering.prompt_builder import PromptBuilder
from answering.citation_manager import CitationManager
from answering.response_formatter import ResponseFormatter
from core.utils.logging_utils import get_component_logger


# ============================================================
# LOGGER CONFIG
# ============================================================

logger = get_component_logger("AnsweringAgent", component="answering")


# ============================================================
# LLM CONFIG
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "mistral:7b-instruct"


# ============================================================
# Lazy Singletons
# ============================================================

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


# ============================================================
# ANSWERING AGENT (PURE RAG)
# ============================================================

class AnsweringAgent:

    def __init__(self, model: str = DEFAULT_MODEL):

        logger.info("=" * 80)
        logger.info("Initializing AnsweringAgent (Pure RAG)")
        logger.info("=" * 80)

        self.model = model
        self.router = None
        self.retriever = None
        self.prompt_builder = None
        self.citation_manager = None
        self.formatter = None

        logger.info(f"Model: {self.model}")
        logger.info("=" * 80)

    # ============================================================
    # PUBLIC API
    # ============================================================

    def answer(self, query: str) -> Dict:
        """
        Main RAG execution method.
        Expects a fully prepared query (memory already injected if needed).
        """

        if not query or not query.strip():
            return {
                "response": "",
                "citations": [],
                "follow_up": ""
            }

        try:

            # -----------------------------------------------
            # Lazy Load Dependencies
            # -----------------------------------------------

            if self.router is None:
                self.router = get_router()

            if self.retriever is None:
                self.retriever = get_retriever()

            if self.prompt_builder is None:
                self.prompt_builder = get_prompt_builder()

            if self.citation_manager is None:
                self.citation_manager = get_citation_manager()

            if self.formatter is None:
                self.formatter = get_formatter()

            # -----------------------------------------------
            # 1️⃣ Intent Detection
            # -----------------------------------------------

            intent = self.router.classify(query)
            logger.info(f"Intent detected: {intent}")

            # -----------------------------------------------
            # 2️⃣ Retrieval
            # -----------------------------------------------

            results = self.retriever.retrieve(
                query=query,
                mode="hybrid",
                top_k=15
            )

            context_chunks = results[:15] if results else []

            # -----------------------------------------------
            # 3️⃣ Prompt Building
            # -----------------------------------------------

            prompt = self.prompt_builder.build(
                query=query,
                context_chunks=context_chunks,
                intent=intent
            )

            # -----------------------------------------------
            # 4️⃣ LLM Call
            # -----------------------------------------------

            llm_response = self._call_llm(prompt)

            if not llm_response:
                return {
                    "response": "",
                    "citations": [],
                    "follow_up": self._build_follow_up(query, intent)
                }

            # -----------------------------------------------
            # 5️⃣ Format Response
            # -----------------------------------------------

            formatted_response = self.formatter.format(llm_response)
            follow_up = ""
            if self._needs_follow_up(formatted_response):
                follow_up = self._build_follow_up(query, intent)

            # -----------------------------------------------
            # 6️⃣ Citations
            # -----------------------------------------------

            citations = []

            if intent in ["medical", "book"] and results:
                citations = self.citation_manager.build(results)

            return {
                "response": formatted_response,
                "citations": citations,
                "follow_up": follow_up
            }

        except Exception:
            logger.exception("Unhandled exception inside answer()")
            return {
                "response": "",
                "citations": [],
                "follow_up": self._build_follow_up(query, "general")
            }

    # ============================================================
    # LLM CALL
    # ============================================================

    def _call_llm(self, prompt: str) -> str:

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": 600
            }
        }

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                logger.error(f"LLM error: {response.status_code}")
                return ""

            return response.json().get("response", "").strip()

        except Exception:
            logger.exception("LLM connection failure")
            return ""

    # ============================================================
    # FOLLOW-UP QUESTION HANDLING
    # ============================================================

    def _needs_follow_up(self, response_text: str) -> bool:
        if not response_text:
            return True
        return response_text.strip().lower() == "information not found"

    def _build_follow_up(self, query: str, intent: str) -> str:
        if intent == "medical":
            return "Can you provide more specific symptoms, duration, or relevant history so I can answer accurately?"
        if intent == "book":
            return "Which chapter, section, or page should I focus on for this question?"
        return "Can you clarify your question or add more details so I can answer precisely?"
