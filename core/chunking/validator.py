"""
Smart Medirag — Pipeline Validator

Purpose:
- Validate intermediate pipeline outputs
- Catch silent failures early
- Stateless and production-aligned
"""

import json
from pprint import pprint


class PipelineValidator:

    def __init__(self):
        print("[PIPELINE VALIDATOR] Initialized")

    # =====================================================
    # CHUNK-LEVEL SIMPLE VALIDATION (Used in Orchestrator)
    # =====================================================

    def is_valid(self, chunk: dict) -> bool:

        if not isinstance(chunk, dict):
            return False

        text = chunk.get("text")

        if not text:
            return False

        if not isinstance(text, str):
            return False

        if len(text.strip()) < 50:
            return False

        return True

    # =====================================================
    # STAGE-BASED VALIDATION (Optional Diagnostic Mode)
    # =====================================================

    def run(self, data, stage: str):

        self.data = data
        self.stage = stage
        self.errors = []
        self.warnings = []

        print(f"\n[VALIDATOR] Running validation for stage: {stage.upper()}")

        if stage == "toc":
            self._validate_toc()
        elif stage == "style":
            self._validate_style()
        elif stage == "accumulator":
            self._validate_accumulator()
        elif stage == "overlapper":
            self._validate_overlapper()
        else:
            self.errors.append(f"Unknown stage: {stage}")

        return self._report()

    # -------------------------------------------------
    # TOC VALIDATION
    # -------------------------------------------------

    def _validate_toc(self):
        if not isinstance(self.data, list):
            self.errors.append("TOC output must be a list")
            return

        if len(self.data) < 3:
            self.warnings.append("TOC contains very few entries")

        for idx, entry in enumerate(self.data):
            if "title" not in entry:
                self.errors.append(f"Entry {idx} missing title")

            if "level" not in entry:
                self.warnings.append(f"Entry {idx} missing level")

    # -------------------------------------------------
    # STYLE VALIDATION
    # -------------------------------------------------

    def _validate_style(self):
        if not isinstance(self.data, list):
            self.errors.append("Style output must be a list")
            return

        required = {"type", "text"}

        for idx, unit in enumerate(self.data):
            missing = required - unit.keys()
            if missing:
                self.errors.append(f"Unit {idx} missing keys: {missing}")

    # -------------------------------------------------
    # ACCUMULATOR VALIDATION
    # -------------------------------------------------

    def _validate_accumulator(self):
        if not isinstance(self.data, list):
            self.errors.append("Accumulator output must be a list")
            return

        for idx, chunk in enumerate(self.data):
            if "text" not in chunk:
                self.errors.append(f"Chunk {idx} missing text")

            if len(chunk.get("text", "")) < 100:
                self.warnings.append(f"Chunk {idx} is small")

    # -------------------------------------------------
    # OVERLAPPER VALIDATION
    # -------------------------------------------------

    def _validate_overlapper(self):
        if not isinstance(self.data, list):
            self.errors.append("Overlap output must be a list")
            return

        for idx, chunk in enumerate(self.data):
            if len(chunk.get("text", "")) < 150:
                self.warnings.append(f"Chunk {idx} overlap small")

    # -------------------------------------------------
    # REPORT
    # -------------------------------------------------

    def _report(self):

        print("\n[VALIDATION REPORT]")

        if self.errors:
            print("\n❌ ERRORS:")
            for e in self.errors:
                print(" -", e)

        if self.warnings:
            print("\n⚠ WARNINGS:")
            for w in self.warnings:
                print(" -", w)

        if not self.errors and not self.warnings:
            print("✅ Validation passed")

        status = "PASS" if not self.errors else "FAIL"

        print(f"\n[FINAL STATUS] {status}")

        return {
            "status": status,
            "errors": self.errors,
            "warnings": self.warnings
        }