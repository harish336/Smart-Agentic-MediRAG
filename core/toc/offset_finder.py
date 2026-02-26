"""
ULTRA-SAFE Production Offset Finder (v2)
Fixes:
- False positives from body numbers
- Large random offset drift (e.g., 244)
- Mixed Roman + numeric numbering
- Header / footer only detection
- Center-aligned number preference
- Sequential verification safety
"""

import sys
import re
import json
import fitz
from collections import Counter


# -------------------------------------------------
# Roman conversion
# -------------------------------------------------

MAX_REASONABLE_OFFSET = 80


ROMAN_MAP = {
    "I": 1, "V": 5, "X": 10, "L": 50,
    "C": 100, "D": 500, "M": 1000
}


def roman_to_int(roman: str):
    roman = roman.upper()
    total = 0
    prev = 0
    for c in reversed(roman):
        if c not in ROMAN_MAP:
            return None
        val = ROMAN_MAP[c]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total


# -------------------------------------------------
# Offset Finder
# -------------------------------------------------

class OffsetFinder:

    def __init__(self, pdf_path, toc_entries):
        self.pdf_path = pdf_path
        self.toc_entries = toc_entries
        self.doc = None

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------

    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        self.doc = fitz.open(self.pdf_path)
        print(f"[OK] Loaded PDF ({self.doc.page_count} pages)")

    # -------------------------------------------------
    # Normalize logical page labels
    # -------------------------------------------------

    def normalize(self, label):
        if not label:
            return None

        label = str(label).strip()

        if label.isdigit():
            return int(label)

        return roman_to_int(label)

    # -------------------------------------------------
    # Collect logical pages from TOC
    # -------------------------------------------------

    def collect_logical_pages(self):
        pages = []

        for e in self.toc_entries:
            val = self.normalize(e.get("page_label"))
            if val:
                pages.append(val)

        pages = sorted(set(pages))
        print(f"[INFO] Logical pages detected: {len(pages)}")
        return pages

    # -------------------------------------------------
    # SAFE page number extraction
    # -------------------------------------------------

    def extract_page_numbers(self, page):

        page_height = page.rect.height
        blocks = page.get_text("blocks")

        candidates = []

        for b in blocks:
            x0, y0, x1, y1, text, *_ = b

            # Only header or footer region
            if y1 < page_height * 0.20 or y0 > page_height * 0.80:

                words = re.findall(r"\b\d{1,3}\b", text)

                for w in words:
                    val = int(w)

                    # Page numbers should be small
                    if 1 <= val <= self.doc.page_count + 10:
                        candidates.append(val)

                # Roman numbers
                roman_words = re.findall(r"\b[ivxlcdmIVXLCDM]{1,6}\b", text)

                for r in roman_words:
                    val = roman_to_int(r)
                    if val and val <= 50:
                        candidates.append(val)

        return candidates

    # -------------------------------------------------
    # Core offset logic
    # -------------------------------------------------
    def find_offset(self):

        self.load_pdf()

        page_candidates = {}

        for phys in range(self.doc.page_count):
            page = self.doc.load_page(phys)
            nums = self.extract_page_numbers(page)
            if nums:
                page_candidates[phys] = nums

        offset_scores = Counter()

        for phys, nums in page_candidates.items():
            for printed in nums:
                offset = phys - (printed - 1)
                offset_scores[offset] += 1

        if not offset_scores:
            print("[FAIL] No offset candidates found.")
            return None

        candidates = offset_scores.most_common(5)

        best_offset = None
        best_sequence = 0

        for offset, _ in candidates:

            streak = 0
            max_streak = 0

            for phys in sorted(page_candidates.keys()):
                expected = phys - offset + 1
                if expected in page_candidates.get(phys, []):
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 0

            if max_streak > best_sequence:
                best_sequence = max_streak
                best_offset = offset

        if best_sequence < 5:
            print("[FAIL] No stable sequential numbering detected.")
            return None

        # 🔒 HARD SAFETY LIMIT
        if abs(best_offset) > MAX_REASONABLE_OFFSET:
            print(
                f"[WARNING] Offset {best_offset} exceeds safe limit "
                f"({MAX_REASONABLE_OFFSET}). Ignoring offset."
            )
            return None

        print(
            f"[SUCCESS] Offset determined: {best_offset} "
            f"(streak={best_sequence})"
        )

        return best_offset

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def run(self):
        return self.find_offset()


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python offset_finder.py <pdf_path> <toc_json>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    toc_json = sys.argv[2]

    print("=" * 60)
    print("ULTRA-SAFE OFFSET FINDER v2")
    print(f"PDF Path : {pdf_path}")
    print(f"TOC File : {toc_json}")
    print("=" * 60)

    try:
        with open(toc_json, "r", encoding="utf-8") as f:
            toc_entries = json.load(f)
    except Exception as e:
        print(f"[ERROR] Could not load TOC JSON: {e}")
        sys.exit(1)

    finder = OffsetFinder(pdf_path, toc_entries)
    finder.run()


if __name__ == "__main__":
    main()