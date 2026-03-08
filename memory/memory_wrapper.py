"""
SmartChunk-RAG — Memory Wrapper
"""

import uuid
import os
import re
import inspect
from typing import Dict, List, Optional
import requests

from memory.memory_service import MemoryService
from answering.answering_agent import AnsweringAgent
from answering.prompt_builder import PromptBuilder
from answering.response_formatter import ResponseFormatter
from core.utils.logging_utils import get_component_logger
from database.app_store import get_thread_messages


OLLAMA_URL = "http://localhost:11434/api/generate"
CLASSIFIER_MODEL = "mistral:7b-instruct"
TRANSFORM_MODEL = os.getenv("OLLAMA_CHAT_MODEL", os.getenv("OLLAMA_MODEL", CLASSIFIER_MODEL))


# ============================================================
# Logger
# ============================================================

logger = get_component_logger("MemoryWrapper", component="answering")


# ============================================================
# Memory Wrapped Agent
# ============================================================

class MemoryWrappedAnsweringAgent:

    def __init__(self, base_agent: AnsweringAgent):

        self.agent = base_agent
        self.memory = MemoryService()
        self.formatter = ResponseFormatter()
        self.prompt_builder = PromptBuilder()

    # ============================================================
    # MAIN ENTRY
    # ============================================================

    def answer(
        self,
        user_id: str,
        query: str,
        thread_id: Optional[str] = None,
        context_prefix: str = "",
        retrieval_filters: Optional[dict] = None,
        thread_messages: Optional[List[Dict]] = None,
        retrieval_options: Optional[Dict] = None,
        uploaded_context: str = "",
    ) -> Dict:

        if not user_id:
            raise ValueError("user_id is required")

        if not query or not query.strip():
            return {"response": "", "citations": []}

        try:
            # --------------------------------------------
            # Resolve Thread
            # --------------------------------------------

            thread_id = self._resolve_thread(user_id, thread_id)
            self._refresh_stm(
                user_id=user_id,
                thread_id=thread_id,
                thread_messages=thread_messages
            )

            # --------------------------------------------
            # Classify Query Type (LLM)
            # --------------------------------------------

            query_type = self._classify_query_type(query)
            logger.info(f"Query classified as: {query_type}")

            # --------------------------------------------
            # Routing Logic
            # --------------------------------------------

            if query_type == "transformation":
                inline_source, cleaned_instruction = self._extract_inline_transformation_source(query)
                transform_instruction = cleaned_instruction or query

                # Prefer persisted thread history so transformations work even after
                # regenerate/branch actions or app restarts.
                last_answer = ""
                if inline_source:
                    last_answer = inline_source
                else:
                    last_answer = self._get_last_assistant(thread_id=thread_id, thread_messages=thread_messages)
                    if not last_answer:
                        last_answer = self.memory.get_last_assistant_response(
                            user_id=user_id,
                            thread_id=thread_id
                        )

                if not last_answer:
                    return {
                        "response": "No previous response available to transform.",
                        "citations": [],
                        "thread_id": thread_id,
                        "user_id": user_id
                    }

                transformed = self._transform_previous_answer(
                    previous_answer=last_answer,
                    instruction=transform_instruction,
                )
                if not transformed:
                    transformed = "dont have an answer"
                result = {"response": self.formatter.format(transformed, intent="transformation"), "citations": []}

            else:
                conversation_window = self._inject_memory(
                    query=query,
                    user_id=user_id,
                    thread_id=thread_id,
                    context_prefix=context_prefix,
                )

            # --------------------------------------------
            # Call Pure RAG Agent
            # --------------------------------------------

            if query_type != "transformation":
                answer_kwargs = {
                    "query": query,                # keep raw user query for generation
                    "retrieval_query": query,      # ONLY clean user question
                    "retrieval_filters": retrieval_filters,
                    "thread_messages": thread_messages,
                    "retrieval_options": retrieval_options,
                    "supplemental_context": uploaded_context,
                }
                # Backward compatibility: older AnsweringAgent versions may not yet
                # accept conversation_window in rolling reload environments.
                try:
                    sig = inspect.signature(self.agent.answer)
                    if "conversation_window" in sig.parameters:
                        answer_kwargs["conversation_window"] = conversation_window
                except Exception:
                    # If introspection fails, proceed without the extra argument.
                    pass

                result = self.agent.answer(**answer_kwargs)

            # --------------------------------------------
            # Persist STM
            # --------------------------------------------

            response_text = (result.get("response") or "").strip()
            if response_text and self.memory.should_store_assistant_stm(response_text):
                self.memory.append_stm(
                    user_id=user_id,
                    thread_id=thread_id,
                    role="user",
                    content=query
                )

                self.memory.append_stm(
                    user_id=user_id,
                    thread_id=thread_id,
                    role="assistant",
                    content=response_text
                )

            result["thread_id"] = thread_id
            result["user_id"] = user_id

            return result

        except Exception:
            logger.exception("Error inside memory wrapper")
            return {"response": "", "citations": []}

    def _get_last_assistant_from_messages(self, thread_messages: Optional[List[Dict]]) -> str:
        for message in reversed(thread_messages or []):
            if (message.get("role") or "").strip().lower() != "assistant":
                continue
            content = (message.get("content") or "").strip()
            if content:
                return content
        return ""

    def _get_last_assistant_from_store(self, thread_id: str) -> str:
        try:
            rows = get_thread_messages(thread_id)
            for message in reversed(rows or []):
                if (message.get("role") or "").strip().lower() != "assistant":
                    continue
                content = (message.get("content") or "").strip()
                if content:
                    return content
        except Exception:
            logger.exception("Failed reading persisted thread messages for transformation")
        return ""

    def _get_last_assistant(self, thread_id: str, thread_messages: Optional[List[Dict]] = None) -> str:
        # Prefer persisted thread history as source-of-truth to avoid stale
        # client payloads selecting an older assistant turn.
        from_store = self._get_last_assistant_from_store(thread_id=thread_id)
        if from_store:
            return from_store
        return self._get_last_assistant_from_messages(thread_messages)

    def _refresh_stm(
        self,
        user_id: str,
        thread_id: str,
        thread_messages: Optional[List[Dict]] = None
    ) -> None:
        """
        Refreshes in-memory STM from provided thread messages when available,
        otherwise from persisted DB messages.
        """
        if thread_messages is not None:
            self._refresh_stm_from_messages(
                user_id=user_id,
                thread_id=thread_id,
                thread_messages=thread_messages
            )
            return

        self._refresh_stm_from_store(user_id=user_id, thread_id=thread_id)

    def _refresh_stm_from_messages(
        self,
        user_id: str,
        thread_id: str,
        thread_messages: List[Dict]
    ) -> None:
        recent_messages = (thread_messages or [])[-8:]
        self.memory.replace_thread_stm(
            user_id=user_id,
            thread_id=thread_id,
            messages=recent_messages
        )

    def _refresh_stm_from_store(self, user_id: str, thread_id: str) -> None:
        """
        Syncs in-memory STM with persisted thread messages.
        Keeps only last 4 turns (8 messages) for deterministic prompt context.
        """
        try:
            rows = get_thread_messages(thread_id)
            if not rows:
                self.memory.replace_thread_stm(user_id=user_id, thread_id=thread_id, messages=[])
                return

            recent_messages = rows[-8:]
            self.memory.replace_thread_stm(
                user_id=user_id,
                thread_id=thread_id,
                messages=recent_messages
            )
        except Exception:
            logger.exception("Failed syncing STM from persisted messages")

    # ============================================================
    # THREAD MANAGEMENT
    # ============================================================

    def _resolve_thread(self, user_id: str, thread_id: Optional[str]) -> str:
        normalized = (thread_id or "").strip()
        if normalized and normalized.lower() != "new":
            return normalized

        # Never reuse implicit per-user active thread here.
        # Missing/`new` thread ids get a fresh isolated thread scope.
        return f"thread_{uuid.uuid4().hex[:8]}"

    # ============================================================
    # MEMORY INJECTION (For Knowledge Queries)
    # ============================================================

    def _inject_memory(
        self,
        query: str,
        user_id: str,
        thread_id: str,
        context_prefix: str = "",
    ) -> str:
        memory_block = [
            "Memory protocol guidance:",
            "- Resolve references like above/that/previous from short-term history first.",
            "- Apply user and global preferences silently.",
            "- Use long-term memory only when relevant to the current query.",
            "- Never expose memory internals in the answer.",
            "",
            "Short-term memory (last 4 turns):",
        ]

        qa_window = self.memory.build_qa_window(user_id, thread_id, 4)
        cleaned_window = self._clean_memory_text(qa_window, max_chars=1400)
        memory_block.append(cleaned_window or "(none)")

        memory_block.extend(
            [
                "",
                "Chat-history references (last 4 exchanges):",
                self._build_reference_window(user_id=user_id, thread_id=thread_id, max_pairs=4) or "(none)",
            ]
        )

        prefix = (context_prefix or "").strip()
        user_pref = self._extract_pref_section(prefix, "### User Preferences")
        global_pref = self._extract_pref_section(prefix, "### User Global Preferences")

        memory_block.extend(["", "User preferences (session/thread):", user_pref or "(none)"])
        memory_block.extend(["", "User global preferences:", global_pref or "(none)"])

        ltm_context = self.memory.get_ltm(user_id)
        ltm_lines: List[str] = []
        for entry in ltm_context[-5:]:
            cleaned_entry = self._clean_memory_text(entry.get("content", ""), max_chars=160)
            if cleaned_entry:
                ltm_lines.append(f"- {cleaned_entry}")
        memory_block.extend(["", "Long-term memory (use only if relevant):", "\n".join(ltm_lines) or "(none)"])

        injected_memory = "\n".join(memory_block).strip()
        return f"{injected_memory}\n\nCurrent user query (highest priority):\n{query}"

    @staticmethod
    def _clean_memory_text(value: str, max_chars: int) -> str:
        text = (value or "").replace("\r\n", "\n").strip()
        if not text:
            return ""
        lines = []
        for raw in text.split("\n"):
            line = " ".join(raw.split()).strip()
            if not line:
                continue
            if line.lower().startswith("### "):
                line = line[4:].strip()
            lines.append(line)
        cleaned = "\n".join(lines).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 3].rstrip() + "..."

    def _build_reference_window(self, user_id: str, thread_id: str, max_pairs: int = 4) -> str:
        messages = self.memory.load_stm(user_id=user_id, thread_id=thread_id)
        if not messages:
            return ""

        pairs: List[str] = []
        pending_user = ""
        for msg in messages:
            role = (msg.get("role") or "").strip().lower()
            content = self._clean_memory_text(msg.get("content") or "", max_chars=220)
            if not content:
                continue
            if role == "user":
                pending_user = content
                continue
            if role == "assistant" and pending_user:
                pairs.append(f"- User: {pending_user}\n  Assistant: {content}")
                pending_user = ""

        if not pairs:
            return ""
        return "\n".join(pairs[-max_pairs:])

    @staticmethod
    def _extract_pref_section(text: str, heading: str) -> str:
        raw = (text or "").replace("\r\n", "\n")
        if not raw or heading not in raw:
            return ""

        start = raw.find(heading)
        if start < 0:
            return ""
        after = raw[start + len(heading):]
        next_heading = re.search(r"\n###\s+", after)
        body = after[: next_heading.start()] if next_heading else after
        return body.strip()

    # ============================================================
    # LLM QUERY CLASSIFIER
    # ============================================================

    def _classify_query_type(self, query: str) -> str:
        # Deterministic short-circuit for common follow-up formatting requests.
        if self._looks_like_transformation(query):
            return "transformation"

        prompt = f"""
### ROLE:
You are a strict intent classifier for an AI system.

### TASK:
Classify the user query into EXACTLY ONE of the following categories:

1. knowledge
2. transformation

### CATEGORY DEFINITIONS:

knowledge:
- User is asking for new information.
- Requires factual explanation.
- Requires document retrieval.
- Asks about definitions, concepts, or explanations.
- Does NOT depend on previous assistant responses.

transformation:
- User refers to previous content.
- Contains words like: above, previous, that, it, this answer.
- Requests summarization, rewriting, formatting, bullet points, simplification.
- Requests converting earlier content into another format.
- Requests like: "make the above response in <format>".
- Depends on previous assistant response.

### IMPORTANT RULES:
- Output must be EXACTLY one word.
- Output must be lowercase.
- Do NOT explain your answer.
- Do NOT add punctuation.
- Do NOT add extra text.

### USER QUERY:
{query}

### OUTPUT:
"""

        payload = {
            "model": CLASSIFIER_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": 5
            }
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=30)

            if response.status_code != 200:
                return "knowledge"

            result = response.json().get("response", "").strip().lower()

            if "transformation" in result:
                return "transformation"

            return "knowledge"

        except Exception:
            return "knowledge"

    @staticmethod
    def _looks_like_transformation(query: str) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False
        has_transform_verb = bool(
            re.search(
                r"\b(format|reformat|rewrite|convert|summari[sz]e|shorten|simplify|paraphrase|make)\b",
                text,
            )
        )
        has_format_target = bool(
            re.search(
                r"\b(table|tabular|bullets?|points?|list|markdown|json|steps?)\b",
                text,
            )
        )
        has_reference = bool(re.search(r"\b(above|previous|earlier|that|this|it|response|answer)\b", text))
        return (has_transform_verb and has_reference) or (
            has_transform_verb and has_format_target and len(text.split()) <= 20
        )

    @staticmethod
    def _extract_inline_transformation_source(query: str) -> tuple[str, str]:
        text = (query or "").strip()
        if not text:
            return "", ""

        lowered = text.lower()
        markers = [
            "text in canvas:",
            "canvas text:",
            "source text:",
            "text:",
        ]

        for marker in markers:
            idx = lowered.find(marker)
            if idx < 0:
                continue

            instruction = text[:idx].strip(" \n:-")
            source = text[idx + len(marker):].strip()
            # Require enough source content to avoid false positives (e.g., "text: yes").
            if len(source) < 80:
                continue
            return source, instruction

        # Fallback heuristic for multi-line format requests:
        # first line carries instruction and remaining block is explicit source.
        lines = text.splitlines()
        if len(lines) >= 3:
            first_line = lines[0].strip().lower()
            if re.search(r"\b(table|tabular|format|reformat|convert|transform)\b", first_line):
                source_block = "\n".join(lines[1:]).strip()
                if len(source_block) >= 120:
                    return source_block, lines[0].strip()

        return "", ""

    def _transform_previous_answer(self, previous_answer: str, instruction: str) -> str:
        source = (previous_answer or "").strip()
        request = (instruction or "").strip()
        if not source or not request:
            return ""

        prompt = self.prompt_builder.build_transformation_prompt(
            instruction=request,
            source_text=source,
        )
        payload = {
            "model": TRANSFORM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.3,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "num_predict": 900,
            },
        }

        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=90)
            if response.status_code != 200:
                return ""
            return (response.json().get("response") or "").strip()
        except Exception:
            return ""
