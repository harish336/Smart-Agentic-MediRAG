"""
SmartChunk-RAG - Memory Service

Handles:
- Short-Term Memory (STM) -> user_id + thread_id scoped
- Long-Term Memory (LTM) -> user_id scoped
- Sliding window trimming
- Safe isolation per user
"""

import uuid
import re
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime
from core.utils.logging_utils import get_component_logger


# ============================================================
# Logger
# ============================================================

logger = get_component_logger("MemoryService", component="answering")


# ============================================================
# Memory Service
# ============================================================

class MemoryService:
    _ASSISTANT_STM_BLOCKLIST_EXACT = {
        "dont have an answer",
        "i don't have enough reliable context to answer that yet. please share a bit more detail.",
        "i dont have enough reliable context to answer that yet. please share a bit more detail.",
        "no response.",
    }
    _ASSISTANT_STM_BLOCKLIST_PATTERNS = (
        r"^error\b",
        r"\binternal server error\b",
        r"\bserver error\b",
        r"\ban error occurred\b",
        r"\bexception\b",
        r"\btraceback\b",
        r"\bfailed to\b",
        r"\bunable to\b",
    )

    def __init__(
        self,
        max_stm_messages: int = 20,
        max_ltm_entries: int = 500
    ):
        """
        :param max_stm_messages: Sliding window size (per thread)
        :param max_ltm_entries: Max long-term memory per user
        """

        logger.info("=" * 70)
        logger.info("[MEMORY SERVICE] Initializing...")
        logger.info("=" * 70)

        self.max_stm_messages = max_stm_messages
        self.max_ltm_entries = max_ltm_entries

        # Short-Term Memory:
        # { user_id: { thread_id: [message_dicts] } }
        self._stm = defaultdict(lambda: defaultdict(list))

        # Long-Term Memory:
        # { user_id: [memory_entries] }
        self._ltm = defaultdict(list)

        logger.info("[MEMORY SERVICE] Ready")
        logger.info("=" * 70)

    def build_qa_window(
        self,
        user_id: str,
        thread_id: str,
        max_turns: int = 4
    ) -> str:
        """
        Builds formatted Q/A conversation window like:
        Q1: ...
        A1: ...
        Q2: ...
        A2: ...
        """
        messages = self._stm[user_id][thread_id]
        return self._build_qa_window_from_messages(messages, max_turns=max_turns)

    def _build_qa_window_from_messages(
        self,
        messages: List[Dict],
        max_turns: int = 4
    ) -> str:
        if not messages:
            return ""

        # Take last 2 * max_turns messages
        window = messages[-(max_turns * 2):]

        formatted_blocks = []
        turn_counter = 1
        i = 0

        while i < len(window):
            if window[i]["role"] == "user":
                q = window[i]["content"]
                a = ""

                # If next message is assistant
                if i + 1 < len(window) and window[i + 1]["role"] == "assistant":
                    a = window[i + 1]["content"]
                    i += 2
                else:
                    i += 1

                formatted_blocks.append(
                    f"Q{turn_counter}: {q}\nA{turn_counter}: {a}"
                )

                turn_counter += 1
            else:
                i += 1

        return "\n\n".join(formatted_blocks)

    # ============================================================
    # SHORT-TERM MEMORY (Thread Scoped)
    # ============================================================

    def load_stm(
        self,
        user_id: str,
        thread_id: str
    ) -> List[Dict]:
        """
        Returns conversation history for a specific thread.
        """
        return self._stm[user_id][thread_id]

    def append_stm(
        self,
        user_id: str,
        thread_id: str,
        role: str,
        content: str
    ) -> None:
        """
        Append a message to STM.
        """

        normalized_role = (role or "").strip().lower()
        normalized_content = self._normalize_message_text(content)
        if not normalized_content:
            return
        if not self._should_store_stm_message(normalized_role, normalized_content):
            return

        message = {
            "id": str(uuid.uuid4()),
            "role": normalized_role or role,
            "content": normalized_content,
            "timestamp": datetime.utcnow().isoformat()
        }

        messages = self._stm[user_id][thread_id]
        if messages:
            last = messages[-1]
            if (
                (last.get("role") or "").strip().lower() == normalized_role
                and (last.get("content") or "") == normalized_content
            ):
                last["timestamp"] = datetime.utcnow().isoformat()
                return

        messages.append(message)

        # Apply sliding window
        if len(self._stm[user_id][thread_id]) > self.max_stm_messages:
            self._stm[user_id][thread_id] = self._stm[user_id][thread_id][-self.max_stm_messages:]

        logger.debug(
            f"STM updated -> user={user_id}, thread={thread_id}"
        )

    def replace_thread_stm(
        self,
        user_id: str,
        thread_id: str,
        messages: List[Dict]
    ) -> None:
        """
        Replaces STM for a thread with normalized persisted messages.
        """
        normalized: List[Dict] = []
        for message in messages or []:
            role = (message.get("role") or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            normalized_content = self._normalize_message_text(message.get("content") or "")
            if not normalized_content:
                continue
            if not self._should_store_stm_message(role, normalized_content):
                continue
            normalized.append(
                {
                    "id": message.get("id") or str(uuid.uuid4()),
                    "role": role,
                    "content": normalized_content,
                    "timestamp": message.get("timestamp") or datetime.utcnow().isoformat()
                }
            )

        deduped: List[Dict] = []
        for message in normalized:
            if deduped:
                prev = deduped[-1]
                if prev["role"] == message["role"] and prev["content"] == message["content"]:
                    deduped[-1]["timestamp"] = message["timestamp"]
                    continue
            deduped.append(message)

        if len(deduped) > self.max_stm_messages:
            deduped = deduped[-self.max_stm_messages:]

        self._stm[user_id][thread_id] = deduped

    def upsert_latest_assistant_stm(
        self,
        user_id: str,
        thread_id: str,
        content: str
    ) -> None:
        """
        Updates latest assistant message in STM; appends if missing.
        """
        normalized_content = self._normalize_message_text(content)
        if not self._should_store_stm_message("assistant", normalized_content):
            return

        messages = self._stm[user_id][thread_id]
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].get("role") == "assistant":
                messages[idx]["content"] = normalized_content
                messages[idx]["timestamp"] = datetime.utcnow().isoformat()
                return

        self.append_stm(
            user_id=user_id,
            thread_id=thread_id,
            role="assistant",
            content=normalized_content
        )

    def clear_thread(
        self,
        user_id: str,
        thread_id: str
    ) -> None:
        """
        Clears a specific thread's STM.
        """
        self._stm[user_id][thread_id] = []
        logger.info(f"Cleared STM -> user={user_id}, thread={thread_id}")

    # ============================================================
    # LONG-TERM MEMORY (User Scoped)
    # ============================================================

    def store_ltm(
        self,
        user_id: str,
        content: str,
        category: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Store long-term memory for a user.
        """

        entry = {
            "id": str(uuid.uuid4()),
            "content": content,
            "category": category or "general",
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        self._ltm[user_id].append(entry)

        # Limit memory growth
        if len(self._ltm[user_id]) > self.max_ltm_entries:
            self._ltm[user_id] = self._ltm[user_id][-self.max_ltm_entries:]

        logger.debug(f"LTM stored -> user={user_id}")

    def get_ltm(
        self,
        user_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve long-term memory entries.
        """

        memories = self._ltm[user_id]

        if category:
            memories = [
                m for m in memories
                if m["category"] == category
            ]

        return memories

    def clear_ltm(self, user_id: str) -> None:
        """
        Clears all long-term memory for user.
        """
        self._ltm[user_id] = []
        logger.info(f"Cleared LTM -> user={user_id}")

    # ============================================================
    # OPTIONAL: MEMORY EXPORT (Debug / Persistence Hook)
    # ============================================================

    def export_user_memory(self, user_id: str) -> Dict:
        """
        Returns full memory snapshot for a user.
        Useful for persistence layer or debugging.
        """
        return {
            "stm": self._stm[user_id],
            "ltm": self._ltm[user_id]
        }

    # ============================================================
    # HELPERS
    # ============================================================

    def get_last_assistant_response(
        self,
        user_id: str,
        thread_id: str
    ) -> str:
        """
        Returns the most recent assistant response for a thread.
        """
        messages = self._stm[user_id][thread_id]
        for message in reversed(messages):
            if message.get("role") == "assistant":
                return message.get("content", "")
        return ""

    @staticmethod
    def _normalize_message_text(value: str) -> str:
        return " ".join((value or "").split()).strip()

    def should_store_assistant_stm(self, content: str) -> bool:
        normalized = self._normalize_message_text(content)
        return self._should_store_stm_message("assistant", normalized)

    def _should_store_stm_message(self, role: str, content: str) -> bool:
        normalized_role = (role or "").strip().lower()
        normalized_content = self._normalize_message_text(content)
        if not normalized_content:
            return False
        if normalized_role != "assistant":
            return True

        lowered = normalized_content.lower()
        if lowered in self._ASSISTANT_STM_BLOCKLIST_EXACT:
            return False

        for pattern in self._ASSISTANT_STM_BLOCKLIST_PATTERNS:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return False

        return True
