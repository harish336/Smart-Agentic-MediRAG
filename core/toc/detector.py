"""
TOC Detector Module (Rule-Based + LLM Fallback)
"""

import sys
import re
import json
import fitz
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.utils.logging_utils import get_component_logger


OLLAMA_MODEL = "mistral"


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("TOCDetector", component="ingestion")


# =====================================================
# Lazy Singleton for LLM
# =====================================================

_llm_instance: Optional[ChatOllama] = None


def get_llm():
    global _llm_instance
    if _llm_instance is None:
        try:
            logger.info("Loading Ollama model for TOC detection (lazy)...")
            _llm_instance = ChatOllama(
                model=OLLAMA_MODEL,
                temperature=0
            )
            logger.info("LLM loaded successfully.")
        except Exception:
            logger.exception("Failed to load Ollama model")
            raise
    return _llm_instance


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

        logger.info("[STEP 1] Loading PDF...")

        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info("PDF loaded successfully")
            logger.info(f"Total pages: {self.doc.page_count}")
        except Exception:
            logger.exception("Failed to load PDF")
            sys.exit(1)

    # -------------------------------------------------
    # STEP 2: Rule-Based Detection
    # -------------------------------------------------
    def detect_toc(self):

        logger.info("[STEP 2] Running rule-based TOC detection...")

        try:
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

                logger.info(
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
                    logger.info(f"Detected {toc_type}")
                    self.detected.append({
                        "page_index": page_index,
                        "toc_type": toc_type
                    })

            if not self.detected:
                logger.info("Rule-based detection failed → switching to LLM fallback")
                self.llm_fallback()

        except Exception:
            logger.exception("Rule-based TOC detection failed")

    # -------------------------------------------------
    # STEP 3: LLM Fallback
    # -------------------------------------------------
    def llm_fallback(self):

        try:
            self.llm = get_llm()

            system_prompt = """
You are a strict classifier.

Determine if the given page is a Table of Contents page.

Return ONLY valid JSON:

{
  "is_toc": true or false,
  "toc_type": "OFFSET_TOC" or "STRUCTURE_TOC" or null
}

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

                logger.info(f"[LLM] Checking page {page_index + 1}...")

                response = chain.invoke({"page_text": text})

                try:
                    data = json.loads(response)
                except Exception:
                    logger.warning("Invalid JSON response from LLM — skipping page")
                    continue

                if data.get("is_toc"):
                    toc_type = data.get("toc_type") or "STRUCTURE_TOC"

                    logger.info(
                        f"LLM detected TOC | Page {page_index + 1} | Type={toc_type}"
                    )

                    self.detected.append({
                        "page_index": page_index,
                        "toc_type": toc_type
                    })

                    return

            logger.info("LLM fallback found no TOC.")

        except Exception:
            logger.exception("LLM fallback detection failed")

    # -------------------------------------------------
    # STEP 4: Final Result
    # -------------------------------------------------
    def get_result(self):

        logger.info("[STEP 4] Final TOC detection result")

        if not self.detected:
            logger.warning("NO TOC FOUND")
            return []

        for item in self.detected:
            logger.info(
                f"TOC FOUND | Page {item['page_index'] + 1} | Type={item['toc_type']}"
            )

        return self.detected


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 2:
        logger.warning("Usage: python detector.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    logger.info("=" * 80)
    logger.info("TOC DETECTOR STARTED")
    logger.info(f"PDF Path: {pdf_path}")
    logger.info("=" * 80)

    try:
        detector = TOCDetector(pdf_path)
        detector.load_pdf()
        detector.detect_toc()
        result = detector.get_result()

        logger.info("FINAL OUTPUT:")
        logger.info(json.dumps(result, indent=2))

        logger.info("=" * 80)
        logger.info("TOC DETECTOR COMPLETED")
        logger.info("=" * 80)

    except Exception:
        logger.exception("Standalone TOC detector crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
