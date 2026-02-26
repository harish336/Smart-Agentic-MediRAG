"""
Text Accumulator & Chunker

Responsibilities:
- Accumulate text based on heading / subheading / body flow
- Maintain page numbers
- Apply max chunk size
- Apply pre & post overlap
- Sort by page number
- Standalone runnable for verification

This file DOES NOT depend on vector DB or Neo4j.
"""

import sys
import json
from pprint import pprint
from typing import List, Dict

# ---------------- CONFIG ----------------
MAX_CHUNK_SIZE = 1500
PRE_OVERLAP = 300
POST_OVERLAP = 300


class TextAccumulator:

    # =====================================================
    # INITIALIZATION
    # =====================================================

    def __init__(self):
        print("[TEXT ACCUMULATOR] Initialized")

        self.current_heading = None
        self.current_subheading = None
        self.buffer = ""
        self.start_page = None
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
        self.start_page = None
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

        if not text:
            return

        # New heading resets everything
        if unit_type == "heading":

            self.flush()
            self.current_heading = text
            self.current_subheading = None
            self.start_page = page
            self.buffer = text + "\n"

        # New subheading resets body accumulation
        elif unit_type == "subheading":

            self.flush()
            self.current_subheading = text
            self.start_page = page
            self.buffer = self._compose_prefix() + text + "\n"

        # Body text accumulates
        else:

            if self.start_page is None:
                self.start_page = page

            self.buffer += text + "\n"

        # Check size
        if len(self.buffer) >= MAX_CHUNK_SIZE:
            self.flush()

    # =====================================================
    # STEP 2: Flush buffer into chunk
    # =====================================================

    def flush(self):

        if not self.buffer.strip():
            return

        chunk = {
            "chapter": self.current_heading,
            "subheading": self.current_subheading,
            "page_physical": self.start_page,
            "page_label": None,  # Can be injected later if offset applied
            "text": self.buffer.strip()
        }

        self.chunks.append(chunk)

        self.buffer = ""

    # =====================================================
    # STEP 3: Apply overlap
    # =====================================================

    def apply_overlap(self):

        overlapped = []

        for i, chunk in enumerate(self.chunks):

            text = chunk["text"]

            if i > 0:
                prev = self.chunks[i - 1]["text"]
                text = prev[-PRE_OVERLAP:] + "\n" + text

            if i < len(self.chunks) - 1:
                nxt = self.chunks[i + 1]["text"]
                text = text + "\n" + nxt[:POST_OVERLAP]

            new_chunk = dict(chunk)
            new_chunk["text"] = text

            overlapped.append(new_chunk)

        self.chunks = overlapped

    # =====================================================
    # STEP 4: Finalize
    # =====================================================

    def finalize(self):

        self.flush()

        # Sort by physical page
        self.chunks.sort(key=lambda x: x["page_physical"] or 0)

        self.apply_overlap()

        return self.chunks

    # =====================================================
    # INTERNAL
    # =====================================================

    def _compose_prefix(self):

        prefix = ""

        if self.current_heading:
            prefix += self.current_heading + "\n"

        return prefix


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python accumulator.py <input_json>")
        sys.exit(1)

    input_file = sys.argv[1]

    print("=" * 100)
    print("TEXT ACCUMULATOR (STANDALONE)")
    print("=" * 100)

    try:
        units = json.load(open(input_file, "r", encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to load input JSON: {e}")
        sys.exit(1)

    accumulator = TextAccumulator()
    chunks = accumulator.run(units)

    pprint(chunks, width=130)

    json.dump(
        chunks,
        open("chunks_accumulated.json", "w", encoding="utf-8"),
        indent=2
    )

    print("\n[OUTPUT] Saved to chunks_accumulated.json")
    print("=" * 100)


if __name__ == "__main__":
    main()