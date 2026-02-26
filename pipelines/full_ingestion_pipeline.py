"""
SMART MEDIRAG — FULL INGESTION PIPELINE

Runs complete flow:
PDF → TOC → Offset → Style → Chunk → Clean →
Validate → Embed → Vector Store → Emotion →
Graph Store
"""

import uuid
from pprint import pprint

# -------------------------------
# CORE MODULES
# -------------------------------

from core.toc.orchestrator import TOCOrchestrator
from core.chunking.orchestrator import ChunkOrchestrator  # assume exists
from core.utils.text_cleaner import TextCleaner

from core.vector.orchestrator import VectorOrchestrator
from core.graph.orchestrator import GraphOrchestrator

from config.system_loader import get_system_config


# =====================================================
# MASTER INGESTION CLASS
# =====================================================

class FullIngestionPipeline:

    def __init__(self, pdf_path: str):

        print("\n" + "=" * 100)
        print("SMART MEDIRAG — FULL INGESTION PIPELINE")
        print("=" * 100)

        self.pdf_path = pdf_path
        self.doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        self.cleaner = TextCleaner()

        self.vector_orch = VectorOrchestrator(self.pdf_path)
        self.graph_orch = GraphOrchestrator(self.vector_orch.document_id)

        self.config = get_system_config()

    # =====================================================
    # STEP 1 — TOC + OFFSET
    # =====================================================

    def process_structure(self):

        print("\n[PIPELINE] STEP 1 — TOC + STRUCTURE")

        toc_orch = TOCOrchestrator(self.pdf_path)
        toc_data = toc_orch.run()

        if not toc_data:
            print("[PIPELINE] No TOC found — fallback chunking")

        return toc_data

    # =====================================================
    # STEP 2 — SMART CHUNKING
    # =====================================================

    def chunk_document(self, toc_data):

        print("\n[PIPELINE] STEP 2 — SMART CHUNKING")

        chunk_orch = ChunkOrchestrator(
            pdf_path=self.pdf_path,
            toc_data=toc_data
        )

        chunks = chunk_orch.run()

        print(f"[PIPELINE] Generated {len(chunks)} chunks")

        return chunks

    # =====================================================
    # STEP 3 — CLEAN CHUNKS
    # =====================================================

    def clean_chunks(self, chunks):

        print("\n[PIPELINE] STEP 3 — CLEANING")

        for chunk in chunks:
            chunk["text"] = self.cleaner.clean(chunk["text"])

        return chunks

    # =====================================================
    # STEP 4 — VECTOR STORE
    # =====================================================

    def store_vector(self, chunks):

        print("\n[PIPELINE] STEP 4 — VECTOR STORAGE")

        self.vector_orch.ingest(
            chunks=chunks
        )

    # =====================================================
    # STEP 5 — GRAPH STORE
    # =====================================================

    def store_graph(self, chunks):

        print("\n[PIPELINE] STEP 5 — GRAPH STORAGE")

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

    # =====================================================
    # RUN PIPELINE
    # =====================================================

    def run(self):

        # STEP 1
        toc_data = self.process_structure()

        # STEP 2
        chunks = self.chunk_document(toc_data)

        if not chunks:
            print("[PIPELINE] No chunks generated — stopping")
            return

        # Attach doc_id
        for chunk in chunks:
            chunk["doc_id"] = self.doc_id

        # STEP 3
        chunks = self.clean_chunks(chunks)

        # STEP 4
        self.store_vector(chunks)

        # STEP 5
        self.store_graph(chunks)

        print("\n" + "=" * 100)
        print("FULL INGESTION COMPLETED SUCCESSFULLY")
        print("=" * 100)

        self.graph_orch.close()


# =====================================================
# RUNNER
# =====================================================

def main():

    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m pipelines.full_ingestion_pipeline <pdf_path>")
        return

    pdf_path = sys.argv[1]

    pipeline = FullIngestionPipeline(pdf_path)
    pipeline.run()


if __name__ == "__main__":
    main()