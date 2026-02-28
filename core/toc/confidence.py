"""
TOC Confidence Scorer
"""

import sys
import json
from pprint import pformat

from core.utils.logging_utils import get_component_logger

# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("TOCConfidenceScorer", component="ingestion")


class TOCConfidenceScorer:

    def __init__(self, toc_entries: list):
        self.toc_entries = toc_entries
        self.score = 0
        self.breakdown = {}

    # -------------------------------------------------
    # STEP 1: Count metrics
    # -------------------------------------------------
    def compute_metrics(self):

        chapters = 0
        sections = 0
        subsections = 0
        page_labels = 0
        unknowns = 0

        for e in self.toc_entries:
            level = e.get("level", "unknown")
            page = e.get("page_label")

            if level == "chapter":
                chapters += 1
            elif level == "section":
                sections += 1
            elif level == "subsection":
                subsections += 1
            else:
                unknowns += 1

            if page:
                page_labels += 1

        self.breakdown = {
            "total_entries": len(self.toc_entries),
            "chapters": chapters,
            "sections": sections,
            "subsections": subsections,
            "unknowns": unknowns,
            "page_labels": page_labels,
        }

    # -------------------------------------------------
    # STEP 2: Score calculation
    # -------------------------------------------------
    def calculate_score(self):

        score = 0

        for e in self.toc_entries:
            score += 1

            level = e.get("level", "unknown")
            if level == "chapter":
                score += 3
            elif level == "section":
                score += 2
            elif level == "subsection":
                score += 2
            else:
                score -= 1

            if e.get("page_label"):
                score += 2

        self.score = max(score, 0)

    # -------------------------------------------------
    # STEP 3: Decision
    # -------------------------------------------------
    def decision(self):

        if self.score >= 40:
            return "HIGH"
        if self.score >= 20:
            return "MEDIUM"
        return "LOW"

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):

        try:
            logger.info("[STEP 1] Computing TOC metrics...")
            self.compute_metrics()
            logger.info(pformat(self.breakdown))

            logger.info("[STEP 2] Calculating confidence score...")
            self.calculate_score()
            logger.info(f"Confidence Score: {self.score}")

            logger.info("[STEP 3] Final decision...")
            decision = self.decision()
            logger.info(f"Confidence Level: {decision}")

            return {
                "score": self.score,
                "level": decision,
                "metrics": self.breakdown
            }

        except Exception:
            logger.exception("TOC confidence scoring failed")
            raise


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():

    if len(sys.argv) < 2:
        logger.warning("Usage: python confidence.py <toc_json_file>")
        sys.exit(1)

    toc_file = sys.argv[1]

    logger.info("=" * 90)
    logger.info("TOC CONFIDENCE SCORER STARTED")
    logger.info(f"Input TOC file: {toc_file}")
    logger.info("=" * 90)

    try:
        try:
            with open(toc_file, "r", encoding="utf-8") as f:
                toc_entries = json.load(f)
        except UnicodeDecodeError:
            logger.warning("UTF-8 decode failed, trying UTF-16...")
            with open(toc_file, "r", encoding="utf-16") as f:
                toc_entries = json.load(f)

        scorer = TOCConfidenceScorer(toc_entries)
        result = scorer.run()

        logger.info("[FINAL CONFIDENCE RESULT]")
        logger.info(pformat(result))

        logger.info("=" * 90)
        logger.info("TOC CONFIDENCE SCORER COMPLETED")
        logger.info("=" * 90)

    except Exception:
        logger.exception("Standalone confidence scorer crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
