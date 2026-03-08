"""
Text Accumulator & Chunker

Responsibilities:
- Accumulate text based on heading / subheading / body flow
- Maintain physical page range
- Map logical page labels from TOC offset when available
- Apply max chunk size from config
- Sort by physical page
"""

import re
from typing import Dict, List, Optional

from config.system_loader import get_system_config


class TextAccumulator:

    # =====================================================
    # INITIALIZATION
    # =====================================================

    def __init__(self, toc_data: Optional[Dict] = None):
        print("[TEXT ACCUMULATOR] Initialized")

        self.config = get_system_config()
        chunk_size_cfg = self.config.get("chunking", {}).get("size", {})
        self.max_chunk_size = int(chunk_size_cfg.get("max_chars", 1500))

        self.toc_data = toc_data or {}
        self.offset = self._parse_offset(self.toc_data.get("offset"))
        self.toc_anchors = self._build_toc_anchors(self.toc_data.get("toc_entries") or [])

        self.current_heading = None
        self.current_subheading = None
        self.buffer = ""
        self.buffer_page_type = None
        self.start_page = None
        self.end_page = None
        self.current_page_type = None
        self.chunks = []

    # =====================================================
    # PIPELINE ENTRY (Used by ChunkOrchestrator)
    # =====================================================

    def run(self, styled_blocks: List[Dict]) -> List[Dict]:

        print("\n" + "=" * 70)
        print("TEXT ACCUMULATION STARTED")
        print("=" * 70)

        # Reset state (important for reuse)
        self.current_heading = None
        self.current_subheading = None
        self.buffer = ""
        self.buffer_page_type = None
        self.start_page = None
        self.end_page = None
        self.current_page_type = None
        self.chunks = []

        for unit in styled_blocks:
            self.add_unit(unit)

        result = self.finalize()

        print("=" * 70)
        print("TEXT ACCUMULATION COMPLETED")
        print("=" * 70 + "\n")

        return result

    # =====================================================
    # STEP 1: Add text unit
    # =====================================================

    def add_unit(self, unit: Dict):

        unit_type = unit.get("type")
        text = unit.get("text", "").strip()
        page = unit.get("page")
        page_type = unit.get("page_type") or "content"

        if not text:
            return

        # Do not mix structurally different page regions in one chunk.
        if self.current_page_type and page_type != self.current_page_type:
            self.flush()

        # New heading resets everything
        if unit_type == "heading":

            self.flush()
            self.current_heading = text
            self.current_subheading = None
            self.start_page = None
            self.end_page = None
            self.current_page_type = page_type
            self.buffer = ""
            self.buffer_page_type = page_type

        # New subheading resets body accumulation
        elif unit_type == "subheading":

            self.flush()
            self.current_subheading = text
            self.start_page = None
            self.end_page = None
            self.current_page_type = page_type
            self.buffer = ""
            self.buffer_page_type = page_type

        # Body text accumulates
        else:

            if self.start_page is None:
                self.start_page = page

            self.end_page = page
            self.current_page_type = page_type
            if self.buffer_page_type is None:
                self.buffer_page_type = page_type

            if not self.buffer:
                prefix = self._compose_prefix()
                if prefix:
                    self.buffer += prefix + "\n"

            self.buffer += text + "\n"

        # Ensure end_page is set for heading/subheading-only chunks
        if self.end_page is None and page is not None:
            self.end_page = page

        # Check size
        if len(self.buffer) >= self.max_chunk_size:
            self.flush()

    # =====================================================
    # STEP 2: Flush buffer into chunk
    # =====================================================

    def flush(self):

        if not self.buffer.strip():
            return

        text = self.buffer.strip()
        page_physical = self.start_page
        page_label = self._physical_to_label(page_physical)
        toc_chapter, toc_subheading = self._toc_context_for_label(page_label)
        chapter = self.current_heading or toc_chapter
        subheading = self.current_subheading or toc_subheading
        page_type = self.buffer_page_type or self.current_page_type or "content"

        parts = self._split_text_for_chunks(text)
        for part in parts:
            chunk = {
                "chapter": chapter,
                "subheading": subheading,
                "page_type": page_type,
                "page_physical": page_physical,
                "page_physical_end": self.end_page,
                "page_label": page_label,
                "text": part,
            }
            self.chunks.append(chunk)

        self.buffer = ""
        self.buffer_page_type = None
        self.start_page = None
        self.end_page = None
        self.current_page_type = None

    # =====================================================
    # STEP 3: Finalize
    # =====================================================

    def finalize(self):

        self.flush()

        # Sort by physical page
        self.chunks.sort(key=lambda x: x["page_physical"] or 0)

        return self.chunks

    # =====================================================
    # INTERNAL
    # =====================================================

    def _compose_prefix(self):

        parts = []

        if self.current_heading:
            parts.append(self.current_heading)

        if self.current_subheading:
            parts.append(self.current_subheading)

        return "\n".join(parts).strip()

    def _split_text_for_chunks(self, text: str) -> List[str]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        if len(cleaned) <= self.max_chunk_size:
            return [cleaned]

        parts = []
        remaining = cleaned

        while len(remaining) > self.max_chunk_size:
            cut = self._find_split_index(remaining, self.max_chunk_size)
            piece = remaining[:cut].strip()
            if piece:
                parts.append(piece)
            remaining = remaining[cut:].strip()

        if remaining:
            parts.append(remaining)

        return parts

    def _find_split_index(self, text: str, preferred: int) -> int:
        if len(text) <= preferred:
            return len(text)

        floor = max(int(preferred * 0.65), 120)
        window = text[:preferred + 1]

        # 1. Prefer double newlines (paragraphs)
        para_cut = window.rfind("\n\n")
        if para_cut >= floor:
            return para_cut + 2

        # 2. Prefer single newlines (bullets, structure)
        newline_cut = window.rfind("\n")
        if newline_cut >= floor:
            return newline_cut + 1

        # 3. Prefer end of sentence
        sentence_cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if sentence_cut >= floor:
            return sentence_cut + 1

        # 4. Final fallback to word boundary
        space_cut = window.rfind(" ")
        if space_cut >= floor:
            return space_cut + 1

        return preferred

    def _parse_offset(self, offset_value):
        try:
            if offset_value is None:
                return None
            return int(offset_value)
        except Exception:
            return None

    def _normalize_label(self, raw_label):
        if raw_label is None:
            return None

        label = str(raw_label).strip()
        if not label:
            return None

        if label.isdigit():
            return int(label)

        roman_val = self._roman_to_int(label)
        if roman_val:
            return roman_val

        return None

    def _roman_to_int(self, roman):
        roman_map = {
            "I": 1,
            "V": 5,
            "X": 10,
            "L": 50,
            "C": 100,
            "D": 500,
            "M": 1000,
        }
        total = 0
        prev = 0
        for ch in reversed(str(roman).upper()):
            if ch not in roman_map:
                return None
            value = roman_map[ch]
            if value < prev:
                total -= value
            else:
                total += value
                prev = value
        return total if total > 0 else None

    def _physical_to_label(self, page_physical):
        if page_physical is None:
            return None

        if self.offset is None:
            return None

        logical = int(page_physical) - int(self.offset)
        return logical if logical > 0 else None

    def _build_toc_anchors(self, toc_entries):
        anchors = []

        for entry in toc_entries:
            title = (entry.get("title") or "").strip()
            if len(title) < 2:
                continue

            label_int = self._normalize_label(entry.get("page_label"))
            if label_int is None:
                continue

            level = (entry.get("level") or "unknown").lower()

            anchors.append(
                {
                    "page_label": label_int,
                    "title": title,
                    "level": level,
                }
            )

        anchors.sort(key=lambda x: x["page_label"])
        return anchors

    def _toc_context_for_label(self, page_label):
        if page_label is None or not self.toc_anchors:
            return None, None

        chapter = None
        subheading = None

        for anchor in self.toc_anchors:
            if anchor["page_label"] > page_label:
                break

            level = anchor["level"]
            title = anchor["title"]

            if level == "chapter":
                chapter = title
                subheading = None
            elif level in {"section", "subsection"}:
                subheading = title
            elif re.match(r"^chapter\b", title.lower()):
                chapter = title
                subheading = None
            else:
                subheading = title

        return chapter, subheading
