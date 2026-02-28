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
from pprint import pformat

from core.utils.logging_utils import get_component_logger

ROMAN_RE = r"[ivxlcdmIVXLCDM]+"
DIGIT_RE = r"\d+"
PAGE_RE = rf"({ROMAN_RE}|{DIGIT_RE})$"


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("RuleBasedTOCExtractor", component="ingestion")


class RuleBasedTOCExtractor:

    def __init__(self, pdf_path: str, toc_start_page: int, max_pages: int = 15):
        self.pdf_path = pdf_path
        self.toc_start_page = toc_start_page
        self.max_pages = max_pages
        self.doc = None
        self.entries = []

    # -------------------------------------------------
    def load_pdf(self):

        logger.info("[STEP 1] Loading PDF...")

        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info(f"PDF loaded | Total pages: {self.doc.page_count}")
        except Exception:
            logger.exception("Failed to load PDF")
            raise

    # -------------------------------------------------
    def extract_rows(self, page_index, y_tol=4):

        try:
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

        except Exception:
            logger.exception(f"Failed extracting rows from page {page_index + 1}")
            return []

    # -------------------------------------------------
    def is_toc_page(self, rows):

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
        logger.debug(f"TOC score: {score}")

        return score >= 4

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
            line = re.sub(r"\.{2,}", " ", line)

            match = re.search(PAGE_RE, line)
            if not match:
                continue

            page_label = match.group(1)
            title = line[: match.start()].strip()

            if len(title) < 3:
                continue

            entry = {
                "title": title,
                "page_label": page_label,
                "level": self.detect_level(title)
            }

            self.entries.append(entry)

            logger.info(
                f"[TOC] {entry['level']:10} | {title} -> {page_label}"
            )

    # -------------------------------------------------
    def run(self):

        try:
            self.load_pdf()

            page_index = self.toc_start_page
            pages_used = 0

            while (
                page_index < self.doc.page_count
                and pages_used < self.max_pages
            ):

                logger.info(f"[SCAN] Page {page_index + 1}")

                rows = self.extract_rows(page_index)

                if not rows or not self.is_toc_page(rows):
                    logger.info("TOC pattern not detected — stopping")
                    break

                logger.info("TOC page confirmed")
                self.extract_entries(rows)

                page_index += 1
                pages_used += 1

            logger.info(
                f"Total entries extracted: {len(self.entries)}"
            )

            return self.entries

        except Exception:
            logger.exception("Rule-based TOC extraction failed")
            raise


# ============================================================
# RUNNER
# ============================================================

def main():

    if len(sys.argv) < 3:
        logger.warning(
            "Usage: python extractor_universal.py <pdf_path> <toc_start_page>"
        )
        sys.exit(1)

    pdf_path = sys.argv[1]

    try:
        toc_start_page = int(sys.argv[2]) - 1
    except Exception:
        logger.error("Invalid TOC start page")
        sys.exit(1)

    logger.info("=" * 100)
    logger.info("UNIVERSAL TOC EXTRACTOR STARTED")
    logger.info("=" * 100)

    try:
        extractor = RuleBasedTOCExtractor(pdf_path, toc_start_page)
        entries = extractor.run()

        logger.info("FINAL TOC STRUCTURE:")
        logger.info(pformat(entries, width=120))

        with open("toc_output.json", "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        logger.info("toc_output.json written successfully")

    except Exception:
        logger.exception("Universal TOC extractor crashed")
        sys.exit(1)

    logger.info("=" * 100)


if __name__ == "__main__":
    main()
