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
    def __init__(self):
        self.current_heading = None
        self.current_subheading = None
        self.buffer = ""
        self.start_page = None
        self.chunks = []

    # -------------------------------------------------
    # STEP 1: Add text unit
    # -------------------------------------------------
    def add_unit(self, unit: Dict):
        """
        unit format:
        {
          "type": "heading|subheading|body",
          "text": "...",
          "page": 12
        }
        """
        unit_type = unit.get("type")
        text = unit.get("text", "").strip()
        page = unit.get("page")

        if not text:
            return

        print("\n[ADD UNIT]")
        print(f"Type : {unit_type}")
        print(f"Page : {page}")
        print(f"Text : {text[:80]}{'...' if len(text) > 80 else ''}")

        # New heading resets everything
        if unit_type == "heading":
            self.flush()
            self.current_heading = text
            self.current_subheading = None
            self.start_page = page
            self.buffer = text + "\n"
            print("[STATE] New heading set")

        # New subheading resets body accumulation
        elif unit_type == "subheading":
            self.flush()
            self.current_subheading = text
            self.start_page = page
            self.buffer = self._compose_prefix() + text + "\n"
            print("[STATE] New subheading set")

        # Body text accumulates
        else:
            if self.start_page is None:
                self.start_page = page
            self.buffer += text + "\n"

        # Check size
        if len(self.buffer) >= MAX_CHUNK_SIZE:
            print("[INFO] Max chunk size reached → flushing")
            self.flush()

    # -------------------------------------------------
    # STEP 2: Flush buffer into chunk
    # -------------------------------------------------
    def flush(self):
        if not self.buffer.strip():
            return

        chunk = {
            "heading": self.current_heading,
            "subheading": self.current_subheading,
            "page": self.start_page,
            "text": self.buffer.strip()
        }

        self.chunks.append(chunk)

        print("\n[FLUSH CHUNK]")
        print(f"Heading    : {self.current_heading}")
        print(f"Subheading : {self.current_subheading}")
        print(f"Start Page : {self.start_page}")
        print(f"Length     : {len(self.buffer)}")

        self.buffer = ""

    # -------------------------------------------------
    # STEP 3: Apply overlap
    # -------------------------------------------------
    def apply_overlap(self):
        print("\n[STEP] Applying overlap...")
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

            print(f"[OVERLAP] Chunk {i} size → {len(text)}")

        self.chunks = overlapped

    # -------------------------------------------------
    # STEP 4: Finalize
    # -------------------------------------------------
    def finalize(self):
        print("\n[FINALIZE] Flushing remaining buffer")
        self.flush()

        print("[FINALIZE] Sorting chunks by page")
        self.chunks.sort(key=lambda x: x["page"] or 0)

        self.apply_overlap()

        print(f"[DONE] Total chunks created: {len(self.chunks)}")
        return self.chunks

    # -------------------------------------------------
    def _compose_prefix(self):
        prefix = ""
        if self.current_heading:
            prefix += self.current_heading + "\n"
        return prefix


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    """
    Example input JSON:
    [
      {"type": "heading", "text": "Chapter 1 Introduction", "page": 1},
      {"type": "subheading", "text": "1.1 Background", "page": 2},
      {"type": "body", "text": "This chapter discusses...", "page": 2}
    ]
    """

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python accumulator.py <input_json>")
        sys.exit(1)

    input_file = sys.argv[1]

    print("=" * 100)
    print("TEXT ACCUMULATOR STARTED")
    print(f"Input file: {input_file}")
    print("=" * 100)

    try:
        units = json.load(open(input_file, "r", encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to load input JSON: {e}")
        sys.exit(1)

    accumulator = TextAccumulator()

    for unit in units:
        accumulator.add_unit(unit)

    chunks = accumulator.finalize()

    print("\n[FINAL CHUNKS]")
    pprint(chunks, width=130)

    json.dump(chunks, open("chunks_accumulated.json", "w", encoding="utf-8"), indent=2)

    print("\n[OUTPUT] Saved to chunks_accumulated.json")
    print("=" * 100)
    print("TEXT ACCUMULATOR COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
