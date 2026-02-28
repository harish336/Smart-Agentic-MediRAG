"""
LLM-based TOC Extractor (FALLBACK)
"""

import sys
import os
import json
import fitz
import re
from pprint import pformat
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.utils.logging_utils import get_component_logger


OLLAMA_MODEL = "mistral"


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("LLMTOCExtractor", component="ingestion")


# =====================================================
# Lazy Singleton LLM
# =====================================================

_llm_instance: Optional[ChatOllama] = None


def get_llm():
    global _llm_instance
    if _llm_instance is None:
        try:
            logger.info("Loading Ollama LLM (lazy)...")
            _llm_instance = ChatOllama(
                model=OLLAMA_MODEL,
                temperature=0,
                num_predict=4096
            )
            logger.info("LLM loaded successfully.")
        except Exception:
            logger.exception("Failed to load Ollama model")
            raise
    return _llm_instance


class LLMTOCExtractor:

    def __init__(self, pdf_path: str, toc_start_page: int, max_pages: int = 3):
        self.pdf_path = pdf_path
        self.toc_start_page = toc_start_page
        self.max_pages = max_pages
        self.doc = None
        self.llm = None

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
    def load_llm(self):
        logger.info("[STEP 2] Loading local Ollama LLM...")
        self.llm = get_llm()

    # -------------------------------------------------
    def build_prompt(self):

        system_prompt = """
You are a strict JSON generator.
Extract Table of Contents entries from raw PDF text.

Rules:
1. Use ONLY input text.
2. Do NOT invent titles or pages.
3. Output MUST be valid JSON.
4. No explanations.
"""

        user_prompt = """
Extract all TOC entries from this text:

{toc_text}

Return EXACTLY:

[
{
    "title": "string",
    "page_label": "string or null",
    "level": "chapter|section|subsection|unknown"
}
]
"""

        return ChatPromptTemplate.from_messages(
            [("system", system_prompt.strip()),
             ("user", user_prompt.strip())]
        )

    # -------------------------------------------------
    def run_llm(self, toc_pages):

        try:
            combined_text = ""
            for p in toc_pages:
                combined_text += f"\n--- PAGE {p['page']} ---\n"
                combined_text += p["text"]

            prompt = self.build_prompt()
            chain = prompt | self.llm | StrOutputParser()

            response = chain.invoke({"toc_text": combined_text})

            logger.debug("Raw LLM output received")
            return response

        except Exception:
            logger.exception("LLM execution failed")
            return ""

    # -------------------------------------------------
    def parse_output(self, raw_output: str):

        logger.info("[STEP] Parsing LLM output safely...")

        if not raw_output:
            logger.warning("Empty LLM output")
            return []

        start = raw_output.find("[")
        end = raw_output.rfind("]")

        if start == -1 or end == -1:
            logger.warning("No JSON array found in output")
            return []

        json_str = raw_output[start:end + 1]
        json_str = re.sub(r"\.\.\..*", "", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)

        try:
            parsed = json.loads(json_str)
            logger.info(f"Parsed {len(parsed)} TOC entries")
            return parsed
        except Exception:
            logger.exception("Failed parsing cleaned JSON")
            return []

    # -------------------------------------------------
    def roman_to_int(self, roman):
        roman = roman.lower()
        roman_map = {'i': 1, 'v': 5, 'x': 10, 'l': 50,
                     'c': 100, 'd': 500, 'm': 1000}
        total, prev = 0, 0
        for char in reversed(roman):
            value = roman_map.get(char, 0)
            if value < prev:
                total -= value
            else:
                total += value
            prev = value
        return total

    def sort_key(self, entry):
        label = entry.get("page_label")
        if label is None:
            return (2, float("inf"))

        if re.fullmatch(r"[ivxlcdmIVXLCDM]+", label):
            return (0, self.roman_to_int(label))

        if re.fullmatch(r"\d+", label):
            return (1, int(label))

        match = re.match(r"(\d+)", label)
        if match:
            return (1, int(match.group(1)))

        return (2, float("inf"))

    # -------------------------------------------------
    def is_toc_page(self, text):

        lower = text.lower()
        if "content" in lower:
            return True

        lines = text.splitlines()
        score = 0

        for line in lines:
            line = line.strip()
            if len(line) < 5:
                continue
            if re.search(r"\s(\d+|[ivxlcdm]+)$", line.lower()):
                score += 1
            if re.search(r"^\d+(\.\d+)+", line):
                score += 1
            if line.lower().startswith("chapter"):
                score += 1

        return score >= 3

    # -------------------------------------------------
    def collect_toc_text(self):

        logger.info("[STEP 3] Detecting consecutive TOC pages...")

        pages = []
        page_index = self.toc_start_page
        scanned = 0

        while page_index < self.doc.page_count and scanned < 15:

            page = self.doc.load_page(page_index)
            text = page.get_text("text")

            if not self.is_toc_page(text):
                break

            pages.append({
                "page": page_index + 1,
                "text": text
            })

            page_index += 1
            scanned += 1

        logger.info(f"Detected {len(pages)} consecutive TOC pages")
        return pages

    # -------------------------------------------------
    def run(self):

        try:
            self.load_pdf()
            self.load_llm()
            toc_pages = self.collect_toc_text()

            all_entries = []

            def process_page(page):
                raw = self.run_llm([page])
                return self.parse_output(raw)

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(process_page, page)
                           for page in toc_pages]

                for future in as_completed(futures):
                    result = future.result()
                    all_entries.extend(result)

            all_entries = sorted(all_entries, key=self.sort_key)
            logger.info("Sorting completed")

            return all_entries

        except Exception:
            logger.exception("LLM TOC extraction pipeline failed")
            raise


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 3:
        logger.warning(
            "Usage: python extractor_llm_fallback.py <pdf_path> <toc_start_page>"
        )
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        logger.error(f"File not found: {pdf_path}")
        sys.exit(1)

    try:
        toc_start_page = int(sys.argv[2]) - 1
        if toc_start_page < 0:
            raise ValueError
    except ValueError:
        logger.error("TOC start page must be positive integer")
        sys.exit(1)

    logger.info("=" * 100)
    logger.info("LLM TOC EXTRACTOR STARTED")
    logger.info("=" * 100)

    try:
        extractor = LLMTOCExtractor(pdf_path, toc_start_page)
        entries = extractor.run()

        logger.info("FINAL TOC STRUCTURE:")
        logger.info(pformat(entries, width=130))

        output_file = "toc_output_llm.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved to {output_file}")

    except Exception:
        logger.exception("Critical error in LLM TOC extractor")
        sys.exit(1)

    logger.info("=" * 100)
    logger.info("LLM TOC EXTRACTOR COMPLETED")
    logger.info("=" * 100)


if __name__ == "__main__":
    main()
