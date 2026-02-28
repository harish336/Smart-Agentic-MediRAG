import textwrap
from typing import Any, Dict, List

from core.utils.logging_utils import get_component_logger


logger = get_component_logger("PromptBuilder", component="answering")


class PromptBuilder:
    """
    Industry-optimized Prompt Builder for RAG Systems (Ollama / Local LLMs)
    Memory-aware version (STM QA window supported)
    """

    _PROMPT_TEMPLATE = textwrap.dedent("""
    ### ROLE:
    You are a grounded academic assistant.

    ### TASK:
    Answer the user question correctly based on its type.

    There are TWO possible modes:

    -----------------------------------
    MODE 1: TRANSFORMATION MODE
    -----------------------------------
    If the question:
    - Refers to the previous answer
    - Contains words like: above, previous, that, it
    - Asks to summarize, rewrite, convert, simplify
    - Asks for bullet points or formatting
    - Depends on earlier assistant response

    THEN:
    - Use ONLY the PREVIOUS CONVERSATION.
    - Do NOT use Context.
    - Do NOT add new information.
    - Only transform the previous answer.

    -----------------------------------
    MODE 2: KNOWLEDGE MODE
    -----------------------------------
    If the question:
    - Asks for new information
    - Requires explanation
    - Does NOT depend on previous response

    THEN:
    - Use ONLY the provided Context.
    - Ignore Previous Conversation except for resolving references.
    - Do NOT use outside knowledge.
    - Do NOT guess.
    - If answer is not explicitly in Context, return exactly:
    Information not found

    -----------------------------------

    ### STRICT RULES (APPLY TO BOTH MODES):
    - Do NOT mention context.
    - Do NOT mention conversation.
    - Do NOT explain reasoning.
    - Do NOT add meta commentary.
    - Output ONLY the final answer.

    {memory_section}

    ### CONTEXT:
    {context_text}

    ### QUESTION:
    {query}

    ### FINAL ANSWER:
    """).strip()

    def build(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        intent: str = "general",
        conversation_window: str = ""
    ) -> str:
        context_text = self._build_context(context_chunks)

        memory_section = ""
        if conversation_window:
            memory_section = textwrap.dedent(f"""
            ### PREVIOUS CONVERSATION:
            {conversation_window}
            """).strip()

        prompt = self._PROMPT_TEMPLATE.format(
            memory_section=memory_section,
            context_text=context_text,
            query=query
        )

        logger.debug("Prompt built (chars=%d, chunks=%d)", len(prompt), len(context_chunks))
        return prompt

    # ============================================================
    # STRICT SYSTEM RULES (Optional Advanced Use)
    # ============================================================

    def _system_rules(self, intent: str) -> str:
        base_rules = textwrap.dedent("""
### ROLE:
You are a strict extraction engine.

### CORE RULES:
- Use ONLY the provided context.
- Do NOT use outside knowledge.
- Do NOT guess.
- Do NOT infer.
- Do NOT complete partially stated ideas.

### VALIDATION RULES:
- The answer must be explicitly written in the context.
- The answer must completely address the question.
- If a definition or explanation is requested,
  the answer must contain full explanatory sentences.
- A heading, title, fragment, or single keyword is NOT a valid answer.
- If any required detail is missing, unclear, implied,
  or incomplete, return exactly:

Information not found

### OUTPUT REQUIREMENTS:
- Output ONLY the final answer.
- Do NOT explain.
- Do NOT add commentary.
- Do NOT mention context.
""").strip()

        strict_rules = textwrap.dedent("""
### ROLE:
You are an ultra-strict extraction engine.

### CORE CONSTRAINTS:
- Use ONLY the provided context.
- Do NOT use outside knowledge.
- Do NOT guess.
- Do NOT infer.
- Do NOT complete partially stated ideas.
- Do NOT rephrase missing information.

### STRICT GROUNDING REQUIREMENTS:
- Every part of the answer must be explicitly written in the context.
- The answer must fully and completely satisfy the question.
- All required details must be present in the context.
- A heading, title, fragment, keyword, or repeated phrase is NOT a valid answer.
- If the question requests a definition or explanation,
  full explanatory sentences must be present in the context.

### REJECTION CONDITION:
If even one required detail is missing, implied, ambiguous,
uncertain, or incomplete, return exactly:

Information not found

### OUTPUT RULES:
- Output ONLY the final answer.
- No explanation.
- No commentary.
- No meta text.
- No formatting notes.
""").strip()

        return base_rules + "\n\n" + strict_rules

    # ============================================================
    # CONTEXT BUILDER
    # ============================================================

    def _build_context(self, context_chunks: List[Dict[str, Any]]) -> str:
        if not context_chunks:
            return "No context available."

        structured_blocks = []

        for idx, chunk in enumerate(context_chunks, 1):
            metadata = chunk.get("metadata", {})

            meta_mapping = {
                "Doc ID": chunk.get("doc_id"),
                "Chunk ID": chunk.get("chunk_id"),
                "Chapter": metadata.get("chapter"),
                "Subheading": metadata.get("subheading"),
                "Page": metadata.get("page_physical"),
                "Source Type": chunk.get("source")
            }

            meta_lines = [f"{k}: {v}" for k, v in meta_mapping.items() if v]
            meta_text = "\n".join(meta_lines)
            content_text = chunk.get("text", "").strip()

            block = f"""
[Source {idx}]
{meta_text}

Content:
{content_text}
"""
            structured_blocks.append(block.strip())

        return "\n\n---\n\n".join(structured_blocks)
