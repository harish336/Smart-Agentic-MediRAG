"""
Style Detector (Standalone)

Purpose:
- Analyze PDF text styles using font sizes
- Identify heading, subheading, and body text
- Remove running headers / footers using frequency
- Output structured units for chunking

This file CAN be run independently.
"""

import sys
import fitz  # PyMuPDF
from collections import Counter, defaultdict
from pprint import pprint


class StyleDetector:
    def __init__(self, pdf_path: str, max_pages: int = 20):
        self.pdf_path = pdf_path
        self.max_pages = max_pages
        self.doc = None
        self.font_counter = Counter()
        self.header_footer_counter = Counter()
        self.style_map = {}

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        self.doc = fitz.open(self.pdf_path)
        print("[OK] PDF loaded")
        print(f"[INFO] Total pages: {self.doc.page_count}")

    # -------------------------------------------------
    # STEP 2: Collect font statistics
    # -------------------------------------------------
    def collect_font_stats(self):
        print("\n[STEP 2] Collecting font size statistics...")

        pages = min(self.max_pages, self.doc.page_count)

        for page_idx in range(pages):
            page = self.doc.load_page(page_idx)
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block["type"] != 0:
                    continue

                for line in block["lines"]:
                    for span in line["spans"]:
                        size = round(span["size"], 1)
                        text = span["text"].strip()

                        if not text:
                            continue

                        self.font_counter[size] += 1

                        # Capture top/bottom frequent lines (headers/footers)
                        if line["bbox"][1] < 80 or line["bbox"][3] > page.rect.height - 80:
                            self.header_footer_counter[text.lower()] += 1

        print("[INFO] Font size frequencies:")
        pprint(self.font_counter.most_common())

    # -------------------------------------------------
    # STEP 3: Identify styles
    # -------------------------------------------------
    def identify_styles(self):
        print("\n[STEP 3] Identifying heading styles...")

        if not self.font_counter:
            print("[ERROR] No font data collected")
            return

        sizes = [s for s, _ in self.font_counter.most_common()]

        body_size = sizes[0]
        heading_size = max(sizes)
        subheading_size = sizes[1] if len(sizes) > 1 else body_size

        self.style_map = {
            heading_size: "heading",
            subheading_size: "subheading",
            body_size: "body"
        }

        print("[STYLE MAP]")
        pprint(self.style_map)

    # -------------------------------------------------
    # STEP 4: Detect running headers / footers
    # -------------------------------------------------
    def detect_headers_footers(self):
        print("\n[STEP 4] Detecting running headers/footers...")

        threshold = max(3, self.max_pages // 2)
        self.headers_footers = {
            text for text, count in self.header_footer_counter.items()
            if count >= threshold
        }

        print("[INFO] Identified headers/footers:")
        pprint(self.headers_footers)

    # -------------------------------------------------
    # STEP 5: Extract structured units
    # -------------------------------------------------
    def extract_units(self):
        print("\n[STEP 5] Extracting structured text units...")
        units = []

        for page_idx in range(self.doc.page_count):
            page = self.doc.load_page(page_idx)
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block["type"] != 0:
                    continue

                for line in block["lines"]:
                    line_text = ""
                    font_sizes = []

                    for span in line["spans"]:
                        text = span["text"]
                        size = round(span["size"], 1)
                        line_text += text
                        font_sizes.append(size)

                    clean = line_text.strip()
                    if not clean:
                        continue

                    # Skip headers / footers
                    if clean.lower() in self.headers_footers:
                        print(f"[SKIP] Header/Footer removed: {clean}")
                        continue

                    avg_size = round(sum(font_sizes) / len(font_sizes), 1)
                    unit_type = self.style_map.get(avg_size, "body")

                    unit = {
                        "type": unit_type,
                        "text": clean,
                        "page": page_idx + 1,
                        "font_size": avg_size
                    }

                    print(f"[UNIT] {unit_type.upper():10} | Pg {page_idx+1} | {clean[:80]}")
                    units.append(unit)

        print(f"\n[INFO] Total units extracted: {len(units)}")
        return units

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        self.load_pdf()
        self.collect_font_stats()
        self.identify_styles()
        self.detect_headers_footers()
        return self.extract_units()


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python style_detector.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print("=" * 100)
    print("STYLE DETECTOR STARTED")
    print(f"PDF Path: {pdf_path}")
    print("=" * 100)

    detector = StyleDetector(pdf_path)
    units = detector.run()

    print("\n[FINAL STRUCTURED UNITS]")
    pprint(units[:20], width=120)

    import json
    with open("style_units.json", "w", encoding="utf-8") as f:
        json.dump(units, f, indent=2)

    print("\n[OUTPUT] Saved to style_units.json")
    print("=" * 100)
    print("STYLE DETECTOR COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
