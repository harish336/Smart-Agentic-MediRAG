"""
Pipeline Validator (Standalone)

Purpose:
- Validate intermediate pipeline outputs
- Catch silent failures early
- Decide whether fallback / retry is required
- Fully verbose and explainable

This file CAN be run independently.
"""

import sys
import json
from pprint import pprint


class PipelineValidator:
    def __init__(self, data, stage: str):
        """
        stage:
          - toc
          - style
          - accumulator
          - overlapper
        """
        self.data = data
        self.stage = stage.lower()
        self.errors = []
        self.warnings = []

    # -------------------------------------------------
    # ENTRY
    # -------------------------------------------------
    def run(self):
        print(f"\n[VALIDATOR] Running validation for stage: {self.stage.upper()}")

        if self.stage == "toc":
            self.validate_toc()
        elif self.stage == "style":
            self.validate_style()
        elif self.stage == "accumulator":
            self.validate_accumulator()
        elif self.stage == "overlapper":
            self.validate_overlapper()
        else:
            self.errors.append(f"Unknown stage: {self.stage}")

        return self.report()

    # -------------------------------------------------
    # TOC VALIDATION
    # -------------------------------------------------
    def validate_toc(self):
        if not isinstance(self.data, list):
            self.errors.append("TOC output must be a list")
            return

        if len(self.data) < 5:
            self.errors.append("TOC contains too few entries")

        for idx, entry in enumerate(self.data):
            if "title" not in entry:
                self.errors.append(f"Entry {idx} missing title")

            if "level" not in entry:
                self.warnings.append(f"Entry {idx} missing level")

            if "page_label" not in entry:
                self.warnings.append(f"Entry {idx} missing page_label")

    # -------------------------------------------------
    # STYLE VALIDATION
    # -------------------------------------------------
    def validate_style(self):
        if not isinstance(self.data, list):
            self.errors.append("Style output must be a list")
            return

        required = {"type", "text", "page"}

        for idx, unit in enumerate(self.data):
            missing = required - unit.keys()
            if missing:
                self.errors.append(f"Unit {idx} missing keys: {missing}")

            if len(unit.get("text", "")) < 3:
                self.warnings.append(f"Unit {idx} text too short")

    # -------------------------------------------------
    # ACCUMULATOR VALIDATION
    # -------------------------------------------------
    def validate_accumulator(self):
        if not isinstance(self.data, list):
            self.errors.append("Accumulator output must be a list")
            return

        for idx, chunk in enumerate(self.data):
            if "text" not in chunk:
                self.errors.append(f"Chunk {idx} missing text")

            if len(chunk.get("text", "")) < 200:
                self.warnings.append(f"Chunk {idx} is very small")

            if "page" not in chunk:
                self.errors.append(f"Chunk {idx} missing page number")

    # -------------------------------------------------
    # OVERLAPPER VALIDATION
    # -------------------------------------------------
    def validate_overlapper(self):
        if not isinstance(self.data, list):
            self.errors.append("Overlap output must be a list")
            return

        for idx, chunk in enumerate(self.data):
            if "overlap" not in chunk:
                self.warnings.append(f"Chunk {idx} missing overlap metadata")

            if len(chunk.get("text", "")) < 300:
                self.warnings.append(f"Chunk {idx} overlap too small")

    # -------------------------------------------------
    # FINAL REPORT
    # -------------------------------------------------
    def report(self):
        print("\n[VALIDATION REPORT]")

        if self.errors:
            print("\n❌ ERRORS:")
            for e in self.errors:
                print(" -", e)

        if self.warnings:
            print("\n⚠️ WARNINGS:")
            for w in self.warnings:
                print(" -", w)

        if not self.errors and not self.warnings:
            print("✅ Validation passed with no issues")

        status = "PASS" if not self.errors else "FAIL"

        print(f"\n[FINAL STATUS] {status}")
        return {
            "status": status,
            "errors": self.errors,
            "warnings": self.warnings
        }


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python validator.py <stage> <json_file>")
        print("\nStages:")
        print("  toc | style | accumulator | overlapper")
        sys.exit(1)

    stage = sys.argv[1]
    json_file = sys.argv[2]

    print("=" * 100)
    print("PIPELINE VALIDATOR STARTED")
    print(f"Stage     : {stage}")
    print(f"Input file: {json_file}")
    print("=" * 100)

    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load JSON: {e}")
        sys.exit(1)

    validator = PipelineValidator(data, stage)
    result = validator.run()

    print("\n[VALIDATION RESULT]")
    pprint(result)

    print("=" * 100)
    print("PIPELINE VALIDATOR COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
