"""
Text Cleaner (Standalone & Verbose)

Purpose:
- Clean raw text extracted from PDFs, OCR, TOC, chunks
- Normalize whitespace and punctuation
- Remove common noise patterns
- Prepare text for chunking and embeddings

Used in:
- TOC extraction
- OCR cleanup
- Chunk preparation
- Vector DB ingestion

This file CAN be run independently.
"""

import sys
import json
import re
from pprint import pprint
from typing import Union, List


class TextCleaner:
    def __init__(self, aggressive: bool = False):
        """
        aggressive:
          False → safe cleaning (recommended)
          True  → aggressive cleanup (OCR-heavy docs)
        """
        self.aggressive = aggressive

    # -------------------------------------------------
    # STEP 1: Normalize whitespace
    # -------------------------------------------------
    def normalize_whitespace(self, text: str) -> str:
        print("[CLEAN] Normalizing whitespace")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # -------------------------------------------------
    # STEP 2: Remove dotted leaders (TOC)
    # -------------------------------------------------
    def remove_dotted_leaders(self, text: str) -> str:
        print("[CLEAN] Removing dotted leaders")
        text = re.sub(r"\.{2,}", " ", text)
        return text

    # -------------------------------------------------
    # STEP 3: Remove repeated hyphens/underscores
    # -------------------------------------------------
    def remove_repeated_symbols(self, text: str) -> str:
        print("[CLEAN] Removing repeated symbols")
        text = re.sub(r"[-_]{2,}", " ", text)
        return text

    # -------------------------------------------------
    # STEP 4: Fix broken line words (hyphenated OCR)
    # -------------------------------------------------
    def fix_hyphenated_words(self, text: str) -> str:
        print("[CLEAN] Fixing hyphenated line breaks")
        text = re.sub(r"(\w+)-\s+(\w+)", r"\1\2", text)
        return text

    # -------------------------------------------------
    # STEP 5: Remove non-printable characters
    # -------------------------------------------------
    def remove_non_printable(self, text: str) -> str:
        print("[CLEAN] Removing non-printable characters")
        text = "".join(c for c in text if c.isprintable())
        return text

    # -------------------------------------------------
    # STEP 6: Aggressive OCR cleanup (optional)
    # -------------------------------------------------
    def aggressive_cleanup(self, text: str) -> str:
        print("[CLEAN] Applying aggressive OCR cleanup")

        # Remove isolated symbols
        text = re.sub(r"\b[^a-zA-Z0-9\s]{1,2}\b", " ", text)

        # Remove excessive punctuation
        text = re.sub(r"[!?]{2,}", ".", text)

        # Remove random single letters
        text = re.sub(r"\b[a-zA-Z]\b", " ", text)

        return text

    # -------------------------------------------------
    # RUN CLEANING PIPELINE
    # -------------------------------------------------
    def clean(self, text: str) -> str:
        print("\n[TEXT CLEANING STARTED]")
        print(f"[INPUT LENGTH] {len(text)}")

        text = self.remove_non_printable(text)
        text = self.fix_hyphenated_words(text)
        text = self.remove_dotted_leaders(text)
        text = self.remove_repeated_symbols(text)
        text = self.normalize_whitespace(text)

        if self.aggressive:
            text = self.aggressive_cleanup(text)
            text = self.normalize_whitespace(text)

        print(f"[OUTPUT LENGTH] {len(text)}")
        print("[TEXT CLEANING COMPLETED]\n")

        return text

    # -------------------------------------------------
    # Clean list of texts
    # -------------------------------------------------
    def clean_list(self, texts: List[str]) -> List[str]:
        print(f"[BATCH CLEAN] Cleaning list of {len(texts)} texts")
        return [self.clean(t) for t in texts if isinstance(t, str)]


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python text_cleaner.py <text_or_json> [--aggressive]")
        print("\nExamples:")
        print("  python text_cleaner.py \"Some raw text...\"")
        print("  python text_cleaner.py texts.json --aggressive")
        sys.exit(1)

    input_value = sys.argv[1]
    aggressive = "--aggressive" in sys.argv

    print("=" * 100)
    print("TEXT CLEANER STARTED")
    print(f"Aggressive mode: {aggressive}")
    print("=" * 100)

    cleaner = TextCleaner(aggressive=aggressive)

    # JSON input
    if input_value.lower().endswith(".json"):
        try:
            with open(input_value, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load JSON: {e}")
            sys.exit(1)

        if isinstance(data, list):
            cleaned = cleaner.clean_list(data)
        else:
            print("[ERROR] JSON must contain a list of strings")
            sys.exit(1)

        print("\n[CLEANED OUTPUT]")
        pprint(cleaned)

    # Direct text input
    else:
        cleaned = cleaner.clean(input_value)
        print("\n[CLEANED OUTPUT]")
        print(cleaned)

    print("=" * 100)
    print("TEXT CLEANER COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
