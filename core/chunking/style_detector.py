"""
Style Detector

Purpose:
- Analyze PDF text styles using font sizes and lightweight text heuristics
- Identify heading, subheading, and body text
- Identify page types (cover/front matter/toc/content/chapter/index/etc.)
- Remove running headers / footers using frequency
- Output structured units for chunking
"""

import re
from collections import Counter

import fitz  # PyMuPDF

from config.system_loader import get_system_config


class StyleDetector:
    def __init__(self, pdf_path: str, max_pages: int = None):
        self.pdf_path = pdf_path
        self.config = get_system_config()

        style_cfg = self.config.get("style", {}).get("font_size_analysis", {})
        cfg_max = style_cfg.get("sample_pages", 120)
        self.max_pages = max_pages or cfg_max

        self.doc = None
        self.font_counter = Counter()
        self.header_footer_counter = Counter()
        self.style_map = {}
        self.body_size = None
        self.page_types = {}
        self.min_heading_ratio = (
            self.config.get("style", {})
            .get("font_size_analysis", {})
            .get("min_frequency_ratio", 0.05)
        )

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
                if block.get("type") != 0:
                    continue

                for line in block.get("lines", []):
                    line_text = " ".join(
                        span.get("text", "") for span in line.get("spans", [])
                    ).strip()
                    if not line_text:
                        continue

                    font_sizes = []
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        size = round(span.get("size", 0.0), 1)
                        if not text or size <= 0:
                            continue
                        font_sizes.append(size)

                    if not font_sizes:
                        continue

                    avg_size = round(sum(font_sizes) / len(font_sizes), 1)
                    self.font_counter[avg_size] += 1

                    # Capture top/bottom frequent lines (headers/footers)
                    y0, y1 = line["bbox"][1], line["bbox"][3]
                    if y0 < 80 or y1 > page.rect.height - 80:
                        normalized = re.sub(r"\s+", " ", line_text.lower())
                        self.header_footer_counter[normalized] += 1

        print(f"[INFO] Unique font sizes: {len(self.font_counter)}")

    # -------------------------------------------------
    # STEP 3: Identify styles
    # -------------------------------------------------
    def identify_styles(self):
        print("\n[STEP 3] Identifying heading styles...")

        if not self.font_counter:
            print("[ERROR] No font data collected")
            return

        total_lines = sum(self.font_counter.values()) or 1
        ordered = sorted(
            self.font_counter.items(),
            key=lambda x: (-x[1], -x[0]),
        )

        self.body_size = ordered[0][0]

        frequent_sizes = [
            size for size, cnt in self.font_counter.items()
            if (cnt / total_lines) >= self.min_heading_ratio
        ]

        if not frequent_sizes:
            frequent_sizes = [self.body_size]

        # Largest frequent size becomes heading; next candidate above body becomes subheading
        heading_size = max(frequent_sizes)

        subheading_candidates = sorted(
            [s for s in frequent_sizes if self.body_size < s < heading_size],
            reverse=True,
        )

        subheading_size = subheading_candidates[0] if subheading_candidates else self.body_size

        if heading_size <= self.body_size:
            heading_size = round(self.body_size + 0.5, 1)

        self.style_map = {
            heading_size: "heading",
            subheading_size: "subheading",
            self.body_size: "body",
        }

        print(f"[STYLE MAP] body={self.body_size} subheading={subheading_size} heading={heading_size}")

    # -------------------------------------------------
    # STEP 4: Detect running headers / footers
    # -------------------------------------------------
    def detect_headers_footers(self):
        print("\n[STEP 4] Detecting running headers/footers...")

        threshold_ratio = (
            self.config.get("style", {})
            .get("running_headers", {})
            .get("frequency_threshold", 0.8)
        )

        pages = max(1, min(self.max_pages, self.doc.page_count))
        threshold = max(2, int(pages * threshold_ratio))

        self.headers_footers = {
            text for text, count in self.header_footer_counter.items()
            if count >= threshold
        }

        print(f"[INFO] Identified headers/footers: {len(self.headers_footers)}")

    # -------------------------------------------------
    # STEP 5: Identify page types
    # -------------------------------------------------
    def classify_pages(self):
        print("\n[STEP 5] Classifying page types...")

        type_counter = Counter()

        for page_idx in range(self.doc.page_count):
            page = self.doc.load_page(page_idx)
            page_type = self._classify_single_page(page, page_idx)
            self.page_types[page_idx + 1] = page_type
            type_counter[page_type] += 1

        print(f"[INFO] Page type distribution: {dict(type_counter)}")

    def _classify_single_page(self, page, page_idx):
        text = page.get_text("text") or ""
        text_norm = re.sub(r"\s+", " ", text).strip()
        text_low = text_norm.lower()

        # Low-text page checks
        words = re.findall(r"\w+", text_low)
        word_count = len(words)

        blocks = page.get_text("dict").get("blocks", [])
        image_blocks = sum(1 for b in blocks if b.get("type") == 1)
        text_blocks = sum(1 for b in blocks if b.get("type") == 0)

        if word_count <= 3 and image_blocks > 0:
            return "image_only"

        if word_count <= 5 and text_blocks <= 1:
            return "blank_or_noise"

        if image_blocks > text_blocks and word_count < 80:
            return "image_heavy"

        if re.search(r"\b(table of contents|contents|brief contents)\b", text_low):
            return "toc"

        toc_like_rows = len(re.findall(r"(?m)^\s*.+\.{2,}\s*[ivxlcdm\d]+\s*$", text_low))
        if toc_like_rows >= 5:
            return "toc"

        if re.search(r"\b(index)\b", text_low) and len(re.findall(r"(?m)^[a-z][^\n]{2,}\s+\d+\s*$", text_low)) >= 6:
            return "index"

        if re.search(r"\b(bibliography|references|works cited)\b", text_low):
            return "references"

        if re.search(r"\b(glossary)\b", text_low):
            return "glossary"

        if re.search(r"\b(appendix|appendices)\b", text_low):
            return "appendix"

        if page_idx == 0 and word_count < 120:
            return "cover"

        if page_idx < 8 and re.search(r"\b(preface|foreword|acknowledg|copyright|dedication|about the author)\b", text_low):
            return "front_matter"

        # Chapter/title-like pages
        first_line = text_norm.split("\n", 1)[0].strip() if text_norm else ""
        chapter_like = bool(re.match(r"^(chapter|part)\b", first_line, re.IGNORECASE))
        if chapter_like and word_count < 250:
            return "chapter_start"

        return "content"

    # -------------------------------------------------
    # STEP 6: Extract structured units
    # -------------------------------------------------
    def extract_units(self):
        print("\n[STEP 6] Extracting structured text units...")
        units = []

        ignored_page_types = {
            "blank_or_noise",
            "image_only",
            "image_heavy",
            "toc",
            "index",
            "references",
            "glossary",
        }

        for page_idx in range(self.doc.page_count):
            page_number = page_idx + 1
            page_type = self.page_types.get(page_number, "content")

            if page_type in ignored_page_types:
                continue

            page = self.doc.load_page(page_idx)
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block.get("type") != 0:
                    continue

                for line_idx, line in enumerate(block.get("lines", [])):
                    spans = line.get("spans", [])
                    line_text = "".join(span.get("text", "") for span in spans).strip()
                    if not line_text:
                        continue

                    normalized = re.sub(r"\s+", " ", line_text.lower())
                    if normalized in self.headers_footers:
                        continue

                    font_sizes = [round(span.get("size", 0.0), 1) for span in spans if span.get("size")]
                    if not font_sizes:
                        continue

                    avg_size = round(sum(font_sizes) / len(font_sizes), 1)
                    unit_type = self._classify_line(line_text, avg_size, page_type)

                    units.append(
                        {
                            "type": unit_type,
                            "text": line_text,
                            "page": page_number,
                            "page_type": page_type,
                            "font_size": avg_size,
                            "line_index": line_idx,
                        }
                    )

        print(f"[INFO] Total units extracted: {len(units)}")
        return units

    def _classify_line(self, text, avg_size, page_type):
        # Chapter start pages should prioritize heading/subheading tags.
        if page_type == "chapter_start":
            if len(text.split()) <= 18:
                return "heading"

        # Size-first mapping
        if avg_size in self.style_map:
            mapped = self.style_map[avg_size]
            if mapped != "body":
                return mapped

        # Heuristic promotion for likely section titles
        word_count = len(text.split())
        alpha_ratio = sum(ch.isalpha() for ch in text) / max(1, len(text))
        is_upperish = text.isupper() and word_count <= 14
        starts_with_number = bool(re.match(r"^\d+(\.\d+)*\s+", text))
        chapter_like = bool(re.match(r"^(chapter|part)\b", text.strip(), re.IGNORECASE))

        if chapter_like or (is_upperish and avg_size >= self.body_size):
            return "heading"

        if starts_with_number and word_count <= 18 and alpha_ratio > 0.4:
            return "subheading"

        # Slight size bump + short line tends to be subheading
        if avg_size > self.body_size and word_count <= 12:
            return "subheading"

        return "body"

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        self.load_pdf()
        self.collect_font_stats()
        self.identify_styles()
        self.detect_headers_footers()
        self.classify_pages()
        return self.extract_units()


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    import json
    import sys

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

    with open("style_units.json", "w", encoding="utf-8") as f:
        json.dump(units, f, indent=2)

    print("\n[OUTPUT] Saved to style_units.json")
    print("=" * 100)
    print("STYLE DETECTOR COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
