"""
SMART MEDIRAG — TOC ORCHESTRATOR (PRODUCTION VERSION)
"""

import sys
import json
from pprint import pformat

from core.toc.detector import TOCDetector
from core.toc.extractor_rule_based import RuleBasedTOCExtractor
from core.toc.extractor_llm_fallback import LLMTOCExtractor
from core.toc.confidence import TOCConfidenceScorer
from core.toc.offset_finder import OffsetFinder
from core.utils.logging_utils import get_component_logger

SAVE_INTERMEDIATE = True


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("TOCOrchestrator", component="ingestion")


class TOCOrchestrator:

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.toc_page = None
        self.toc_type = None
        self.toc_entries = []
        self.offset = None

    # -------------------------------------------------
    # STEP 1: Detect TOC
    # -------------------------------------------------
    def detect_toc(self):

        logger.info("[STEP 1] Detecting TOC...")

        try:
            detector = TOCDetector(self.pdf_path)
            detector.load_pdf()
            detector.detect_toc()
            results = detector.get_result()

            if not results:
                logger.warning("No TOC detected")
                return False

            self.toc_page = results[0]["page_index"]
            self.toc_type = results[0]["toc_type"]

            logger.info(
                f"TOC detected | Page={self.toc_page + 1} | Type={self.toc_type}"
            )

            return True

        except Exception:
            logger.exception("TOC detection failed")
            return False

    # -------------------------------------------------
    # STEP 2: Rule-based extraction
    # -------------------------------------------------
    def extract_rule_based(self):

        logger.info("[STEP 2] Rule-based TOC extraction...")

        try:
            extractor = RuleBasedTOCExtractor(
                self.pdf_path,
                toc_start_page=self.toc_page
            )

            self.toc_entries = extractor.run()

            if SAVE_INTERMEDIATE:
                with open("toc_rule_based.json", "w", encoding="utf-8") as f:
                    json.dump(self.toc_entries, f, indent=2)

                logger.info("Rule-based TOC saved → toc_rule_based.json")

        except Exception:
            logger.exception("Rule-based TOC extraction failed")
            raise

    # -------------------------------------------------
    # STEP 3: Confidence scoring
    # -------------------------------------------------
    def score_confidence(self):

        logger.info("[STEP 3] Scoring TOC confidence...")

        try:
            scorer = TOCConfidenceScorer(self.toc_entries)
            result = scorer.run()

            level = result["level"]
            logger.info(f"Confidence Level: {level}")

            return level

        except Exception:
            logger.exception("TOC confidence scoring failed")
            return "LOW"

    # -------------------------------------------------
    # STEP 4: LLM fallback
    # -------------------------------------------------
    def llm_fallback(self):

        logger.info("[STEP 4] Running LLM fallback extractor...")

        try:
            extractor = LLMTOCExtractor(
                self.pdf_path,
                toc_start_page=self.toc_page
            )

            self.toc_entries = extractor.run()

            if SAVE_INTERMEDIATE:
                with open("toc_llm_fallback.json", "w", encoding="utf-8") as f:
                    json.dump(self.toc_entries, f, indent=2)

                logger.info("LLM TOC saved → toc_llm_fallback.json")

        except Exception:
            logger.exception("LLM fallback extraction failed")
            raise

    # -------------------------------------------------
    # STEP 5: OFFSET DETECTION
    # -------------------------------------------------
    def detect_offset(self):

        logger.info("[STEP 5] Detecting page offset...")

        if not self.toc_entries:
            logger.warning("Cannot compute offset — TOC empty")
            return

        try:
            finder = OffsetFinder(self.pdf_path, self.toc_entries)
            self.offset = finder.run()

            if self.offset is None:
                logger.warning("Offset detection failed")
            else:
                logger.info(f"Page Offset Detected: {self.offset}")

        except Exception:
            logger.exception("Offset detection failed")

    # -------------------------------------------------
    # SMART DECISION LOGIC
    # -------------------------------------------------
    def decide_extraction_strategy(self, confidence_level):

        try:
            if self.toc_type == "STRUCTURE_TOC":
                logger.info("STRUCTURE_TOC detected → using LLM extractor")
                self.llm_fallback()
                return

            if confidence_level != "HIGH":
                logger.info(
                    f"Confidence = {confidence_level} → switching to LLM fallback"
                )
                self.llm_fallback()
                return

            logger.info("Rule-based TOC accepted (HIGH confidence)")

        except Exception:
            logger.exception("Decision logic failed")
            raise

    # -------------------------------------------------
    # RUN FULL PIPELINE
    # -------------------------------------------------
    def run(self):

        logger.info("=" * 100)
        logger.info("SMART MEDIRAG — TOC ORCHESTRATOR STARTED")
        logger.info(f"PDF Path: {self.pdf_path}")
        logger.info("=" * 100)

        try:
            if not self.detect_toc():
                return None

            self.extract_rule_based()

            confidence_level = self.score_confidence()

            self.decide_extraction_strategy(confidence_level)

            self.detect_offset()

            logger.info("=" * 100)
            logger.info("FINAL ORCHESTRATOR OUTPUT")
            logger.info("=" * 100)

            logger.info(f"TOC Type  : {self.toc_type}")
            logger.info(f"TOC Page  : {self.toc_page + 1}")

            logger.info("[FINAL TOC STRUCTURE]")
            logger.info(pformat(self.toc_entries, width=130))

            final_output = {
                "toc_type": self.toc_type,
                "toc_page": self.toc_page + 1,
                "toc_page_index": self.toc_page,
                "toc_entries": self.toc_entries
            }

            with open("toc_final.json", "w", encoding="utf-8") as f:
                json.dump(final_output, f, indent=2)

            logger.info("Final output saved → toc_final.json")
            logger.info("=" * 100)
            logger.info("SMART MEDIRAG — TOC ORCHESTRATOR COMPLETED")
            logger.info("=" * 100)

            return final_output

        except Exception:
            logger.exception("TOC Orchestrator pipeline failed")
            raise


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 2:
        logger.warning("Usage: python orchestrator.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    try:
        orchestrator = TOCOrchestrator(pdf_path)
        orchestrator.run()
    except Exception:
        logger.exception("Standalone TOC execution crashed")


if __name__ == "__main__":
    main()
