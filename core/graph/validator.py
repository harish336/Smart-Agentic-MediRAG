"""
Smart Medirag — Graph Ingestion Validator

Purpose:
- Validate chunk before graph insertion
- Prevent broken hierarchy
- Prevent duplicate ingestion
- Validate emotion safety
- Ensure relationship integrity
"""

from core.graph.schema import (
    DOC_ID,
    CHUNK_ID,
    NAME,
    TEXT,
    PAGE_LABEL,
    PAGE_PHYSICAL
)


class GraphValidator:

    ALLOWED_EMOTIONS = {
        "Neutral",
        "Informative",
        "Positive",
        "Negative",
        "Concern",
        "Warning"
    }

    def __init__(self, graph_store):
        self.store = graph_store
        self.errors = []
        self.warnings = []

    # =====================================================
    # MAIN VALIDATION ENTRY
    # =====================================================

    def validate_chunk(self, chunk: dict):

        self.errors = []
        self.warnings = []

        self._validate_required_fields(chunk)
        self._validate_types(chunk)
        self._validate_emotion(chunk)
        self._check_duplicate_chunk(chunk)

        return self._finalize()

    # =====================================================
    # REQUIRED FIELDS
    # =====================================================

    def _validate_required_fields(self, chunk):

        required = [
            DOC_ID,
            CHUNK_ID,
            TEXT
        ]

        for field in required:
            if field not in chunk or not chunk[field]:
                self.errors.append(f"Missing required field: {field}")

        # Soft-required fields
        if not chunk.get("chapter"):
            self.warnings.append("Missing chapter — will default to 'Unknown'")

        if not chunk.get("subheading"):
            self.warnings.append("Missing subheading — will default to 'Unknown'")

    # =====================================================
    # TYPE VALIDATION
    # =====================================================

    def _validate_types(self, chunk):

        if not isinstance(chunk.get(DOC_ID), str):
            self.errors.append("doc_id must be string")

        if not isinstance(chunk.get(CHUNK_ID), str):
            self.errors.append("chunk_id must be string")

        if not isinstance(chunk.get(TEXT), str):
            self.errors.append("text must be string")

        if chunk.get(PAGE_PHYSICAL) is not None and not isinstance(chunk.get(PAGE_PHYSICAL), int):
            self.errors.append("page_physical must be integer")

    # =====================================================
    # EMOTION VALIDATION
    # =====================================================

    def _validate_emotion(self, chunk):

        emotion = chunk.get("emotion")

        if not emotion:
            self.warnings.append("Emotion missing — defaulting to Neutral")
            return

        if emotion not in self.ALLOWED_EMOTIONS:
            self.warnings.append(
                f"Emotion '{emotion}' not recognized — setting to Neutral"
            )

    # =====================================================
    # DUPLICATE CHECK
    # =====================================================

    def _check_duplicate_chunk(self, chunk):

        chunk_id = chunk.get(CHUNK_ID)

        if not chunk_id:
            return

        exists = self.store.document_exists(chunk.get(DOC_ID))

        # Soft logic:
        # If document exists, we allow re-ingestion
        # because MERGE ensures safety.
        # But we warn if document already exists.

        if exists:
            self.warnings.append(
                f"Document {chunk.get(DOC_ID)} already exists — "
                f"MERGE will prevent duplication"
            )

    # =====================================================
    # HIERARCHY CONSISTENCY CHECK
    # =====================================================

    def validate_sequence(self, previous_chunk_id, current_chunk_id):

        if previous_chunk_id == current_chunk_id:
            self.errors.append("Chunk cannot link to itself")

        return self._finalize()

    # =====================================================
    # FINALIZE RESULT
    # =====================================================

    def _finalize(self):

        print("\n" + "=" * 70)
        print("[GRAPH VALIDATOR] Validation Summary")
        print("=" * 70)

        if self.errors:
            print("\n[ERRORS]")
            for e in self.errors:
                print(" -", e)

        if self.warnings:
            print("\n[WARNINGS]")
            for w in self.warnings:
                print(" -", w)

        if not self.errors:
            print("\n[STATUS] VALID")
        else:
            print("\n[STATUS] INVALID")

        print("=" * 70 + "\n")

        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings
        }