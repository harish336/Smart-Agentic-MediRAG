"""
SmartChunk-RAG — Answering Agent

Responsibilities:
- Route intent (general / medical / book)
- Retrieve context (hybrid retrieval)
- Enforce grounding rules
- Call LLM (Ollama local)
- Format response
- Build structured citations
- Return strict JSON

Output format:
{
    "response": "",
    "citations": []
}
"""

import json
import requests
from typing import Dict, List

from retriever.orchestrator import RetrieverOrchestrator
from answering.intent_router import IntentRouter
from answering.prompt_builder import PromptBuilder
from answering.citation_manager import CitationManager
from answering.response_formatter import ResponseFormatter


# ============================================================
# LLM CONFIGURATION (Ollama Local)
# ============================================================

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "mistral:7b-instruct"  # Change if needed


# ============================================================
# Answering Agent
# ============================================================

class AnsweringAgent:

    def __init__(self, model: str = DEFAULT_MODEL):

        print("=" * 80)
        print("[ANSWERING AGENT] Initializing...")
        print("=" * 80)

        self.model = model

        self.router = IntentRouter()
        self.retriever = RetrieverOrchestrator()
        self.prompt_builder = PromptBuilder()
        self.citation_manager = CitationManager()
        self.formatter = ResponseFormatter()

        print(f"[ANSWERING AGENT] Using model: {self.model}")
        print("[ANSWERING AGENT] Ready")
        print("=" * 80)

    # ============================================================
    # Public API
    # ============================================================

    def answer(self, query: str) -> Dict:

        if not query or not query.strip():
            return self._empty_response()

        # -----------------------------
        # Step 1: Intent Classification
        # -----------------------------
        intent = self.router.classify(query)

        # -----------------------------
        # Step 2: Retrieve Context
        # -----------------------------
        results = self.retriever.retrieve(
            query=query,
            mode="hybrid",
            top_k=5
        )

        # If medical/book and no context → refuse
        if intent in ["medical", "book"] and not results:
            return self._empty_response()

        # If general and no results → allow LLM free answer
        context_chunks = results[:3] if results else []

        # -----------------------------
        # Step 3: Build Prompt
        # -----------------------------
        prompt = self.prompt_builder.build(
            query=query,
            context_chunks=context_chunks,
            intent=intent
        )

        # -----------------------------
        # Step 4: Call LLM
        # -----------------------------
        llm_response = self._call_llm(prompt)

        if not llm_response or llm_response.strip() == "":
            return self._empty_response()

        # -----------------------------
        # Step 5: Format Output
        # -----------------------------
        formatted_response = self.formatter.format(llm_response)

        if formatted_response == "":
            return self._empty_response()

        # -----------------------------
        # Step 6: Build Citations
        # -----------------------------
        citations = []
        if intent in ["medical", "book"]:
            citations = self.citation_manager.build(context_chunks)

            # If medical/book but no citation built → refuse
            if not citations:
                return self._empty_response()

        return {
            "response": formatted_response,
            "citations": citations
        }

    # ============================================================
    # Internal: Call Ollama LLM
    # ============================================================

    def _call_llm(self, prompt: str) -> str:

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,   # Low hallucination
                "top_p": 0.9,
                "num_predict": 800
            }
        }

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                print("[LLM ERROR]", response.text)
                return ""

            data = response.json()
            return data.get("response", "").strip()

        except Exception as e:
            print("[LLM CONNECTION ERROR]", e)
            return ""

    # ============================================================
    # Empty Safe Response
    # ============================================================

    def _empty_response(self) -> Dict:
        return {
            "response": "",
            "citations": []
        }