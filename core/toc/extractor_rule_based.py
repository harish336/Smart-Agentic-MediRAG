"""
Universal Rule-Based TOC Extractor
Production-grade
Handles multiple TOC styles robustly
"""

import sys
import re
import json
import fitz
from collections import defaultdict
from pprint import pprint


ROMAN_RE = r"[ivxlcdmIVXLCDM]+"
DIGIT_RE = r"\d+"
PAGE_RE = rf"({ROMAN_RE}|{DIGIT_RE})$"


class RuleBasedTOCExtractor:
    def __init__(self, pdf_path: str, toc_start_page: int, max_pages: int = 15):
        self.pdf_path = pdf_path
        self.toc_start_page = toc_start_page
        self.max_pages = max_pages
        self.doc = None
        self.entries = []

    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        self.doc = fitz.open(self.pdf_path)
        print("[OK] PDF loaded successfully")
        print(f"[INFO] Total pages: {self.doc.page_count}")

    # -------------------------------------------------
    def extract_rows(self, page_index, y_tol=4):
        page = self.doc.load_page(page_index)
        blocks = page.get_text("blocks")

        rows = defaultdict(list)

        for block in blocks:
            x0, y0, x1, y1, text = block[:5]

            for line in text.split("\n"):
                clean = line.strip()
                if not clean:
                    continue

                key = round(y0 / y_tol) * y_tol
                rows[key].append((x0, clean))

        merged = []
        for y in sorted(rows):
            parts = [t for _, t in sorted(rows[y], key=lambda x: x[0])]
            merged.append(" ".join(parts).strip())

        return merged

    # -------------------------------------------------
    def is_toc_page(self, rows):
        """
        Detect TOC by:
        - Count of lines ending with page numbers
        - Presence of chapter/section numbering
        """

        page_end_hits = 0
        numbering_hits = 0

        for line in rows:
            if re.search(PAGE_RE, line):
                page_end_hits += 1

            if re.match(r"^\d+(\.\d+)*", line):
                numbering_hits += 1

            if line.lower().startswith("chapter"):
                numbering_hits += 1

        score = page_end_hits + numbering_hits
        print(f"[DEBUG] TOC score: {score}")

        return score >= 4  # robust threshold

    # -------------------------------------------------
    def detect_level(self, title):
        t = title.strip().lower()

        if t.startswith("chapter"):
            return "chapter"

        if re.match(r"^\d+\.\d+", t):
            return "section"

        if re.match(r"^\d+\.", t):
            return "subsection"

        return "unknown"

    # -------------------------------------------------
    def extract_entries(self, rows):

        for line in rows:

            line = line.strip()

            # remove dotted leaders
            line = re.sub(r"\.{2,}", " ", line)

            match = re.search(PAGE_RE, line)
            if not match:
                continue

            page_label = match.group(1)

            title = line[: match.start()].strip()

            # avoid capturing short garbage
            if len(title) < 3:
                continue

            entry = {
                "title": title,
                "page_label": page_label,
                "level": self.detect_level(title)
            }

            self.entries.append(entry)

            print(f"[TOC] {entry['level']:10} | {title} -> {page_label}")

    # -------------------------------------------------
    def run(self):
        self.load_pdf()

        page_index = self.toc_start_page
        pages_used = 0

        while page_index < self.doc.page_count and pages_used < self.max_pages:

            print(f"\n[SCAN] Page {page_index + 1}")
            rows = self.extract_rows(page_index)

            if not self.is_toc_page(rows):
                print("[STOP] TOC pattern not detected")
                break

            print("[INFO] TOC page confirmed")
            self.extract_entries(rows)

            page_index += 1
            pages_used += 1

        print(f"\n[INFO] Total entries extracted: {len(self.entries)}")
        return self.entries


# ============================================================
# RUNNER
# ============================================================
def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python extractor_universal.py <pdf_path> <toc_start_page>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    toc_start_page = int(sys.argv[2]) - 1

    print("=" * 100)
    print("UNIVERSAL TOC EXTRACTOR STARTED")
    print("=" * 100)

    extractor = RuleBasedTOCExtractor(pdf_path, toc_start_page)
    entries = extractor.run()

    print("\n[FINAL TOC STRUCTURE]")
    pprint(entries, width=120)

    with open("toc_output.json", "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    print("\n[OUTPUT] toc_output.json written successfully")
    print("=" * 100)


if __name__ == "__main__":
    main()