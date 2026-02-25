"""
SMART MEDIRAG — TOC ORCHESTRATOR (PRODUCTION VERSION)

Handles:
- TOC detection
- Rule-based extraction
- Confidence scoring
- Intelligent LLM fallback
- Final structured output

LLM will be triggered if:
    1. TOC type = STRUCTURE_TOC
    OR
    2. Confidence != HIGH
"""

import sys
import json
from pprint import pprint

from core.toc.detector import TOCDetector
from core.toc.extractor_rule_based import RuleBasedTOCExtractor
from core.toc.extractor_llm_fallback import LLMTOCExtractor
from core.toc.confidence import TOCConfidenceScorer


SAVE_INTERMEDIATE = True


class TOCOrchestrator:

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.toc_page = None
        self.toc_type = None
        self.toc_entries = []

    # -------------------------------------------------
    # STEP 1: Detect TOC
    # -------------------------------------------------
    def detect_toc(self):

        print("\n[ORCH] STEP 1 — Detecting TOC...")

        detector = TOCDetector(self.pdf_path)
        detector.load_pdf()
        detector.detect_toc()
        results = detector.get_result()

        if not results:
            print("[ORCH] ❌ No TOC detected")
            return False

        # Use first detected TOC
        self.toc_page = results[0]["page_index"]
        self.toc_type = results[0]["toc_type"]

        print(
            f"[ORCH] ✅ TOC detected | "
            f"Page={self.toc_page + 1} | Type={self.toc_type}"
        )

        return True

    # -------------------------------------------------
    # STEP 2: Rule-based extraction
    # -------------------------------------------------
    def extract_rule_based(self):

        print("\n[ORCH] STEP 2 — Rule-based TOC extraction...")

        extractor = RuleBasedTOCExtractor(
            self.pdf_path,
            toc_start_page=self.toc_page
        )

        self.toc_entries = extractor.run()

        if SAVE_INTERMEDIATE:
            with open("toc_rule_based.json", "w", encoding="utf-8") as f:
                json.dump(self.toc_entries, f, indent=2)

            print("[ORCH] Rule-based TOC saved → toc_rule_based.json")

    # -------------------------------------------------
    # STEP 3: Confidence scoring
    # -------------------------------------------------
    def score_confidence(self):

        print("\n[ORCH] STEP 3 — Scoring TOC confidence...")

        scorer = TOCConfidenceScorer(self.toc_entries)
        result = scorer.run()

        level = result["level"]
        print(f"[ORCH] Confidence Level: {level}")

        return level

    # -------------------------------------------------
    # STEP 4: LLM fallback
    # -------------------------------------------------
    def llm_fallback(self):

        print("\n[ORCH] STEP 4 — Running LLM fallback extractor...")

        extractor = LLMTOCExtractor(
            self.pdf_path,
            toc_start_page=self.toc_page
        )

        self.toc_entries = extractor.run()

        if SAVE_INTERMEDIATE:
            with open("toc_llm_fallback.json", "w", encoding="utf-8") as f:
                json.dump(self.toc_entries, f, indent=2)

            print("[ORCH] LLM TOC saved → toc_llm_fallback.json")

    # -------------------------------------------------
    # SMART DECISION LOGIC
    # -------------------------------------------------
    def decide_extraction_strategy(self, confidence_level):

        # If STRUCTURE_TOC → always use LLM
        if self.toc_type == "STRUCTURE_TOC":
            print("[ORCH] STRUCTURE_TOC detected → using LLM extractor")
            self.llm_fallback()
            return

        # If confidence not HIGH → use LLM
        if confidence_level != "HIGH":
            print(
                f"[ORCH] Confidence = {confidence_level} "
                f"→ switching to LLM fallback"
            )
            self.llm_fallback()
            return

        print("[ORCH] ✅ Rule-based TOC accepted (HIGH confidence)")

    # -------------------------------------------------
    # RUN FULL PIPELINE
    # -------------------------------------------------
    def run(self):

        print("=" * 100)
        print("SMART MEDIRAG — TOC ORCHESTRATOR STARTED")
        print(f"PDF Path: {self.pdf_path}")
        print("=" * 100)

        # Step 1: Detect TOC
        if not self.detect_toc():
            return None

        # Step 2: Rule-based extraction
        self.extract_rule_based()

        # Step 3: Confidence scoring
        confidence_level = self.score_confidence()

        # Step 4: Smart decision
        self.decide_extraction_strategy(confidence_level)

        # Final Output
        print("\n" + "=" * 100)
        print("FINAL ORCHESTRATOR OUTPUT")
        print("=" * 100)

        print(f"TOC Type  : {self.toc_type}")
        print(f"TOC Page  : {self.toc_page + 1}")

        print("\n[FINAL TOC STRUCTURE]")
        pprint(self.toc_entries, width=130)

        final_output = {
            "toc_type": self.toc_type,
            "toc_page": self.toc_page + 1,
            "toc_page_index": self.toc_page,
            "toc_entries": self.toc_entries
        }

        with open("toc_final.json", "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2)

        print("\n[ORCH] Final output saved → toc_final.json")
        print("=" * 100)
        print("SMART MEDIRAG — TOC ORCHESTRATOR COMPLETED")
        print("=" * 100)

        return final_output


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python orchestrator.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    orchestrator = TOCOrchestrator(pdf_path)
    orchestrator.run()


if __name__ == "__main__":
    main()