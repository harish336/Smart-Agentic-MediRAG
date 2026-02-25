"""
TOC Confidence Scorer

Purpose:
- Score how reliable a TOC extraction is
- Decide whether LLM fallback is required
- Fully explainable and deterministic

This file CAN be run standalone.
"""

import sys
import json
from pprint import pprint


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
        """
        Scoring logic (tuned for textbook PDFs):

        - Each entry: +1
        - Chapter: +3
        - Section: +2
        - Subsection: +2
        - Page label present: +2
        - Unknown level: -1
        """

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
        """
        Thresholds:
        - >= 40 : HIGH confidence (rule-based OK)
        - 20–39 : MEDIUM confidence (optional LLM)
        - < 20  : LOW confidence (LLM fallback required)
        """

        if self.score >= 40:
            return "HIGH"
        if self.score >= 20:
            return "MEDIUM"
        return "LOW"

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        print("[STEP 1] Computing TOC metrics...")
        self.compute_metrics()
        pprint(self.breakdown)

        print("\n[STEP 2] Calculating confidence score...")
        self.calculate_score()
        print(f"[INFO] Confidence Score: {self.score}")

        print("\n[STEP 3] Final decision...")
        decision = self.decision()
        print(f"[RESULT] Confidence Level: {decision}")

        return {
            "score": self.score,
            "level": decision,
            "metrics": self.breakdown
        }


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python confidence.py <toc_json_file>")
        print("\nExample:")
        print("  python confidence.py toc_output.json")
        sys.exit(1)

    toc_file = sys.argv[1]

    print("=" * 90)
    print("TOC CONFIDENCE SCORER STARTED")
    print(f"Input TOC file: {toc_file}")
    print("=" * 90)

    try:
        with open(toc_file, "r", encoding="utf-8") as f:
            toc_entries = json.load(f)
    except UnicodeDecodeError:
        print("[WARN] UTF-8 decode failed, trying UTF-16...")
        with open(toc_file, "r", encoding="utf-16") as f:
            toc_entries = json.load(f)


    scorer = TOCConfidenceScorer(toc_entries)
    result = scorer.run()

    print("\n[FINAL CONFIDENCE RESULT]")
    pprint(result)

    print("=" * 90)
    print("TOC CONFIDENCE SCORER COMPLETED")
    print("=" * 90)


if __name__ == "__main__":
    main()