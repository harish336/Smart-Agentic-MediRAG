"""
Smart Medirag — Chunking Orchestrator

Connects:
- Style detection
- Accumulation
- Overlap
- Validation
"""

import uuid
from core.chunking.style_detector import StyleDetector
from core.chunking.accumulator import TextAccumulator
from core.chunking.overlapper import ChunkOverlapper
from core.chunking.validator import PipelineValidator
from config.system_loader import get_system_config


class ChunkOrchestrator:

    def __init__(self, pdf_path, toc_data=None):

        self.pdf_path = pdf_path
        self.toc_data = toc_data

        self.style_detector = StyleDetector(pdf_path)
        self.accumulator = TextAccumulator()
        self.overlapper = ChunkOverlapper()
        self.validator = PipelineValidator()

        self.config = get_system_config()

        print("\n[CHUNK ORCH] Initialized")

    # =====================================================
    # MAIN RUN
    # =====================================================

    def run(self):

        print("\n" + "=" * 70)
        print("SMART MEDIRAG — CHUNKING STARTED")
        print("=" * 70)

        # -----------------------------------------
        # STEP 1 — Detect styles
        # -----------------------------------------

        styled_blocks = self.style_detector.run()

        print(f"[CHUNK ORCH] Styled blocks: {len(styled_blocks)}")

        # -----------------------------------------
        # STEP 2 — Accumulate hierarchical chunks
        # -----------------------------------------

        chunks = self.accumulator.run(styled_blocks)

        print(f"[CHUNK ORCH] Accumulated chunks: {len(chunks)}")

        # -----------------------------------------
        # STEP 3 — Apply overlap
        # -----------------------------------------

        if self.config["overlap"]["enabled"]:
            chunks = self.overlapper.apply(chunks)

        print(f"[CHUNK ORCH] After overlap: {len(chunks)}")

        # -----------------------------------------
        # STEP 4 — Validate chunks
        # -----------------------------------------

        valid_chunks = []

        for chunk in chunks:

            if self.validator.is_valid(chunk):
                chunk["chunk_id"] = str(uuid.uuid4())
                valid_chunks.append(chunk)

        print(f"[CHUNK ORCH] Valid chunks: {len(valid_chunks)}")

        print("=" * 70)
        print("SMART MEDIRAG — CHUNKING COMPLETED")
        print("=" * 70 + "\n")

        return valid_chunks