"""
SmartChunk-RAG — Vector & Graph Retriever Test

Purpose:
- Independently test VectorRetriever
- Independently test GraphRetriever
- Print structured results
- Measure latency

Usage:
    python -m pipelines.test_vector_and_graph "What is psychology?" 5

Author: SmartChunk-RAG System
"""

import sys
import time

from retriever.vector_retriever import VectorRetriever
from retriever.graph_retriever import GraphRetriever


# =====================================================
# Pretty Print Function
# =====================================================

def print_results(title, results):

    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)

    if not results:
        print("No results found.")
        return

    for idx, r in enumerate(results, 1):

        print(f"\nResult #{idx}")
        print("-" * 100)
        print(f"Score        : {round(r.get('score', 0), 4)}")
        print(f"Source       : {r.get('source')}")
        print(f"Doc ID       : {r.get('doc_id')}")
        print(f"Chunk ID     : {r.get('chunk_id')}")

        metadata = r.get("metadata", {})

        print(f"Chapter      : {metadata.get('chapter')}")
        print(f"Subheading   : {metadata.get('subheading')}")
        print(f"Page Label   : {metadata.get('page_label')}")
        print(f"Page Physical: {metadata.get('page_physical')}")
        print(f"Emotion      : {metadata.get('emotion')}")

        print("\nText Preview:")
        print(r.get("text", "")[:600])
        print("-" * 100)


# =====================================================
# Main Test Runner
# =====================================================

def run_test(query, top_k=5):

    print("\n" + "=" * 100)
    print("SMARTCHUNK-RAG — VECTOR & GRAPH RETRIEVER TEST")
    print("=" * 100)
    print(f"Query : {query}")
    print(f"Top K : {top_k}")

    # -------------------------
    # VECTOR TEST
    # -------------------------

    print("\n[VECTOR TEST]")

    vector = VectorRetriever()

    start = time.time()
    vector_results = vector.retrieve(query, top_k=top_k)
    vector_time = round(time.time() - start, 4)

    print_results("VECTOR RESULTS", vector_results)
    print(f"\nVector Retrieval Time: {vector_time} seconds")

    # -------------------------
    # GRAPH TEST
    # -------------------------

    print("\n[GRAPH TEST]")

    graph = GraphRetriever()

    start = time.time()
    graph_results = graph.retrieve(query, top_k=top_k)
    graph_time = round(time.time() - start, 4)

    print_results("GRAPH RESULTS", graph_results)
    print(f"\nGraph Retrieval Time: {graph_time} seconds")

    print("\n" + "=" * 100)
    print("TEST COMPLETED")
    print("=" * 100 + "\n")


# =====================================================
# CLI ENTRY
# =====================================================

if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print('python -m pipelines.test_vector_and_graph "your query" [top_k]')
        sys.exit(1)

    query_input = sys.argv[1]

    top_k_input = 5
    if len(sys.argv) >= 3:
        try:
            top_k_input = int(sys.argv[2])
        except:
            pass

    run_test(query_input, top_k_input)