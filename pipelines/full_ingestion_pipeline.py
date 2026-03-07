"""
SMART MEDIRAG - FULL INGESTION PIPELINE
"""

from concurrent.futures import ThreadPoolExecutor

from core.toc.orchestrator import TOCOrchestrator
from core.chunking.orchestrator import ChunkOrchestrator
from core.utils.text_cleaner import TextCleaner
from core.vector.orchestrator import VectorOrchestrator
from core.graph.orchestrator import GraphOrchestrator
from config.system_loader import get_system_config
from core.utils.logging_utils import get_component_logger


logger = get_component_logger("FullIngestionPipeline", component="ingestion")


class FullIngestionPipeline:
    def __init__(
        self,
        pdf_path: str,
        owner_user_id: str | None = None,
        scope: str = "global",
    ):
        logger.info("\n" + "=" * 100)
        logger.info("SMART MEDIRAG - FULL INGESTION PIPELINE")
        logger.info("=" * 100)

        self.pdf_path = pdf_path
        self.owner_user_id = (owner_user_id or "").strip() or None
        self.scope = (scope or "global").strip().lower()

        try:
            self.cleaner = TextCleaner()
            self.vector_orch = VectorOrchestrator(
                self.pdf_path,
                owner_user_id=self.owner_user_id,
                scope=self.scope,
            )
            self.doc_id = self.vector_orch.document_id
            self.graph_orch = GraphOrchestrator(
                self.vector_orch.document_id,
                owner_user_id=self.owner_user_id,
            )
            self.config = get_system_config()
        except Exception:
            logger.exception("Pipeline initialization failed")
            raise

    def process_structure(self):
        logger.info("[PIPELINE] STEP 1 - TOC + STRUCTURE")
        try:
            toc_orch = TOCOrchestrator(self.pdf_path)
            toc_data = toc_orch.run()

            if not toc_data:
                logger.warning("No TOC found - fallback chunking")

            return toc_data
        except Exception:
            logger.exception("TOC processing failed")
            raise

    def chunk_document(self, toc_data):
        logger.info("[PIPELINE] STEP 2 - SMART CHUNKING")
        try:
            chunk_orch = ChunkOrchestrator(pdf_path=self.pdf_path, toc_data=toc_data)
            chunks = chunk_orch.run()
            logger.info("Generated %d chunks", len(chunks))
            return chunks
        except Exception:
            logger.exception("Chunking failed")
            raise

    def clean_chunks(self, chunks):
        logger.info("[PIPELINE] STEP 3 - CLEANING")
        try:
            workers = min(8, max(1, len(chunks)))

            def _clean(chunk):
                chunk["text"] = self.cleaner.clean(chunk.get("text", ""))
                return chunk

            if workers == 1:
                for chunk in chunks:
                    _clean(chunk)
            else:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    chunks = list(executor.map(_clean, chunks))
            return chunks
        except Exception:
            logger.exception("Chunk cleaning failed")
            raise

    def store_vector(self, chunks):
        logger.info("[PIPELINE] STEP 4 - VECTOR STORAGE")
        try:
            # VectorOrchestrator already handles internal batching.
            self.vector_orch.ingest(chunks=chunks)
        except Exception:
            logger.exception("Vector storage failed")
            raise

    def store_graph(self, chunks):
        logger.info("[PIPELINE] STEP 5 - GRAPH STORAGE")
        try:
            chunk_payloads = []
            for chunk in chunks:
                chunk_payloads.append(
                    {
                        "doc_id": self.doc_id,
                        "chapter": chunk.get("chapter"),
                        "subheading": chunk.get("subheading"),
                        "page_type": chunk.get("page_type"),
                        "chunk_id": chunk["chunk_id"],
                        "text": chunk["text"],
                        "page_label": chunk.get("page_label"),
                        "page_physical": chunk.get("page_physical"),
                    }
                )

            # GraphOrchestrator already handles internal batching.
            self.graph_orch.ingest_chunks(chunk_payloads)
        except Exception:
            logger.exception("Graph storage failed")
            raise

    def run(self):
        try:
            toc_data = self.process_structure()
            chunks = self.chunk_document(toc_data)

            if not chunks:
                logger.warning("No chunks generated - stopping pipeline")
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


def main():
    import sys

    if len(sys.argv) < 2:
        logger.warning("Usage: python -m pipelines.full_ingestion_pipeline <pdf_path>")
        return

    pdf_path = sys.argv[1]

    try:
        pipeline = FullIngestionPipeline(pdf_path)
        pipeline.run()
    except Exception:
        logger.exception("Pipeline execution crashed")


if __name__ == "__main__":
    main()
