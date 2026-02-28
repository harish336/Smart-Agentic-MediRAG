"""
Text Cleaner (Standalone & Verbose)
"""

import sys
import json
import re
from pprint import pformat
from typing import List

from core.utils.logging_utils import get_component_logger

# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("TextCleaner", component="ingestion")


class TextCleaner:

    def __init__(self, aggressive: bool = False):
        self.aggressive = aggressive

    # -------------------------------------------------
    def normalize_whitespace(self, text: str) -> str:
        logger.debug("Normalizing whitespace")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # -------------------------------------------------
    def remove_dotted_leaders(self, text: str) -> str:
        logger.debug("Removing dotted leaders")
        return re.sub(r"\.{2,}", " ", text)

    # -------------------------------------------------
    def remove_repeated_symbols(self, text: str) -> str:
        logger.debug("Removing repeated symbols")
        return re.sub(r"[-_]{2,}", " ", text)

    # -------------------------------------------------
    def fix_hyphenated_words(self, text: str) -> str:
        logger.debug("Fixing hyphenated line breaks")
        return re.sub(r"(\w+)-\s+(\w+)", r"\1\2", text)

    # -------------------------------------------------
    def remove_non_printable(self, text: str) -> str:
        logger.debug("Removing non-printable characters")
        return "".join(c for c in text if c.isprintable())

    # -------------------------------------------------
    def aggressive_cleanup(self, text: str) -> str:
        logger.debug("Applying aggressive OCR cleanup")

        text = re.sub(r"\b[^a-zA-Z0-9\s]{1,2}\b", " ", text)
        text = re.sub(r"[!?]{2,}", ".", text)
        text = re.sub(r"\b[a-zA-Z]\b", " ", text)

        return text

    # -------------------------------------------------
    def clean(self, text: str) -> str:

        try:
            logger.info("TEXT CLEANING STARTED")
            logger.info(f"Input length: {len(text)}")

            text = self.remove_non_printable(text)
            text = self.fix_hyphenated_words(text)
            text = self.remove_dotted_leaders(text)
            text = self.remove_repeated_symbols(text)
            text = self.normalize_whitespace(text)

            if self.aggressive:
                text = self.aggressive_cleanup(text)
                text = self.normalize_whitespace(text)

            logger.info(f"Output length: {len(text)}")
            logger.info("TEXT CLEANING COMPLETED")

            return text

        except Exception:
            logger.exception("Text cleaning failed")
            raise

    # -------------------------------------------------
    def clean_list(self, texts: List[str]) -> List[str]:

        logger.info(f"Batch cleaning {len(texts)} texts")

        try:
            return [
                self.clean(t)
                for t in texts
                if isinstance(t, str)
            ]
        except Exception:
            logger.exception("Batch text cleaning failed")
            raise


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 2:
        logger.warning(
            "Usage: python text_cleaner.py <text_or_json> [--aggressive]"
        )
        sys.exit(1)

    input_value = sys.argv[1]
    aggressive = "--aggressive" in sys.argv

    logger.info("=" * 100)
    logger.info("TEXT CLEANER STARTED")
    logger.info(f"Aggressive mode: {aggressive}")
    logger.info("=" * 100)

    cleaner = TextCleaner(aggressive=aggressive)

    try:

        # JSON input
        if input_value.lower().endswith(".json"):

            with open(input_value, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                logger.error("JSON must contain a list of strings")
                sys.exit(1)

            cleaned = cleaner.clean_list(data)

            logger.info("CLEANED OUTPUT:")
            logger.info(pformat(cleaned))

        # Direct text input
        else:
            cleaned = cleaner.clean(input_value)
            logger.info("CLEANED OUTPUT:")
            logger.info(cleaned)

    except Exception:
        logger.exception("Text cleaner crashed")
        sys.exit(1)

    logger.info("=" * 100)
    logger.info("TEXT CLEANER COMPLETED")
    logger.info("=" * 100)


if __name__ == "__main__":
    main()
