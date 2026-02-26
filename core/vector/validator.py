"""
SmartChunk-RAG — Vector Chunk Validator

Responsibilities:
- Validate chunk structure before vector ingestion
- Enforce required metadata fields
- Check for duplicates
- Enforce minimum text length
- Respect fail-soft mode
- Config-driven validation

Config Sources:
- config/database.yaml → metadata_fields
- config/system.yaml → validation

Author: SmartChunk-RAG System
"""

from typing import List, Dict
from config.system_loader import (
    get_database_config,
    get_system_config
)


class VectorChunkValidator:

    def __init__(self):

        db_config = get_database_config()
        system_config = get_system_config()

        self.vector_cfg = db_config.get("vector_db", {})
        self.validation_cfg = system_config.get("validation", {})

        self.fail_soft = system_config["project"].get("fail_soft", True)

        # Required metadata fields from database.yaml
        self.required_fields = set(
            self.vector_cfg.get("metadata_fields", [])
        )

        # Chunk size rules
        chunk_cfg = system_config.get("chunking", {})
        size_cfg = chunk_cfg.get("size", {})

        self.min_chars = size_cfg.get("min_chars", 0)

    # -------------------------------------------------
    # Main Validation Entry
    # -------------------------------------------------

    def validate(self, chunks: List[Dict]) -> bool:

        print("=" * 70)
        print("[VECTOR VALIDATOR] Starting validation")
        print("=" * 70)

        if not chunks:
            print("[VECTOR VALIDATOR] No chunks provided")
            return False

        errors = []
        warnings = []

        seen_chunk_ids = set()

        for idx, chunk in enumerate(chunks):

            # -----------------------------------------
            # Check required metadata fields
            # -----------------------------------------
            missing = self.required_fields - set(chunk.keys())

            if missing:
                errors.append(
                    f"Chunk {idx} missing required fields: {missing}"
                )

            # -----------------------------------------
            # Check chunk_id uniqueness
            # -----------------------------------------
            chunk_id = chunk.get("chunk_id")

            if not chunk_id:
                errors.append(f"Chunk {idx} missing chunk_id")

            elif chunk_id in seen_chunk_ids:
                errors.append(f"Duplicate chunk_id detected: {chunk_id}")

            else:
                seen_chunk_ids.add(chunk_id)

            # -----------------------------------------
            # Check text field
            # -----------------------------------------
            text = chunk.get("text", "")

            if not text or not isinstance(text, str):
                errors.append(f"Chunk {idx} has invalid text")

            elif len(text) < self.min_chars:
                warnings.append(
                    f"Chunk {chunk_id} below min_chars ({self.min_chars})"
                )

            # -----------------------------------------
            # Optional metadata checks
            # -----------------------------------------
            if "page_physical" in chunk:
                if not isinstance(chunk["page_physical"], int):
                    warnings.append(
                        f"Chunk {chunk_id} page_physical not int"
                    )

        # -------------------------------------------------
        # Reporting
        # -------------------------------------------------

        if errors:
            print("\n[VECTOR VALIDATOR] ERRORS:")
            for e in errors:
                print(" -", e)

        if warnings:
            print("\n[VECTOR VALIDATOR] WARNINGS:")
            for w in warnings:
                print(" -", w)

        if errors and not self.fail_soft:
            print("\n[VECTOR VALIDATOR] Validation failed (strict mode)")
            return False

        print("\n[VECTOR VALIDATOR] Validation completed")
        print("=" * 70)

        return True