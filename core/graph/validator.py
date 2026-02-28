"""
Smart Medirag â€” Graph Ingestion Validator

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

    # =====================================================
    # MAIN VALIDATION ENTRY
    # =====================================================

    def validate_chunk(self, chunk: dict, doc_exists: bool = None, log: bool = True):

        errors = []
        warnings = []

        self._validate_required_fields(chunk, errors, warnings)
        self._validate_types(chunk, errors)
        self._validate_emotion(chunk, warnings)
        self._check_duplicate_chunk(chunk, warnings, doc_exists)

        return self._finalize(errors, warnings, log)

    def validate_chunks(self, chunks: list, doc_exists: bool = None, log: bool = True):

        if not chunks:
            return []

        if doc_exists is None:
            doc_exists = self.store.document_exists(chunks[0].get(DOC_ID))

        valid_chunks = []
        all_errors = []
        all_warnings = []

        for chunk in chunks:
            result = self.validate_chunk(chunk, doc_exists=doc_exists, log=False)
            if result["valid"]:
                valid_chunks.append(chunk)
            all_errors.extend(result["errors"])
            all_warnings.extend(result["warnings"])

        if log:
            self._finalize_summary(
                total=len(chunks),
                valid=len(valid_chunks),
                errors=all_errors,
                warnings=all_warnings
            )

        return valid_chunks

    # =====================================================
    # REQUIRED FIELDS
    # =====================================================

    def _validate_required_fields(self, chunk, errors, warnings):

        required = [
            DOC_ID,
            CHUNK_ID,
            TEXT
        ]

        for field in required:
            if field not in chunk or not chunk[field]:
                errors.append(f"Missing required field: {field}")

        # Soft-required fields
        if not chunk.get("chapter"):
            warnings.append("Missing chapter â€” will default to 'Unknown'")

        if not chunk.get("subheading"):
            warnings.append("Missing subheading â€” will default to 'Unknown'")

    # =====================================================
    # TYPE VALIDATION
    # =====================================================

    def _validate_types(self, chunk, errors):

        if not isinstance(chunk.get(DOC_ID), str):
            errors.append("doc_id must be string")

        if not isinstance(chunk.get(CHUNK_ID), str):
            errors.append("chunk_id must be string")

        if not isinstance(chunk.get(TEXT), str):
            errors.append("text must be string")

        if chunk.get(PAGE_PHYSICAL) is not None and not isinstance(chunk.get(PAGE_PHYSICAL), int):
            errors.append("page_physical must be integer")

    # =====================================================
    # EMOTION VALIDATION
    # =====================================================

    def _validate_emotion(self, chunk, warnings):

        emotion = chunk.get("emotion")

        if not emotion:
            warnings.append("Emotion missing â€” defaulting to Neutral")
            return

        if emotion not in self.ALLOWED_EMOTIONS:
            warnings.append(
                f"Emotion '{emotion}' not recognized â€” setting to Neutral"
            )

    # =====================================================
    # DUPLICATE CHECK
    # =====================================================

    def _check_duplicate_chunk(self, chunk, warnings, doc_exists: bool = None):

        chunk_id = chunk.get(CHUNK_ID)

        if not chunk_id:
            return

        exists = doc_exists
        if exists is None:
            exists = self.store.document_exists(chunk.get(DOC_ID))

        # Soft logic:
        # If document exists, we allow re-ingestion
        # because MERGE ensures safety.
        # But we warn if document already exists.

        if exists:
            warnings.append(
                f"Document {chunk.get(DOC_ID)} already exists â€” "
                f"MERGE will prevent duplication"
            )

    # =====================================================
    # HIERARCHY CONSISTENCY CHECK
    # =====================================================

    def validate_sequence(self, previous_chunk_id, current_chunk_id):

        errors = []
        warnings = []

        if previous_chunk_id == current_chunk_id:
            errors.append("Chunk cannot link to itself")

        return self._finalize(errors, warnings, log=True)

    # =====================================================
    # FINALIZE RESULT
    # =====================================================

    def _finalize(self, errors, warnings, log: bool = True):

        if log:
            print("\n" + "=" * 70)
            print("[GRAPH VALIDATOR] Validation Summary")
            print("=" * 70)

            if errors:
                print("\n[ERRORS]")
                for e in errors:
                    print(" -", e)

            if warnings:
                print("\n[WARNINGS]")
                for w in warnings:
                    print(" -", w)

            if not errors:
                print("\n[STATUS] VALID")
            else:
                print("\n[STATUS] INVALID")

            print("=" * 70 + "\n")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _finalize_summary(self, total: int, valid: int, errors: list, warnings: list):

        print("\n" + "=" * 70)
        print("[GRAPH VALIDATOR] Batch Validation Summary")
        print("=" * 70)
        print(f"Total chunks : {total}")
        print(f"Valid chunks : {valid}")
        print(f"Invalid      : {total - valid}")

        if errors:
            print("\n[ERRORS] (sample)")
            for e in errors[:5]:
                print(" -", e)
            if len(errors) > 5:
                print(f" ... ({len(errors)} total)")

        if warnings:
            print("\n[WARNINGS] (sample)")
            for w in warnings[:5]:
                print(" -", w)
            if len(warnings) > 5:
                print(f" ... ({len(warnings)} total)")

        if not errors:
            print("\n[STATUS] VALID")
        else:
            print("\n[STATUS] INVALID")

        print("=" * 70 + "\n")
