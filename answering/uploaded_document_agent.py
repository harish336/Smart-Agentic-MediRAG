"""
Agent for answering questions directly from uploaded document context.
"""

import os
from typing import Dict, Optional

import requests

from core.utils.logging_utils import get_component_logger


logger = get_component_logger("UploadedDocumentAgent", component="answering")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
UPLOAD_MODEL = os.getenv("OLLAMA_UPLOAD_MODEL", os.getenv("OLLAMA_KNOWLEDGE_MODEL", DEFAULT_MODEL))


class UploadedDocumentAgent:
    def __init__(self, model: str = UPLOAD_MODEL):
        self.model = model

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

        prompt_parts = [
            "You answer strictly from uploaded document content.",
            "If the answer is not explicitly in context, output exactly: dont have an answer",
            "Keep answers concise and factual.",
            "Return valid Markdown only.",
            "Use real line breaks. Never output literal \\n tokens.",
            "Do not use HTML tags such as <br>, <p>, <ul>, <li>, or <table>.",
            "For bullet points use '-' with one item per line.",
            "For numbered steps use '1.', '2.', '3.' format.",
            "If a table is requested, use Markdown table syntax with one logical record per row.",
            "For multi-item table cells, keep all items in the same cell separated by semicolons.",
        ]
        if prefix:
            prompt_parts.append("Conversation context:")
            prompt_parts.append(prefix)
        prompt_parts.append("Uploaded document context:")
        prompt_parts.append(context)
        prompt_parts.append("User question:")
        prompt_parts.append(question)
        prompt_parts.append("Answer:")
        prompt = "\n\n".join(prompt_parts)

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
            if not text:
                text = "dont have an answer"
            return {"response": text, "citations": [], "follow_up": ""}
        except Exception:
            logger.exception("uploaded document answer failed")
            return {"response": "dont have an answer", "citations": [], "follow_up": ""}
