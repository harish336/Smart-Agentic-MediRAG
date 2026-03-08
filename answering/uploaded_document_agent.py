"""
Agent for answering questions directly from uploaded document context.
"""

import os
from typing import Dict

import requests

from answering.prompt_builder import PromptBuilder
from answering.response_formatter import ResponseFormatter
from core.utils.logging_utils import get_component_logger


logger = get_component_logger("UploadedDocumentAgent", component="answering")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
UPLOAD_MODEL = os.getenv("OLLAMA_UPLOAD_MODEL", os.getenv("OLLAMA_KNOWLEDGE_MODEL", DEFAULT_MODEL))


class UploadedDocumentAgent:
    def __init__(self, model: str = UPLOAD_MODEL):
        self.model = model
        self.formatter = ResponseFormatter()
        self.prompt_builder = PromptBuilder()

    def answer(
        self,
        query: str,
        uploaded_context: str,
        context_prefix: str = "",
    ) -> Dict:
        question = (query or "").strip()
        context = (uploaded_context or "").strip()
        prefix = (context_prefix or "").strip()

        if not question:
            return {"response": "", "citations": [], "follow_up": ""}
        if not context:
            return {"response": "dont have an answer", "citations": [], "follow_up": ""}

        prompt = self.prompt_builder.build_uploaded_document_qa(
            query=question,
            uploaded_text=context,
            conversation_notes=prefix,
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.2,
                "top_k": 30,
                "repeat_penalty": 1.1,
                "seed": 42,
                "num_predict": 700,
            },
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=90)
            response.raise_for_status()
            text = (response.json().get("response") or "").strip()
            formatted = self.formatter.format(text, intent="medical") if text else ""
            if not formatted:
                formatted = "dont have an answer"
            return {"response": formatted, "citations": [], "follow_up": ""}
        except Exception:
            logger.exception("uploaded document answer failed")
            return {"response": "dont have an answer", "citations": [], "follow_up": ""}
