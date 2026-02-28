import sys
import fitz
from collections import Counter
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("StyleAnalyzer", component="ingestion")


# =====================================================
# Lazy LLM Singleton
# =====================================================

_llm_instance: Optional[ChatOllama] = None


def get_llm():
    global _llm_instance
    if _llm_instance is None:
        logger.info("Loading Ollama model (lazy)...")
        _llm_instance = ChatOllama(
            model="mistral",
            temperature=0
        )
        logger.info("LLM loaded successfully.")
    return _llm_instance


class StyleAnalyzer:

    def __init__(self, pdf_path, toc_start_page):
        self.pdf_path = pdf_path
        self.toc_start_page = toc_start_page
        self.doc = None
        self.font_counter = Counter()
        self.blocks = []
        self.llm = None

    # -------------------------------------------------
    def load_pdf(self):
        logger.info("[STEP 1] Loading PDF...")
        try:
            self.doc = fitz.open(self.pdf_path)
            logger.info(f"Loaded PDF | Pages: {self.doc.page_count}")
        except Exception:
            logger.exception("Failed to load PDF")
            raise

    # -------------------------------------------------
    def load_llm(self):
        self.llm = get_llm()

    # -------------------------------------------------
    def detect_consecutive_toc(self):

        logger.info("[STEP 2] Detecting consecutive TOC pages using LLM...")
        self.load_llm()

        prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a highly accurate document classification AI.\n"
     "Your only task is to determine if the provided text from a PDF page constitutes a 'Table of Contents' (TOC).\n\n"
     "CHARACTERISTICS OF A TOC PAGE:\n"
     "1. Contains a structured list of chapters, sections, or headings.\n"
     "2. Pairs these headings with specific page numbers (e.g., 'Introduction .... 5').\n"
     "3. Usually features words like 'Contents', 'Table of Contents', or 'Brief Contents' near the top.\n\n"
     "EXCLUSIONS (Respond NO):\n"
     "- A page that simply mentions the phrase 'Table of Contents' in standard prose/paragraphs.\n"
     "- An alphabetical keyword index or glossary at the end of a book.\n"
     "- A title page, copyright page, or preface.\n\n"
     "OUTPUT FORMAT:\n"
     "Respond with exactly one word: YES or NO. Do not add punctuation, markdown, or explanations."
    ),
    ("user",
     "Analyze the following PDF page text and classify it:\n\n"
     "--- PAGE TEXT START ---\n"
     "{page_text}\n"
     "--- PAGE TEXT END ---\n\n"
     "Is this a Table of Contents page? (YES/NO):")
])

        chain = prompt | self.llm | StrOutputParser()

        page_index = self.toc_start_page
        toc_pages = 0

        try:
            while page_index < self.doc.page_count:

                page = self.doc.load_page(page_index)
                text = page.get_text("text")[:2000]

                logger.info(f"[LLM] Checking page {page_index + 1}...")

                response = chain.invoke(
                    {"page_text": text}
                ).strip().upper()

                logger.info(f"[LLM Response] {response}")

                if response.startswith("YES"):
                    toc_pages += 1
                    page_index += 1
                else:
                    break

        except Exception:
            logger.exception("LLM TOC detection failed")
            raise

        toc_end_page = self.toc_start_page + toc_pages

        logger.info(f"Consecutive TOC pages detected: {toc_pages}")
        logger.info(f"Content analysis will start from page: {toc_end_page + 1}")

        return toc_end_page

    # -------------------------------------------------
    def extract_fonts_after_toc(self, start_page):

        logger.info("[STEP 3] Extracting font styles after TOC...")

        try:
            for page_index in range(start_page, self.doc.page_count):

                page = self.doc.load_page(page_index)
                blocks = page.get_text("dict")["blocks"]

                for block in blocks:
                    if block["type"] != 0:
                        continue

                    for line in block["lines"]:
                        for span in line["spans"]:

                            text = span["text"].strip()
                            size = round(span["size"], 1)

                            if not text:
                                continue

                            self.font_counter[size] += 1

                            self.blocks.append({
                                "text": text,
                                "size": size,
                                "page": page_index + 1
                            })

            logger.info("Font extraction complete")

        except Exception:
            logger.exception("Font extraction failed")
            raise

    # -------------------------------------------------
    def analyze_styles(self):

        logger.info("[STEP 4] Analyzing font distribution...")

        if not self.font_counter:
            logger.error("No font data extracted")
            return

        for size, count in self.font_counter.most_common():
            logger.info(f"Font Size {size} → {count} occurrences")

        if len(self.font_counter) < 2:
            logger.warning("Not enough font variation")
            return

        body_size = self.font_counter.most_common(1)[0][0]
        unique_sizes = sorted(self.font_counter.keys())

        chapter_size = unique_sizes[-1]
        subheading_size = (
            unique_sizes[-2] if len(unique_sizes) > 1 else body_size
        )

        logger.info("Detected Structure:")
        logger.info(f"Chapter Font Size    : {chapter_size}")
        logger.info(f"Subheading Font Size : {subheading_size}")
        logger.info(f"Body Font Size       : {body_size}")

        self.show_examples(chapter_size, subheading_size, body_size)

    # -------------------------------------------------
    def show_examples(self, chapter_size, subheading_size, body_size):

        logger.info("[SAMPLE OUTPUT]")

        printed = {"chapter": 0, "subheading": 0, "body": 0}

        for block in self.blocks:

            if printed["chapter"] < 5 and block["size"] == chapter_size:
                logger.info(
                    f"[CHAPTER] Page {block['page']} | {block['text']}"
                )
                printed["chapter"] += 1

            elif printed["subheading"] < 5 and block["size"] == subheading_size:
                logger.info(
                    f"[SUBHEADING] Page {block['page']} | {block['text']}"
                )
                printed["subheading"] += 1

            elif printed["body"] < 5 and block["size"] == body_size:
                logger.info(
                    f"[BODY] Page {block['page']} | {block['text']}"
                )
                printed["body"] += 1

            if all(v >= 5 for v in printed.values()):
                break

    # -------------------------------------------------
    def run(self):

        logger.info("=" * 80)
        logger.info("POST-TOC STYLE ANALYZER")
        logger.info("=" * 80)

        try:
            self.load_pdf()
            toc_end = self.detect_consecutive_toc()
            self.extract_fonts_after_toc(toc_end)
            self.analyze_styles()

        except Exception:
            logger.exception("Style analysis pipeline failed")
            raise

        logger.info("=" * 80)
        logger.info("ANALYSIS COMPLETED")
        logger.info("=" * 80)


# -------------------------------------------------
# CLI
# -------------------------------------------------

def main():

    if len(sys.argv) < 3:
        logger.warning(
            "Usage: python style_analyzer.py <pdf_path> <toc_start_page>"
        )
        sys.exit(1)

    pdf_path = sys.argv[1]
    toc_start_page = int(sys.argv[2]) - 1

    try:
        analyzer = StyleAnalyzer(pdf_path, toc_start_page)
        analyzer.run()
    except Exception:
        logger.exception("Style analyzer crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
