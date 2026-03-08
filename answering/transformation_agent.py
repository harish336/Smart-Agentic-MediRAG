"""
LLM-driven transformation agent for follow-up formatting tasks.
"""

import os
import re

import requests

from answering.prompt_builder import PromptBuilder
from core.utils.logging_utils import get_component_logger


logger = get_component_logger("TransformationAgent", component="answering")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct")
TRANSFORM_MODEL = os.getenv("OLLAMA_CHAT_MODEL", DEFAULT_MODEL)
FORBIDDEN_RESPONSE_WORDS = tuple(
    w.strip().lower()
    for w in os.getenv("FORBIDDEN_RESPONSE_WORDS", "").split(",")
    if w.strip()
)


class TransformationAgent:
    _BANNED_META_PATTERNS = (
        r"\bprovided\s+(?:text|context|content|source|sources|book)\b",
        r"\btext\s+you\s+provided\b",
        r"\bbased\s+on\s+the\s+(?:provided\s+)?(?:text|context|content|source|book)\b",
        r"\bnot\s+explicitly\s+mentioned\b",
        r"\bit\s+appears\b",
        r"\bfrom\s+the\s+provided\s+source\b",
        r"\bbook\s+you\S*ve\s+provided\b",
        r"\bthe\s+book\s+(?:you|that)\s+provided\b",
        r"\bthese\s+topics\s+are\s+discussed\b",
        r"\bin\s+the\s+book\b",
        r"\bfrom\s+a\s+global\s+perspective\b",
        r"\bhere\s+are\s+some\s+of\s+the\s+main\s+topics\b",
        r"\bcovers\s+a\s+wide\s+range\s+of\b",
        r"\bproviding\s+insights\s+into\b",
        r"\bthe\s+social\s+problems\s+covered\s+in\s+this\s+book\s+include\b",
    )

    _BANNED_META_LINE_PATTERNS = (
        r"^\s*the\s+book\s+.*(?:provided|is\s+titled|covers)\b.*$",
        r"^\s*here\s+are\s+some\s+of\s+the\s+main\s+topics.*$",
        r"^\s*these\s+topics\s+are\s+discussed.*$",
        r"^\s*the\s+social\s+problems\s+covered\s+in\s+this\s+book\s+include.*$",
    )

    def __init__(self, model: str = TRANSFORM_MODEL):
        self.model = model
        self.prompt_builder = PromptBuilder()
        self.forbidden_words = FORBIDDEN_RESPONSE_WORDS

    def transform(self, instruction: str, source_text: str) -> str:
        request = (instruction or "").strip()
        source = (source_text or "").strip()
        if not request or not source:
            return ""

        table_request = self._is_table_request(request)
        prompt = self.prompt_builder.build_transformation_prompt(
            instruction=request,
            source_text=source,
        )
        candidate = self._call_llm(prompt)
        if not candidate:
            return ""

        for _ in range(4):
            if self._has_banned_meta_language(candidate):
                regenerated = self._regenerate_without_meta_with_llm(
                    instruction=request,
                    source_text=source,
                    table_request=table_request,
                )
                if regenerated:
                    candidate = regenerated.strip()

            if self._has_banned_meta_language(candidate):
                repaired_meta = self._repair_meta_language_with_llm(
                    instruction=request,
                    source_text=source,
                    candidate_text=candidate,
                    table_request=table_request,
                )
                if repaired_meta:
                    candidate = repaired_meta.strip()

            if table_request and not self._is_strict_topic_description_table(candidate):
                repaired = self._repair_table_with_llm(
                    instruction=request,
                    source_text=source,
                    candidate_text=candidate,
                )
                if repaired:
                    candidate = repaired.strip()

            if not self._has_banned_meta_language(candidate) and (
                not table_request or self._is_strict_topic_description_table(candidate)
            ):
                break

        cleaned = self._strip_banned_meta_lines(candidate)
        if cleaned and not self._has_banned_meta_language(cleaned):
            final_text = self._remove_empty_list_markers(cleaned).strip()
        else:
            final_text = self._remove_empty_list_markers(candidate).strip()

        # Never return malformed/degenerate table skeletons for table requests.
        if table_request and not self._is_strict_topic_description_table(final_text):
            return ""

        return final_text

    def _call_llm(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "top_p": 0.15,
                "top_k": 20,
                "repeat_penalty": 1.05,
                "num_predict": 900,
            },
        }

        try:
            logger.info("TRANSFORM_LLM_REQUEST model=%s", self.model)
            response = requests.post(OLLAMA_URL, json=payload, timeout=90)
            if response.status_code != 200:
                logger.error("Transformation LLM error status=%s", response.status_code)
                return ""
            text = (response.json().get("response") or "").strip()
            logger.info(
                "TRANSFORM_LLM_RESPONSE_START model=%s chars=%d",
                self.model,
                len(text),
            )
            logger.info("%s", text if text else "<empty>")
            logger.info("TRANSFORM_LLM_RESPONSE_END")
            return text
        except Exception:
            logger.exception("Transformation LLM request failed")
            return ""

    @staticmethod
    def _is_table_request(instruction: str) -> bool:
        text = (instruction or "").strip().lower()
        return bool(re.search(r"\b(table|tabular|table format|as a table)\b", text))

    @staticmethod
    def _is_strict_topic_description_table(text: str) -> bool:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return False
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        if len(lines) < 3:
            return False
        if any(not ln.startswith("|") for ln in lines):
            return False
        header_cells = [c.strip().lower() for c in lines[0].strip("|").split("|")]
        if len(header_cells) != 2:
            return False
        if header_cells[0] != "topic" or header_cells[1] != "description":
            return False
        separator = lines[1]
        if not re.match(r"^\|\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|$", separator):
            return False
        return True

    def _repair_table_with_llm(self, instruction: str, source_text: str, candidate_text: str) -> str:
        repair_prompt = f"""
[INST]
### SYSTEM ROLE ###
You are a strict Markdown table repair engine.

### TASK ###
Fix the CANDIDATE OUTPUT so it strictly follows the requested table conversion using SOURCE TEXT only.

### HARD RULES ###
- Use ONLY SOURCE TEXT facts.
- Do NOT invent fields (e.g., authors, sources, licenses) unless present in SOURCE TEXT.
- Output exactly one Markdown table with exactly two columns:
| Topic | Description |
| ----- | ----------- |
- No prose before or after the table.
- Keep each row on one line.

### USER INSTRUCTION ###
{instruction}

### SOURCE TEXT ###
{source_text}

### CANDIDATE OUTPUT TO REPAIR ###
{candidate_text}
[/INST]
"""
        return self._call_llm(repair_prompt)

    def _regenerate_without_meta_with_llm(
        self,
        instruction: str,
        source_text: str,
        table_request: bool,
    ) -> str:
        output_rule = (
            "Return ONLY one Markdown table with exactly two columns: Topic and Description."
            if table_request
            else "Return ONLY the transformed Markdown body."
        )

        regen_prompt = f"""
[INST]
### SYSTEM ROLE ###
You are a strict transformation engine.

### TASK ###
Generate a fresh transformed output from SOURCE TEXT and USER INSTRUCTION.

### HARD RULES ###
- Use ONLY SOURCE TEXT facts.
- Do not add or infer new facts.
- Never use meta wording such as:
  "provided context", "provided content", "provided source", "provided book",
  "text you provided", "based on the context", "not explicitly mentioned", "it appears",
  "the book you've provided", "here are some of the main topics", "these topics are discussed",
  "the social problems covered in this book include".
- No intros/outros. No commentary.
- {output_rule}

### USER INSTRUCTION ###
{instruction}

### SOURCE TEXT ###
{source_text}
[/INST]
"""
        return self._call_llm(regen_prompt)

    def _repair_meta_language_with_llm(
        self,
        instruction: str,
        source_text: str,
        candidate_text: str,
        table_request: bool,
    ) -> str:
        output_rule = (
            "Return ONLY one Markdown table with exactly two columns: Topic and Description."
            if table_request
            else "Return ONLY the transformed Markdown body."
        )

        repair_prompt = f"""
[INST]
### SYSTEM ROLE ###
You are a strict output sanitizer.

### TASK ###
Rewrite CANDIDATE OUTPUT to preserve facts while removing banned meta wording.

### HARD RULES ###
- Keep only SOURCE TEXT facts.
- Do not add new facts.
- Remove any wording like:
  "provided context", "provided content", "provided source", "provided book",
  "text you provided", "based on the context", "not explicitly mentioned", "it appears",
  "the book you've provided", "here are some of the main topics", "these topics are discussed",
  "the social problems covered in this book include".
- Do not add intro/outro commentary.
- {output_rule}

### USER INSTRUCTION ###
{instruction}

### SOURCE TEXT ###
{source_text}

### CANDIDATE OUTPUT ###
{candidate_text}
[/INST]
"""
        return self._call_llm(repair_prompt)

    def _has_banned_meta_language(self, text: str) -> bool:
        candidate = (text or "").strip().lower()
        if not candidate:
            return False
        return any(re.search(pattern, candidate) for pattern in self._BANNED_META_PATTERNS)

    def _contains_forbidden_words(self, text: str) -> bool:
        value = (text or "").strip().lower()
        if not value:
            return False
        for word in self.forbidden_words:
            if re.search(rf"\b{re.escape(word)}\b", value):
                return True
        return False

    def _strip_banned_meta_lines(self, text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        lines = [ln for ln in raw.split("\n")]
        kept = []
        for line in lines:
            normalized = line.strip().lower()
            if not normalized:
                kept.append(line)
                continue
            if any(re.search(pattern, normalized) for pattern in self._BANNED_META_LINE_PATTERNS):
                continue
            kept.append(line)

        cleaned = "\n".join(kept)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _remove_empty_list_markers(self, text: str) -> str:
        value = (text or "").replace("\r\n", "\n")
        if not value.strip():
            return ""

        value = re.sub(r"(?m)^\s*(?:\d+[.)]|[-*+])\s*$\n?", "", value)
        value = re.sub(r"(?m)\n?\s*\d+[.)]\s*$", "", value)
        value = re.sub(r"\n{3,}", "\n\n", value).strip()
        return value
