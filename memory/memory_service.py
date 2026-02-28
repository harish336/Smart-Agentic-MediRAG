"""
SmartChunk-RAG — Memory Service

Handles:
- Short-Term Memory (STM) → user_id + thread_id scoped
- Long-Term Memory (LTM) → user_id scoped
- Sliding window trimming
- Safe isolation per user
"""

import uuid
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

        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }

        self._stm[user_id][thread_id].append(message)

        # Apply sliding window
        if len(self._stm[user_id][thread_id]) > self.max_stm_messages:
            self._stm[user_id][thread_id] = \
                self._stm[user_id][thread_id][-self.max_stm_messages:]

        logger.debug(
            f"STM updated → user={user_id}, thread={thread_id}"
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
        logger.info(f"Cleared STM → user={user_id}, thread={thread_id}")

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
            self._ltm[user_id] = \
                self._ltm[user_id][-self.max_ltm_entries:]

        logger.debug(f"LTM stored → user={user_id}")

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
        logger.info(f"Cleared LTM → user={user_id}")

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
