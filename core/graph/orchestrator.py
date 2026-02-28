"""
Smart Medirag — Optimized Graph Orchestrator
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.graph.store import GraphStore
from core.graph.validator import GraphValidator
from core.graph.emotion_extractor import EmotionExtractor
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("GraphOrchestrator", component="ingestion")


class GraphOrchestrator:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self, document_id: str, max_workers: int = 8, batch_size: int = 500):

        logger.info("\n" + "=" * 80)
        logger.info("SMART MEDIRAG — GRAPH ORCHESTRATOR (OPTIMIZED)")
        logger.info("=" * 80)

        try:
            self.document_id = document_id
            self.max_workers = max_workers
            self.batch_size = batch_size

            self.store = GraphStore()
            self.validator = GraphValidator(self.store)
            self.emotion_extractor = EmotionExtractor()

            logger.info(f"Document ID: {self.document_id}")
            logger.info(f"Emotion Workers: {self.max_workers}")
            logger.info(f"Batch Size: {self.batch_size}")
            logger.info("GraphOrchestrator Ready\n")

        except Exception:
            logger.exception("GraphOrchestrator initialization failed")
            raise

    # =====================================================
    # PARALLEL EMOTION EXTRACTION
    # =====================================================

    def _extract_emotions_parallel(self, chunks: list) -> list:

        logger.info("[STEP 1] Extracting emotions in parallel...")

        def process(chunk):
            try:
                emotion = self.emotion_extractor.extract(chunk["text"])
            except Exception:
                logger.exception("Emotion extraction failed for a chunk")
                emotion = "Neutral"

            chunk["emotion"] = emotion
            return chunk

        enriched_chunks = []

        try:
            if len(chunks) < 2:
                for chunk in chunks:
                    enriched_chunks.append(process(chunk))
                logger.info("[STEP 1] Emotion extraction completed\n")
                return enriched_chunks

            workers = min(self.max_workers, len(chunks))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(process, chunk) for chunk in chunks]

                for future in as_completed(futures):
                    enriched_chunks.append(future.result())

            logger.info("[STEP 1] Emotion extraction completed\n")
            return enriched_chunks

        except Exception:
            logger.exception("Parallel emotion extraction failed")
            return chunks  # fail-soft behavior

    # =====================================================
    # MAIN INGESTION
    # =====================================================

    def ingest_chunks(self, chunks: list):

        if not chunks:
            logger.warning("No chunks provided to GraphOrchestrator")
            return

        start_time = time.time()

        logger.info(f"Received {len(chunks)} chunks\n")

        # -----------------------------------------
        # STEP 1 — Parallel Emotion Extraction
        # -----------------------------------------

        chunks = self._extract_emotions_parallel(chunks)

        # -----------------------------------------
        # STEP 2 — Validate Chunks
        # -----------------------------------------

        logger.info("[STEP 2] Validating chunks...")

        try:
            doc_exists = self.store.document_exists(self.document_id)
            valid_chunks = self.validator.validate_chunks(
                chunks,
                doc_exists=doc_exists,
                log=True
            )

            logger.info(f"[STEP 2] {len(valid_chunks)} valid chunks\n")

        except Exception:
            logger.exception("Chunk validation failed")
            return

        if not valid_chunks:
            logger.warning("No valid chunks after validation")
            return

        # -----------------------------------------
        # STEP 3 — Batch Ingest into Graph
        # -----------------------------------------

        logger.info("[STEP 3] Batch ingesting into Neo4j...")

        try:
            if self.batch_size and len(valid_chunks) > self.batch_size:
                for i in range(0, len(valid_chunks), self.batch_size):
                    batch = valid_chunks[i:i + self.batch_size]
                    self.store.batch_ingest(
                        doc_id=self.document_id,
                        chunks=batch
                    )
            else:
                self.store.batch_ingest(
                    doc_id=self.document_id,
                    chunks=valid_chunks
                )

            logger.info("[STEP 3] Batch ingestion completed\n")

        except Exception:
            logger.exception("Graph batch ingestion failed")
            return

        # -----------------------------------------
        # STEP 4 — Batch Sequential Linking
        # -----------------------------------------

        logger.info("[STEP 4] Linking sequential chunks...")

        links = []

        try:
            for i in range(1, len(valid_chunks)):
                prev_id = valid_chunks[i - 1]["chunk_id"]
                curr_id = valid_chunks[i]["chunk_id"]
                if prev_id != curr_id:
                    links.append((prev_id, curr_id))

            if links:
                self.store.batch_link(links)
                logger.info(f"[STEP 4] {len(links)} sequential links created\n")
            else:
                logger.info("[STEP 4] No valid links to create\n")

        except Exception:
            logger.exception("Sequential linking failed")

        total_time = round(time.time() - start_time, 2)

        logger.info("=" * 80)
        logger.info(f"GRAPH INGESTION COMPLETED in {total_time} seconds")
        logger.info("=" * 80 + "\n")

    # =====================================================
    # CLOSE
    # =====================================================

    def close(self):
        try:
            self.store.close()
        except Exception:
            logger.exception("Failed closing GraphStore connection")
