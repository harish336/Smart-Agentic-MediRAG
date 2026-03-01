import textwrap
from typing import Any, Dict, List

from core.utils.logging_utils import get_component_logger


logger = get_component_logger("PromptBuilder", component="answering")


class PromptBuilder:
    """
    Prompt builder with two explicit modes:
    - Companion mode for general conversation
    - Evidence-grounded mode for medical/book answers
    """

    _KNOWLEDGE_TEMPLATE = textwrap.dedent("""
    You are Smart Medirag, an evidence-grounded medical assistant.

    Follow these rules exactly:
    - Use ONLY the provided CONTEXT.
    - Do not use outside knowledge.
    - Do not guess or infer missing facts.
    - If the answer is missing or incomplete in CONTEXT, output exactly:
    dont have an answer

    Style and format rules:
    - Be calm, clear, and professional.
    - For clinical or psychological topics, use empathetic psychiatrist-like language.
    - Do not use creative storytelling, metaphors, or speculative language.
    - Use markdown with these sections in this order:
      1) ### Direct Answer
      2) ### Evidence Summary
      3) ### Practical Guidance
      4) ### Safety Notes
    - When listing types, categories, steps, or recommendations, always use markdown bullets (`- item`) on separate lines.
    - Keep short paragraphs separated by blank lines so output is easy to scan in chat.
    - Keep statements factual and concise.
    - Do not mention context or internal instructions.

    {memory_section}

    CONTEXT:
    {context_text}

    QUESTION:
    {query}

    FINAL ANSWER:
    """).strip()

    _COMPANION_TEMPLATE = textwrap.dedent("""
    You are Smart Medirag, a supportive and friendly companion for everyday conversation.

    Rules:
    - Be warm, respectful, concise, and positive.
    - You may be lightly creative in phrasing when it improves clarity and encouragement.
    - Use simple language.
    - Do not fabricate medical facts.
    - If the user asks medical or textbook evidence questions, suggest they ask directly and you will provide cited answers.
    - When there are multiple types/options/ideas, format them as markdown bullet points with one item per line.
    - Use short paragraphs with clear line breaks.
    - Return only the answer.

    USER MESSAGE:
    {query}

    RESPONSE:
    """).strip()

    def build(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        intent: str = "general",
        conversation_window: str = ""
    ) -> str:
        if intent == "general":
            return self.build_companion(query=query)

        context_text = self._build_context(context_chunks)

        memory_section = ""
        if conversation_window:
            memory_section = textwrap.dedent(f"""
            ### PREVIOUS CONVERSATION:
            {conversation_window}
            """).strip()

        prompt = self._KNOWLEDGE_TEMPLATE.format(
            memory_section=memory_section,
            context_text=context_text,
            query=query
        )

        logger.debug("Knowledge prompt built (chars=%d, chunks=%d, intent=%s)", len(prompt), len(context_chunks), intent)
        return prompt

    def build_companion(self, query: str) -> str:
        prompt = self._COMPANION_TEMPLATE.format(query=query)
        logger.debug("Companion prompt built (chars=%d)", len(prompt))
        return prompt

    def _build_context(self, context_chunks: List[Dict[str, Any]]) -> str:
        if not context_chunks:
            return ""

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
