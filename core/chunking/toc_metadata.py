"""
TOC Metadata Enricher

Purpose:
- Enrich fallback chunks with TOC chapter/subheading metadata after accumulation
- Preserve original metadata while filling gaps from TOC timeline
- Optionally prefix chunk text with compact TOC context
"""

import re
from typing import Dict, List, Optional


class TOCMetadataEnricher:

    def __init__(self, toc_data: Optional[Dict] = None):
        self.toc_data = toc_data or {}
        self.offset = self._parse_int(self.toc_data.get("offset"))
        self.toc_start_page = self._parse_int(self.toc_data.get("toc_page"))
        self.anchors = self._build_anchors(self.toc_data.get("toc_entries") or [])

    def apply(self, chunks: List[Dict]) -> List[Dict]:
        if not chunks or not self.anchors:
            return chunks or []

        toc_index = 0
        current_chapter = None
        current_subheading = None
        enriched = []

        for chunk in chunks:
            item = dict(chunk)
            page_physical = self._parse_int(item.get("page_physical"))

            if self.toc_start_page and page_physical and page_physical < self.toc_start_page:
                enriched.append(item)
                continue

            page_label = self._resolve_page_label(item, page_physical)
            if page_label is None:
                enriched.append(item)
                continue

            while toc_index < len(self.anchors) and self.anchors[toc_index]["page_label"] <= page_label:
                entry = self.anchors[toc_index]
                if entry["level"] == "chapter":
                    current_chapter = entry["title"]
                    current_subheading = None
                else:
                    current_subheading = entry["title"]
                toc_index += 1

            page_entries = [a for a in self.anchors if a["page_label"] == page_label]
            page_chapters = [a["title"] for a in page_entries if a["level"] == "chapter"]
            page_subs = [a["title"] for a in page_entries if a["level"] != "chapter"]

            toc_chapter = self._join_unique(page_chapters) if page_chapters else current_chapter
            toc_subheading = self._join_unique(page_subs) if page_subs else current_subheading

            merged_chapter = self._merge_label(item.get("chapter"), toc_chapter)
            merged_subheading = self._merge_label(item.get("subheading"), toc_subheading)

            if merged_chapter:
                item["chapter"] = merged_chapter
            if merged_subheading:
                item["subheading"] = merged_subheading

            prefix = self._toc_prefix(toc_chapter, toc_subheading)
            text = (item.get("text") or "").strip()
            if prefix and text and not text.startswith(prefix):
                item["text"] = f"{prefix}\n{text}"

            enriched.append(item)

        return enriched

    def _build_anchors(self, entries: List[Dict]) -> List[Dict]:
        anchors = []

        for entry in entries:
            title = (entry.get("title") or "").strip()
            if len(title) < 2:
                continue

            page_label = self._normalize_label(entry.get("page_label"))
            if page_label is None:
                continue

            level = (entry.get("level") or "unknown").strip().lower()
            if level == "chapter":
                normalized_level = "chapter"
            elif level in {"section", "subsection"}:
                normalized_level = "subheading"
            elif re.match(r"^chapter\b", title, flags=re.IGNORECASE):
                normalized_level = "chapter"
            else:
                normalized_level = "subheading"

            anchors.append(
                {
                    "page_label": page_label,
                    "title": title,
                    "level": normalized_level,
                }
            )

        anchors.sort(key=lambda x: x["page_label"])
        return anchors

    def _resolve_page_label(self, chunk: Dict, page_physical: Optional[int]) -> Optional[int]:
        label = self._normalize_label(chunk.get("page_label"))
        if label is not None:
            return label

        if page_physical is None or self.offset is None:
            return None

        logical = page_physical - self.offset
        return logical if logical > 0 else None

    def _normalize_label(self, value) -> Optional[int]:
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        if text.isdigit():
            return int(text)

        return self._roman_to_int(text)

    def _roman_to_int(self, roman: str) -> Optional[int]:
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
        for ch in reversed(roman.upper()):
            if ch not in roman_map:
                return None
            value = roman_map[ch]
            if value < prev:
                total -= value
            else:
                total += value
                prev = value
        return total if total > 0 else None

    def _parse_int(self, value) -> Optional[int]:
        try:
            if value is None:
                return None
            return int(value)
        except Exception:
            return None

    def _join_unique(self, values: List[str]) -> Optional[str]:
        seen = set()
        unique = []
        for value in values:
            text = (value or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(text)
        return ", ".join(unique) if unique else None

    def _merge_label(self, existing, toc_value) -> Optional[str]:
        existing_text = (existing or "").strip()
        toc_text = (toc_value or "").strip()

        if existing_text and toc_text:
            if existing_text.lower() == toc_text.lower():
                return existing_text
            return f"{existing_text}, {toc_text}"
        if existing_text:
            return existing_text
        if toc_text:
            return toc_text
        return None

    def _toc_prefix(self, chapter, subheading) -> Optional[str]:
        chapter_text = (chapter or "").strip()
        sub_text = (subheading or "").strip()

        if chapter_text and sub_text:
            return f"[TOC] Chapter: {chapter_text} | Subheading: {sub_text}"
        if chapter_text:
            return f"[TOC] Chapter: {chapter_text}"
        if sub_text:
            return f"[TOC] Subheading: {sub_text}"
        return None
