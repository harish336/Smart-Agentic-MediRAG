"""
Overlapper Module (Standalone)

Purpose:
- Apply pre-overlap and post-overlap to text chunks
- Preserve chunk metadata
- Verbose printing for debugging & verification

Expected input:
A JSON file containing a list of chunks like:

[
  {
    "heading": "Chapter 1 Introduction",
    "subheading": "1.1 Background",
    "page": 2,
    "text": "...."
  }
]

This file CAN be run independently.
"""

import sys
import json
from pprint import pprint
from typing import List, Dict

# ---------------- CONFIG ----------------
PRE_OVERLAP = 300
POST_OVERLAP = 300


class ChunkOverlapper:

    def __init__(self):
        print("[OVERLAP] Initialized")

    def apply(self, chunks: list) -> list:

        if not chunks:
            return []

        overlapped = []

        for i, chunk in enumerate(chunks):

            new_chunk = chunk.copy()

            # Pre overlap
            if i > 0:
                prev_text = chunks[i - 1]["text"]
                new_chunk["text"] = prev_text[-300:] + " " + new_chunk["text"]

            # Post overlap
            if i < len(chunks) - 1:
                next_text = chunks[i + 1]["text"]
                new_chunk["text"] += " " + next_text[:300]

            overlapped.append(new_chunk)

        return overlapped

    # -------------------------------------------------
    # STEP 1: Apply overlap
    # -------------------------------------------------
    def apply_overlap(self):
        print("\n[STEP 1] Applying pre and post overlap...")
        print(f"[CONFIG] PRE_OVERLAP  = {PRE_OVERLAP}")
        print(f"[CONFIG] POST_OVERLAP = {POST_OVERLAP}")

        for idx, chunk in enumerate(self.chunks):
            print("\n" + "-" * 80)
            print(f"[PROCESSING CHUNK] Index: {idx}")

            base_text = chunk.get("text", "")
            new_text = base_text

            print(f"[ORIGINAL SIZE] {len(base_text)} characters")

            # -------- PRE-OVERLAP --------
            if idx > 0:
                prev_text = self.chunks[idx - 1].get("text", "")
                pre = prev_text[-PRE_OVERLAP:]
                new_text = pre + "\n" + new_text
                print(f"[PRE-OVERLAP] Added {len(pre)} characters")

            # -------- POST-OVERLAP --------
            if idx < len(self.chunks) - 1:
                next_text = self.chunks[idx + 1].get("text", "")
                post = next_text[:POST_OVERLAP]
                new_text = new_text + "\n" + post
                print(f"[POST-OVERLAP] Added {len(post)} characters")

            print(f"[FINAL SIZE] {len(new_text)} characters")

            overlapped_chunk = dict(chunk)
            overlapped_chunk["text"] = new_text
            overlapped_chunk["overlap"] = {
                "pre": PRE_OVERLAP if idx > 0 else 0,
                "post": POST_OVERLAP if idx < len(self.chunks) - 1 else 0
            }

            self.overlapped_chunks.append(overlapped_chunk)

        print("\n[STEP 2] Overlap application completed")
        print(f"[INFO] Total chunks processed: {len(self.overlapped_chunks)}")

        return self.overlapped_chunks


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python overlapper.py <chunks_json>")
        print("\nExample:")
        print("  python overlapper.py chunks_output.json")
        sys.exit(1)

    input_file = sys.argv[1]

    print("=" * 100)
    print("CHUNK OVERLAPPER STARTED")
    print(f"Input file: {input_file}")
    print("=" * 100)

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load chunks JSON: {e}")
        sys.exit(1)

    print(f"[INFO] Chunks loaded: {len(chunks)}")

    overlapper = ChunkOverlapper(chunks)
    overlapped_chunks = overlapper.apply_overlap()

    print("\n[FINAL OVERLAPPED CHUNKS]")
    pprint(overlapped_chunks, width=130)

    output_file = "chunks_overlapped.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(overlapped_chunks, f, indent=2)

    print("\n[OUTPUT]")
    print(f"Overlapped chunks saved to: {output_file}")
    print("=" * 100)
    print("CHUNK OVERLAPPER COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
