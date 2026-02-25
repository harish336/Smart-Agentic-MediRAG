"""
TOC Detector Module (Rule-Based + LLM Fallback)

Detects:
1. OFFSET_TOC
2. STRUCTURE_TOC
3. NO_TOC

If rule-based fails → automatically triggers LLM fallback.

Standalone runnable.
"""

import sys
import re
import json
import fitz

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


OLLAMA_MODEL = "mistral"


class TOCDetector:

    def __init__(self, pdf_path: str, max_scan_pages: int = 15):
        self.pdf_path = pdf_path
        self.max_scan_pages = max_scan_pages
        self.doc = None
        self.detected = []
        self.llm = None

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        try:
            self.doc = fitz.open(self.pdf_path)
            print("[OK] PDF loaded successfully")
            print(f"[INFO] Total pages: {self.doc.page_count}")
        except Exception as e:
            print(f"[ERROR] Failed to load PDF: {e}")
            sys.exit(1)

    # -------------------------------------------------
    # STEP 2: Rule-Based Detection
    # -------------------------------------------------
    def detect_toc(self):
        print("[STEP 2] Running rule-based TOC detection...")

        pages_to_scan = min(self.max_scan_pages, self.doc.page_count)

        for page_index in range(pages_to_scan):
            page = self.doc.load_page(page_index)
            text = page.get_text("text")
            text_lower = text.lower()

            has_contents_word = (
                "contents" in text_lower or
                re.search(r"c\s*o\s*n\s*t\s*e\s*n\s*t\s*s", text_lower)
            )

            section_lines = re.findall(r"(?m)^\s*\d+(\.\d+)*[:\s]", text)
            trailing_numbers = re.findall(r"(?m)\s+\d+\s*$", text)
            bullet_points = re.findall(r"[•\-]\s+", text)

            print(
                f"[PAGE {page_index + 1}] "
                f"sections={len(section_lines)}, "
                f"trailing_nums={len(trailing_numbers)}, "
                f"bullets={len(bullet_points)}"
            )

            toc_type = None

            if len(trailing_numbers) >= 5:
                toc_type = "OFFSET_TOC"
            elif has_contents_word and (len(section_lines) >= 5 or len(bullet_points) >= 5):
                toc_type = "STRUCTURE_TOC"
            elif len(section_lines) >= 10 and page_index <= 3:
                toc_type = "STRUCTURE_TOC"

            if toc_type:
                print(f"  -> [DETECTED] {toc_type}")
                self.detected.append({
                    "page_index": page_index,
                    "toc_type": toc_type
                })

        # If rule-based fails → fallback
        if not self.detected:
            print("\n[INFO] Rule-based detection failed → switching to LLM fallback")
            self.llm_fallback()

    # -------------------------------------------------
    # STEP 3: LLM Fallback
    # -------------------------------------------------
    def llm_fallback(self):

        print("[LLM] Loading local Ollama model...")
        self.llm = ChatOllama(
            model=OLLAMA_MODEL,
            temperature=0
        )

        system_prompt = """
You are a strict classifier.

Determine if the given page is a Table of Contents page.

Return ONLY valid JSON:

{{
  "is_toc": true or false,
  "toc_type": "OFFSET_TOC" or "STRUCTURE_TOC" or null
}}

Rules:
- OFFSET_TOC = page numbers visible
- STRUCTURE_TOC = structured headings without page numbers
- If not TOC, return is_toc=false
- No explanation
"""

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("user", "{page_text}")]
        )

        chain = prompt | self.llm | StrOutputParser()

        pages_to_scan = min(15, self.doc.page_count)

        for page_index in range(pages_to_scan):
            page = self.doc.load_page(page_index)
            text = page.get_text("text")[:3000]

            print(f"[LLM] Checking page {page_index + 1}...")

            response = chain.invoke({"page_text": text})

            try:
                data = json.loads(response)
            except:
                print("[LLM] Invalid JSON response — skipping page")
                continue

            if data.get("is_toc"):
                toc_type = data.get("toc_type") or "STRUCTURE_TOC"

                print(f"[LLM DETECTED] Page {page_index + 1} | Type={toc_type}")

                self.detected.append({
                    "page_index": page_index,
                    "toc_type": toc_type
                })

                return

        print("[LLM] No TOC detected via fallback.")

    # -------------------------------------------------
    # STEP 4: Final Result
    # -------------------------------------------------
    def get_result(self):
        print("\n[STEP 4] Final TOC detection result")

        if not self.detected:
            print("[RESULT] ❌ NO TOC FOUND")
            return []

        for item in self.detected:
            print(
                f"[RESULT] ✅ TOC FOUND | "
                f"Page {item['page_index'] + 1} | "
                f"Type={item['toc_type']}"
            )

        return self.detected


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python detector.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print("=" * 80)
    print("TOC DETECTOR STARTED")
    print(f"PDF Path: {pdf_path}")
    print("=" * 80)

    detector = TOCDetector(pdf_path)
    detector.load_pdf()
    detector.detect_toc()
    result = detector.get_result()

    print("\n[FINAL OUTPUT]")
    print(json.dumps(result, indent=2))

    print("=" * 80)
    print("TOC DETECTOR COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()