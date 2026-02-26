"""
SmartChunk-RAG — Retriever Orchestrator Test Pipeline

Purpose:
- Test full retrieval pipeline
- Show vector + graph + hybrid flow
- Show reranking scores
- Display latency breakdown

Usage:
    python -m pipelines.test_retriever_orchestrator "Explain mitochondria" hybrid 5

Author: SmartChunk-RAG System
"""

import sys
import time

from retriever.orchestrator import RetrieverOrchestrator


# =====================================================
# Pretty Print Results
# =====================================================

def print_results(results):

    print("\n" + "=" * 100)
    print("FINAL RETRIEVAL RESULTS (POST-RERANK)")
    print("=" * 100)

    if not results:
        print("No results found.")
        return

    for idx, r in enumerate(results, 1):

        metadata = r.get("metadata", {})

        print(f"\nResult #{idx}")
        print("-" * 100)
        print(f"Rerank Score  : {round(r.get('rerank_score', 0), 4)}")
        print(f"Initial Score : {round(r.get('score', 0), 4)}")
        print(f"Source        : {r.get('source')}")
        print(f"Doc ID        : {r.get('doc_id')}")
        print(f"Chunk ID      : {r.get('chunk_id')}")

        # 🔥 ADD THESE LINES
        print(f"Chapter       : {metadata.get('chapter')}")
        print(f"Subheading    : {metadata.get('subheading')}")
        print(f"Emotion       : {metadata.get('emotion')}")

        print(f"Page Label    : {metadata.get('page_label')}")
        print(f"Page Physical : {metadata.get('page_physical')}")

        print("\nText Preview:")
        print(r.get("text", "")[:600])
        print("-" * 100)

    print("=" * 100)


# =====================================================
# Run Test
# =====================================================

def run_test(query, mode="hybrid", top_k=5):

    print("\n" + "=" * 100)
    print("SMARTCHUNK-RAG — FULL RETRIEVAL TEST")
    print("=" * 100)

    print(f"Query : {query}")
    print(f"Mode  : {mode}")
    print(f"Top K : {top_k}")

    orchestrator = RetrieverOrchestrator()

    start = time.time()

    results = orchestrator.retrieve(
        query=query,
        mode=mode,
        top_k=top_k
    )

    total_time = round(time.time() - start, 4)

    print_results(results)

    print(f"\nTotal Retrieval Time: {total_time} seconds")
    print("=" * 100 + "\n")


# =====================================================
# CLI ENTRY
# =====================================================

if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print('python -m pipelines.test_retriever_orchestrator "your query" [mode] [top_k]')
        sys.exit(1)

    query_input = sys.argv[1]

    mode_input = "hybrid"
    if len(sys.argv) >= 3:
        mode_input = sys.argv[2]

    top_k_input = 5
    if len(sys.argv) >= 4:
        try:
            top_k_input = int(sys.argv[3])
        except:
            pass

    run_test(query_input, mode_input, top_k_input)