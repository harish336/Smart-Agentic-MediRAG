"""
SMART MEDIRAG — FULL INGESTION PIPELINE
"""

import uuid

# -------------------------------
# CORE MODULES
# -------------------------------

from core.toc.orchestrator import TOCOrchestrator
from core.chunking.orchestrator import ChunkOrchestrator
from core.utils.text_cleaner import TextCleaner

from core.vector.orchestrator import VectorOrchestrator
from core.graph.orchestrator import GraphOrchestrator

from config.system_loader import get_system_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("FullIngestionPipeline", component="ingestion")


# =====================================================
# MASTER INGESTION CLASS
# =====================================================

class FullIngestionPipeline:

    def __init__(self, pdf_path: str):

        logger.info("\n" + "=" * 100)
        logger.info("SMART MEDIRAG — FULL INGESTION PIPELINE")
        logger.info("=" * 100)

        self.pdf_path = pdf_path
        self.doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        try:
            self.cleaner = TextCleaner()
            self.vector_orch = VectorOrchestrator(self.pdf_path)
            self.graph_orch = GraphOrchestrator(self.vector_orch.document_id)
            self.config = get_system_config()
        except Exception:
            logger.exception("Pipeline initialization failed")
            raise

    # =====================================================
    # STEP 1 — TOC + OFFSET
    # =====================================================

    def process_structure(self):

        logger.info("[PIPELINE] STEP 1 — TOC + STRUCTURE")

        try:
            toc_orch = TOCOrchestrator(self.pdf_path)
            toc_data = toc_orch.run()

            if not toc_data:
                logger.warning("No TOC found — fallback chunking")

            return toc_data

        except Exception:
            logger.exception("TOC processing failed")
            raise

    # =====================================================
    # STEP 2 — SMART CHUNKING
    # =====================================================

    def chunk_document(self, toc_data):

        logger.info("[PIPELINE] STEP 2 — SMART CHUNKING")

        try:
            chunk_orch = ChunkOrchestrator(
                pdf_path=self.pdf_path,
                toc_data=toc_data
            )

            chunks = chunk_orch.run()

            logger.info(f"Generated {len(chunks)} chunks")

            return chunks

        except Exception:
            logger.exception("Chunking failed")
            raise

    # =====================================================
    # STEP 3 — CLEAN CHUNKS
    # =====================================================

    def clean_chunks(self, chunks):

        logger.info("[PIPELINE] STEP 3 — CLEANING")

        try:
            for chunk in chunks:
                chunk["text"] = self.cleaner.clean(chunk["text"])

            return chunks

        except Exception:
            logger.exception("Chunk cleaning failed")
            raise

    # =====================================================
    # STEP 4 — VECTOR STORE
    # =====================================================

    def store_vector(self, chunks):

        logger.info("[PIPELINE] STEP 4 — VECTOR STORAGE")

        try:
            self.vector_orch.ingest(
                chunks=chunks
            )
        except Exception:
            logger.exception("Vector storage failed")
            raise

    # =====================================================
    # STEP 5 — GRAPH STORE
    # =====================================================

    def store_graph(self, chunks):

        logger.info("[PIPELINE] STEP 5 — GRAPH STORAGE")

        try:
            for chunk in chunks:

                chunk_payload = {
                    "doc_id": self.doc_id,
                    "chapter": chunk.get("chapter"),
                    "subheading": chunk.get("subheading"),
                    "chunk_id": chunk["chunk_id"],
                    "text": chunk["text"],
                    "page_label": chunk.get("page_label"),
                    "page_physical": chunk.get("page_physical")
                }

                self.graph_orch.ingest_chunks([chunk_payload])

        except Exception:
            logger.exception("Graph storage failed")
            raise

    # =====================================================
    # RUN PIPELINE
    # =====================================================

    def run(self):

        try:
            toc_data = self.process_structure()

            chunks = self.chunk_document(toc_data)

            if not chunks:
                logger.warning("No chunks generated — stopping pipeline")
                return

            for chunk in chunks:
                chunk["doc_id"] = self.doc_id

            chunks = self.clean_chunks(chunks)

            self.store_vector(chunks)

            self.store_graph(chunks)

            logger.info("\n" + "=" * 100)
            logger.info("FULL INGESTION COMPLETED SUCCESSFULLY")
            logger.info("=" * 100)

        except Exception:
            logger.exception("Full ingestion pipeline failed")
            raise

        finally:
            try:
                self.graph_orch.close()
            except Exception:
                logger.exception("Failed closing graph connection")


# =====================================================
# RUNNER
# =====================================================

def main():

    import sys

    if len(sys.argv) < 2:
        logger.warning(
            "Usage: python -m pipelines.full_ingestion_pipeline <pdf_path>"
        )
        return

    pdf_path = sys.argv[1]

    try:
        pipeline = FullIngestionPipeline(pdf_path)
        pipeline.run()
    except Exception:
        logger.exception("Pipeline execution crashed")


if __name__ == "__main__":
    main()
