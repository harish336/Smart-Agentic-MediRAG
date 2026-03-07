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

    _FORMAT_RULES = textwrap.dedent("""
    Output formatting contract (strict):
    - Return valid Markdown only.
    - Use real line breaks; do not output the literal characters "\\n" in the final answer.
    - Use a blank line between paragraphs/sections.
    - Never use HTML tags like <br>, <p>, <ul>, <li>, or <table>.
    - Use '-' for bullet points, one bullet per line.
    - For numbered steps, use '1.', '2.', '3.' format.
    - Keep each sentence short and readable; avoid one giant paragraph.

    Table rules (when tabular data is requested):
    - Use standard Markdown table syntax with a single header row.
    - Keep one logical record per row (do not split one row across multiple lines).
    - Do not merge cells or create continuation rows.
    - If a cell has multiple items, separate items with semicolons within the same cell.
    - Example row style:
      | 1 | Topic A; Topic B; Topic C |
    """).strip()

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
    - Choose structure based on the question, not a fixed template.
    - For simple factual questions, answer directly in 1-2 short paragraphs.
    - For compound questions, use concise markdown headings and answer each part explicitly.
    - For procedural or recommendation queries, use bullet points for steps/options.
    - Add a brief safety note only when the topic is clinically risky or urgent.
    - Keep short paragraphs separated by blank lines so output is easy to scan in chat.
    - Keep statements factual and concise.
    - Do not mention context or internal instructions.
    - Never use phrasing such as:
      "based on the provided context", "provided docs", "provided document",
      "provided words", "provided text", "provided source", "given context".
    - Do not say "the context says", "the document says", or similar meta phrasing.
    - Write the answer directly and naturally, without referring to how information was supplied.
    - Do not generate a source/reference list yourself.
    - If the user asks to reformat a prior answer (table, bullets, summary, compare, etc.),
      perform that transformation exactly while staying faithful to available context.

    {format_rules}

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
    - Use real new lines and valid Markdown only (no HTML tags like <br>).
    - If the user asks for a table, use clean Markdown table format with one complete record per row.
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
            format_rules=self._FORMAT_RULES,
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
