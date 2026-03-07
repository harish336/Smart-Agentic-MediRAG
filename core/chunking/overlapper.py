"""
Overlapper Module

Purpose:
- Apply pre-overlap and post-overlap to text chunks
- Preserve chunk metadata
"""

import re

from config.system_loader import get_system_config


class ChunkOverlapper:

    def __init__(self):
        print("[OVERLAP] Initialized")
        cfg = get_system_config().get("overlap", {})
        self.pre_overlap = int(cfg.get("pre_overlap", 150))
        self.post_overlap = int(cfg.get("post_overlap", 150))

    def apply(self, chunks: list) -> list:

        if not chunks:
            return []

        overlapped = []

        for i, chunk in enumerate(chunks):

            new_chunk = chunk.copy()
            text = new_chunk.get("text", "")
            has_table = bool(new_chunk.get("table_html"))

            # Pre overlap
            if i > 0 and self.pre_overlap > 0 and not has_table:
                prev_chunk = chunks[i - 1]
                if self._is_context_compatible(prev_chunk, chunk) and not prev_chunk.get("table_html"):
                    prev_text = prev_chunk.get("text", "")
                    pre = self._tail_by_sentences(prev_text, self.pre_overlap)
                    if pre:
                        text = pre + "\n" + text

            # Post overlap
            if i < len(chunks) - 1 and self.post_overlap > 0 and not has_table:
                next_chunk = chunks[i + 1]
                if self._is_context_compatible(next_chunk, chunk) and not next_chunk.get("table_html"):
                    next_text = next_chunk.get("text", "")
                    post = self._head_by_sentences(next_text, self.post_overlap)
                    if post:
                        text += "\n" + post

            new_chunk["text"] = text
            overlapped.append(new_chunk)

        return overlapped

    def _is_context_compatible(self, candidate: dict, current: dict) -> bool:
        if candidate.get("page_type") != current.get("page_type"):
            return False

        c_chapter = (candidate.get("chapter") or "").strip().lower()
        n_chapter = (current.get("chapter") or "").strip().lower()
        if c_chapter and n_chapter and c_chapter != n_chapter:
            return False

        c_sub = (candidate.get("subheading") or "").strip().lower()
        n_sub = (current.get("subheading") or "").strip().lower()
        if c_sub and n_sub and c_sub != n_sub:
            return False

        return True

    def _split_sentences(self, text: str) -> list:
        source = re.sub(r"\s+", " ", (text or "").strip())
        if not source:
            return []

        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", source) if s.strip()]
        if parts:
            return parts
        return [source]

    def _word_count(self, text: str) -> int:
        return len(re.findall(r"\S+", text or ""))

    def _tail_by_sentences(self, text: str, max_words: int) -> str:
        source = (text or "").strip()
        if not source or max_words <= 0:
            return ""

        sentences = self._split_sentences(source)
        selected = []
        total_words = 0
        for sentence in reversed(sentences):
            count = self._word_count(sentence)
            if selected and (total_words + count) > max_words:
                break
            selected.append(sentence)
            total_words += count
            if total_words >= max_words:
                break
        return " ".join(reversed(selected)).strip()

    def _head_by_sentences(self, text: str, max_words: int) -> str:
        source = (text or "").strip()
        if not source or max_words <= 0:
            return ""

        sentences = self._split_sentences(source)
        selected = []
        total_words = 0
        for sentence in sentences:
            count = self._word_count(sentence)
            if selected and (total_words + count) > max_words:
                break
            selected.append(sentence)
            total_words += count
            if total_words >= max_words:
                break
        return " ".join(selected).strip()
