"""
Smart Medirag — Optimized Graph Orchestrator

Optimizations:
- Parallel emotion extraction (ThreadPool)
- Batch graph ingestion
- Batch sequential linking
- Minimal logging overhead
- Fail-soft compatible
- Fully idempotent
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.graph.store import GraphStore
from core.graph.validator import GraphValidator
from core.graph.emotion_extractor import EmotionExtractor


class GraphOrchestrator:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, document_id: str, max_workers: int = 8):

        print("\n" + "=" * 80)
        print("SMART MEDIRAG — GRAPH ORCHESTRATOR (OPTIMIZED)")
        print("=" * 80)

        self.document_id = document_id
        self.max_workers = max_workers

        self.store = GraphStore()
        self.validator = GraphValidator(self.store)
        self.emotion_extractor = EmotionExtractor()

        print(f"[GRAPH ORCH] Document ID: {self.document_id}")
        print(f"[GRAPH ORCH] Emotion Workers: {self.max_workers}")
        print("[GRAPH ORCH] Ready\n")

    # =====================================================
    # PARALLEL EMOTION EXTRACTION
    # =====================================================

    def _extract_emotions_parallel(self, chunks: list) -> list:

        print("[STEP 1] Extracting emotions in parallel...")

        def process(chunk):
            try:
                emotion = self.emotion_extractor.extract(chunk["text"])
            except Exception:
                emotion = "Neutral"
            chunk["emotion"] = emotion
            return chunk

        enriched_chunks = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(process, chunk) for chunk in chunks]

            for future in as_completed(futures):
                enriched_chunks.append(future.result())

        print("[STEP 1] Emotion extraction completed\n")
        return enriched_chunks

    # =====================================================
    # MAIN INGESTION
    # =====================================================

    def ingest_chunks(self, chunks: list):

        if not chunks:
            print("[GRAPH ORCH] No chunks provided")
            return

        start_time = time.time()

        print(f"[GRAPH ORCH] Received {len(chunks)} chunks\n")

        # -----------------------------------------
        # STEP 1 — Parallel Emotion Extraction
        # -----------------------------------------

        chunks = self._extract_emotions_parallel(chunks)

        # -----------------------------------------
        # STEP 2 — Validate Chunks
        # -----------------------------------------

        print("[STEP 2] Validating chunks...")

        valid_chunks = []

        for chunk in chunks:
            validation = self.validator.validate_chunk(chunk)

            if validation["valid"]:
                valid_chunks.append(chunk)

        print(f"[STEP 2] {len(valid_chunks)} valid chunks\n")

        if not valid_chunks:
            print("[GRAPH ORCH] No valid chunks after validation")
            return

        # -----------------------------------------
        # STEP 3 — Batch Ingest into Graph
        # -----------------------------------------

        print("[STEP 3] Batch ingesting into Neo4j...")

        try:
            self.store.batch_ingest(
                doc_id=self.document_id,
                chunks=valid_chunks
            )
        except Exception as e:
            print(f"[GRAPH BATCH INGEST ERROR] {e}")
            return

        print("[STEP 3] Batch ingestion completed\n")

        # -----------------------------------------
        # STEP 4 — Batch Sequential Linking
        # -----------------------------------------

        print("[STEP 4] Linking sequential chunks...")

        links = []

        for i in range(1, len(valid_chunks)):
            prev_id = valid_chunks[i - 1]["chunk_id"]
            curr_id = valid_chunks[i]["chunk_id"]

            seq_validation = self.validator.validate_sequence(prev_id, curr_id)

            if seq_validation["valid"]:
                links.append((prev_id, curr_id))

        if links:
            try:
                self.store.batch_link(links)
                print(f"[STEP 4] {len(links)} sequential links created\n")
            except Exception as e:
                print(f"[SEQUENCE LINK ERROR] {e}")
        else:
            print("[STEP 4] No valid links to create\n")

        total_time = round(time.time() - start_time, 2)

        print("=" * 80)
        print(f"GRAPH INGESTION COMPLETED in {total_time} seconds")
        print("=" * 80 + "\n")

    # =====================================================
    # CLOSE
    # =====================================================

    def close(self):
        self.store.close()