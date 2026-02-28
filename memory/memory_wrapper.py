"""
SmartChunk-RAG — Memory Wrapper
"""

import uuid
from typing import Dict, Optional
import requests

from memory.memory_service import MemoryService
from answering.answering_agent import AnsweringAgent
from core.utils.logging_utils import get_component_logger


OLLAMA_URL = "http://localhost:11434/api/generate"
CLASSIFIER_MODEL = "mistral:7b-instruct"


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
        self.active_threads = {}

    # ============================================================
    # MAIN ENTRY
    # ============================================================

    def answer(
        self,
        user_id: str,
        query: str,
        thread_id: Optional[str] = None
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

            # --------------------------------------------
            # Classify Query Type (LLM)
            # --------------------------------------------

            query_type = self._classify_query_type(query)
            logger.info(f"Query classified as: {query_type}")

            # --------------------------------------------
            # Routing Logic
            # --------------------------------------------

            if query_type == "transformation":

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

                enriched_query = f"""
Previous Answer:
{last_answer}

Instruction:
{query}
"""

            else:
                enriched_query = self._inject_memory(
                    query=query,
                    user_id=user_id,
                    thread_id=thread_id
                )

            # --------------------------------------------
            # Call Pure RAG Agent
            # --------------------------------------------

            result = self.agent.answer(
                query=enriched_query,       # used for prompt
                retrieval_query=query       # ONLY clean user question
            )

            # --------------------------------------------
            # Persist STM
            # --------------------------------------------

            if result.get("response"):
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
                    content=result["response"]
                )

            result["thread_id"] = thread_id
            result["user_id"] = user_id

            return result

        except Exception:
            logger.exception("Error inside memory wrapper")
            return {"response": "", "citations": []}

    # ============================================================
    # THREAD MANAGEMENT
    # ============================================================

    def _resolve_thread(self, user_id: str, thread_id: Optional[str]) -> str:

        if thread_id and thread_id.strip().lower() != "new":
            self.active_threads[user_id] = thread_id
            return thread_id

        if thread_id and thread_id.strip().lower() == "new":
            new_thread = f"thread_{uuid.uuid4().hex[:8]}"
            self.active_threads[user_id] = new_thread
            return new_thread

        if user_id in self.active_threads:
            return self.active_threads[user_id]

        new_thread = f"thread_{uuid.uuid4().hex[:8]}"
        self.active_threads[user_id] = new_thread
        return new_thread

    # ============================================================
    # MEMORY INJECTION (For Knowledge Queries)
    # ============================================================

    def _inject_memory(self, query: str, user_id: str, thread_id: str) -> str:

        memory_block = []

        ltm_context = self.memory.get_ltm(user_id)
        if ltm_context:
            memory_block.append("### User Long-Term Memory:")
            for entry in ltm_context[-5:]:
                memory_block.append(f"- {entry['content']}")

        qa_window = self.memory.build_qa_window(user_id, thread_id, 4)
        if qa_window:
            memory_block.append("\n### Recent Conversation:")
            memory_block.append(qa_window)

        if memory_block:
            injected_memory = "\n".join(memory_block)
            return f"{injected_memory}\n\n### Current User Query:\n{query}"

        return query

    # ============================================================
    # LLM QUERY CLASSIFIER
    # ============================================================

    def _classify_query_type(self, query: str) -> str:

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
