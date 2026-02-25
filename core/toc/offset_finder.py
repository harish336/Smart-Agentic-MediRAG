"""
ULTRA-SAFE Production Offset Finder
Handles:
- Roman + numeric numbering
- Header or footer numbering
- Mixed front-matter + body
- Requires sequential confirmation
- Fails safely
"""

import sys
import re
import json
import fitz
from collections import Counter


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
    # Extract page numbers from full page
    # -------------------------------------------------
    def extract_page_numbers(self, page):
        text = page.get_text()
        numbers = []

        # Numeric
        for n in re.findall(r"\b\d{1,4}\b", text):
            val = int(n)
            if 1 <= val <= 3000:
                numbers.append(val)

        # Roman
        for r in re.findall(r"\b[ivxlcdmIVXLCDM]{1,7}\b", text):
            val = roman_to_int(r)
            if val:
                numbers.append(val)

        return numbers

    # -------------------------------------------------
    # Core offset logic
    # -------------------------------------------------
    def find_offset(self):

        self.load_pdf()
        logical_pages = self.collect_logical_pages()

        if len(logical_pages) < 3:
            print("[FAIL] Not enough logical anchors.")
            return None

        offset_votes = []

        print("[STEP] Scanning for anchor matches...")

        scan_limit = min(self.doc.page_count, 300)

        for phys in range(scan_limit):
            page = self.doc.load_page(phys)
            numbers = self.extract_page_numbers(page)

            for printed in numbers:
                if printed in logical_pages:
                    offset = phys - (printed - 1)
                    offset_votes.append(offset)

        if not offset_votes:
            print("[FAIL] No anchors found.")
            return None

        counter = Counter(offset_votes)
        candidate, support = counter.most_common(1)[0]

        print(f"[INFO] Top offset candidate: {candidate} (support={support})")

        # SAFETY: require minimum stability
        if support < 3:
            print("[FAIL] Offset not stable enough.")
            return None

        # Sequential confirmation
        confirmed = 0
        for logical in logical_pages[:10]:
            phys = logical - 1 + candidate
            if 0 <= phys < self.doc.page_count:
                page = self.doc.load_page(phys)
                numbers = self.extract_page_numbers(page)
                if logical in numbers:
                    confirmed += 1

        print(f"[INFO] Sequential confirmation count: {confirmed}")

        if confirmed < 3:
            print("[FAIL] Offset failed sequential verification.")
            return None

        print(f"[SUCCESS] Offset determined: {candidate}")
        return candidate

    # -------------------------------------------------
    # PUBLIC API (Required by Orchestrator)
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
    print("OFFSET FINDER — STANDALONE TEST")
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