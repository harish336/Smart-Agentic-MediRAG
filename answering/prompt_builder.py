import textwrap
from typing import List, Dict, Any

class PromptBuilder:
    """
    Industry-optimized Prompt Builder for RAG Systems (Ollama / Local LLMs)
    """

    def build(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        intent: str = "general"
    ) -> str:
        
        context_text = self._build_context(context_chunks)
        system_rules = self._system_rules(intent)

        # Using pseudo-XML tags helps instruction-tuned local models isolate information
        prompt = f"""
<system>
{system_rules}
</system>

<context>
{context_text}
</context>

<question>
{query}
</question>

<instructions>
- Return ONLY the final answer.
- Adhere strictly to the FORBIDDEN PHRASES list in the system rules.
- Ensure Unicode-safe output.
</instructions>
"""
        return textwrap.dedent(prompt).strip()

    # ============================================================
    # SYSTEM RULES & STRICT CONTROL
    # ============================================================

    def _system_rules(self, intent: str) -> str:
        # Core rules applied to every prompt
        base_rules = textwrap.dedent("""
            You are a highly accurate, direct, and professional AI assistant.

            GENERAL RULES:
            - Be precise, highly structured, and concise.
            - Use bullet points when listing items.
            - Use numbered steps for procedures.
            - Do not hallucinate or invent facts.
            - If including URLs, place them after two newlines at the bottom.

            TONE & STYLE (STRICTLY ENFORCED):
            - Answer directly. No conversational filler.
            - Do NOT explain your thought process.
            
            FORBIDDEN PHRASES (NEVER USE THESE):
            - "Based on the provided context..."
            - "According to the book/document..."
            - "As stated in the text..."
            - "Here is the information..."
            - "The context mentions that..."
        """).strip()

        # Domain-specific grounding rules (Medical, Book, etc.)
        if intent in ["medical", "book"]:
            strict_rules = textwrap.dedent("""
                
                STRICT GROUNDING RULES:
                - Answer strictly and exclusively using the provided <context>.
                - Do NOT use external knowledge, speculate, or assume missing data.
                - If the context does not contain the answer, return exactly: "INSUFFICIENT_DATA". Do not output anything else.
            """)
            return base_rules + strict_rules

        return base_rules

    # ============================================================
    # CONTEXT BUILDER
    # ============================================================

    def _build_context(self, context_chunks: List[Dict[str, Any]]) -> str:
        if not context_chunks:
            return "No context available."

        structured_blocks = []

        for idx, chunk in enumerate(context_chunks, 1):
            metadata = chunk.get("metadata", {})
            
            # Dynamically build metadata lines only if the data exists 
            # (Prevents confusing the LLM with "Chapter: None")
            meta_lines = []
            if chunk.get("doc_id"): meta_lines.append(f"Doc ID: {chunk.get('doc_id')}")
            if chunk.get("chunk_id"): meta_lines.append(f"Chunk ID: {chunk.get('chunk_id')}")
            if metadata.get("chapter"): meta_lines.append(f"Chapter: {metadata.get('chapter')}")
            if metadata.get("subheading"): meta_lines.append(f"Subheading: {metadata.get('subheading')}")
            if metadata.get("page_physical"): meta_lines.append(f"Page: {metadata.get('page_physical')}")
            if chunk.get("source"): meta_lines.append(f"Source Type: {chunk.get('source')}")

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