"""
Agent for answering questions directly from uploaded document context.
"""

import os
import re
from typing import Dict

import requests

from answering.prompt_builder import PromptBuilder
from answering.response_formatter import ResponseFormatter
from core.utils.logging_utils import get_component_logger


logger = get_component_logger("UploadedDocumentAgent", component="answering")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
UPLOAD_MODEL = os.getenv(
    "OLLAMA_UPLOAD_MODEL",
    os.getenv("OLLAMA_KNOWLEDGE_MODEL", DEFAULT_MODEL),
)

UPLOAD_MAX_REWRITE_ROUNDS = max(
    0, int(os.getenv("UPLOAD_MAX_REWRITE_ROUNDS", "0"))
)

FORBIDDEN_RESPONSE_WORDS = tuple(
    w.strip().lower()
    for w in os.getenv("FORBIDDEN_RESPONSE_WORDS", "").split(",")
    if w.strip()
)


class UploadedDocumentAgent:
    """
    Agent that answers questions using uploaded document text only.
    """

    BANNED_META_PATTERNS = [
        r"\bprovided\s+(text|context|content|source|sources|book)\b",
        r"\btext\s+you\s+provided\b",
        r"\bbased\s+on\s+the\s+(provided\s+)?(text|context|content|source|book)\b",
        r"\bnot\s+explicitly\s+mentioned\b",
        r"\bit\s+appears\b",
        r"\bfrom\s+the\s+provided\s+source\b",
        r"\bbook\s+you\S*ve\s+provided\b",
        r"\bthese\s+topics\s+are\s+discussed\b",
        r"\bin\s+the\s+book\b",
        r"\bfrom\s+a\s+global\s+perspective\b",
    ]

    LONG_FORM_PATTERN = re.compile(
        r"\b(chapter[-\s]*wise|all\s+chapters?|complete\s+summary|"
        r"comprehensive\s+summary|detailed\s+summary|full\s+summary)\b",
        re.IGNORECASE,
    )

    PLACEHOLDER_PATTERN = re.compile(r"\[[^\]]+\]")

    def __init__(self, model: str = UPLOAD_MODEL):

        self.model = model
        self.formatter = ResponseFormatter()
        self.prompt_builder = PromptBuilder()

        self.max_rewrite_rounds = UPLOAD_MAX_REWRITE_ROUNDS
        self.forbidden_words = FORBIDDEN_RESPONSE_WORDS

    # ------------------------------------------------------------------
    # MAIN ENTRY
    # ------------------------------------------------------------------

    def answer(
        self,
        query: str,
        uploaded_context: str,
        context_prefix: str = "",
    ) -> Dict:

        question = (query or "").strip()
        context = (uploaded_context or "").strip()

        if not question:
            return self._empty()

        if not context:
            return self._fallback()

        prompt = self.prompt_builder.build_uploaded_document_qa(
            query=question,
            uploaded_text=context,
            conversation_notes=context_prefix,
        )

        payload = self._build_payload(question, prompt)

        try:

            text = self._call_llm(payload)

            logger.info(
                "UPLOAD_LLM_RESPONSE chars=%d",
                len(text),
            )

            text = self._rewrite_if_needed(text, question, context)

            text = self._sanitize(text, question, context)

            if not text:
                text = "dont have an answer"

            formatted = self.formatter.format(text, intent="book")

            return {
                "response": formatted or "dont have an answer",
                "citations": [],
                "follow_up": "",
            }

        except Exception:
            logger.exception("Uploaded document answering failed")
            return self._fallback()

    # ------------------------------------------------------------------
    # PAYLOAD
    # ------------------------------------------------------------------

    def _build_payload(self, question: str, prompt: str) -> Dict:

        return {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.2,
                "top_k": 30,
                "repeat_penalty": 1.1,
                "seed": 42,
                "num_predict": self._num_predict(question),
            },
        }

    def _num_predict(self, question: str) -> int:

        if self.LONG_FORM_PATTERN.search(question):
            return 1600

        return 700

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _call_llm(self, payload: Dict) -> str:

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=90,
        )

        response.raise_for_status()

        return (response.json().get("response") or "").strip()

    # ------------------------------------------------------------------
    # REWRITE LOOP
    # ------------------------------------------------------------------

    def _rewrite_if_needed(self, text, question, context):

        for _ in range(self.max_rewrite_rounds):

            if not self._has_meta(text):
                break

            text = self._regenerate(question, context)

        return text

    # ------------------------------------------------------------------
    # META DETECTION
    # ------------------------------------------------------------------

    def _has_meta(self, text: str) -> bool:

        t = (text or "").lower()

        for pattern in self.BANNED_META_PATTERNS:
            if re.search(pattern, t):
                return True

        return False

    # ------------------------------------------------------------------
    # REGENERATE
    # ------------------------------------------------------------------

    def _regenerate(self, question, context):

        prompt = f"""
[INST]

You are a document analysis assistant.

Answer using ONLY the uploaded document.

STRICT RULES
- Use only information present in the document.
- Do NOT invent or assume content.
- Do NOT use phrases like:
  "provided text", "provided context", "the book you provided".
- If the answer cannot be found, return: "dont have an answer".

TASK
Generate a COMPLETE chapter-wise summary of the document.

IMPORTANT INSTRUCTIONS

1. Identify chapters ONLY if they follow this pattern:
   "Chapter X" where X is a number.

2. Ignore section headings such as:
   1.1, 2.3, 3.4 etc.

3. The summary must include ALL chapters in order.

4. For each chapter:
   - include the chapter title
   - summarize the key ideas
   - summarize the main sections inside the chapter

OUTPUT FORMAT

Title: <document title if available>

Chapter 1: <chapter title>
• key ideas
• key ideas

Chapter 2: <chapter title>
• key ideas
• key ideas

Continue until the FINAL chapter.

DOCUMENT
--------
DOCUMENT START
{context}
DOCUMENT END

QUESTION
--------
{question}

Return ONLY the final structured answer.

[/INST]
"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.15,
                "top_k": 20,
                "seed": 42,
                "num_predict": 700,
            },
        }

        return self._call_llm(payload)

    # ------------------------------------------------------------------
    # SANITIZATION
    # ------------------------------------------------------------------

    def _sanitize(self, text, question, context):

        text = self._remove_meta_sentences(text)

        text = self._remove_placeholders(text)

        text = self._remove_empty_lists(text)

        text = text.strip()

        if self._has_meta(text):
            return ""

        return text

    # ------------------------------------------------------------------
    # CLEANERS
    # ------------------------------------------------------------------

    def _remove_meta_sentences(self, text):

        sentences = re.split(r"(?<=[.!?])\s+", text)

        cleaned = []

        for s in sentences:

            if not self._has_meta(s):
                cleaned.append(s.strip())

        return " ".join(cleaned)

    def _remove_placeholders(self, text):

        return re.sub(self.PLACEHOLDER_PATTERN, "", text)

    def _remove_empty_lists(self, text):

        text = re.sub(r"(?m)^\s*\d+[.)]\s*$", "", text)
        text = re.sub(r"(?m)^\s*[-*]\s*$", "", text)

        return text

    # ------------------------------------------------------------------
    # FALLBACK
    # ------------------------------------------------------------------

    def _fallback(self):

        return {
            "response": "dont have an answer",
            "citations": [],
            "follow_up": "",
        }

    def _empty(self):

        return {
            "response": "",
            "citations": [],
            "follow_up": "",
        }