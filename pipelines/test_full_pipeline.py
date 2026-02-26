"""
SmartChunk-RAG — Full Answering Pipeline Test

Flow:
Query
   ↓
RetrieverOrchestrator (vector + graph + rerank)
   ↓
AnsweringAgent (LLM grounded answer)
   ↓
Structured JSON Output

Usage:
python -m pipelines.test_full_pipeline "What is psychology?" hybrid 5
"""

import sys
import time
import json

from retriever.orchestrator import RetrieverOrchestrator
from answering.answering_agent import AnsweringAgent


# =====================================================
# Pretty Print Retrieval Results
# =====================================================

def print_retrieval(results):

    print("\n" + "=" * 100)
    print("RETRIEVAL RESULTS (POST-RERANK)")
    print("=" * 100)

    if not results:
        print("No retrieval results found.")
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
        print(f"Chapter       : {metadata.get('chapter')}")
        print(f"Subheading    : {metadata.get('subheading')}")
        print(f"Emotion       : {metadata.get('emotion')}")
        print(f"Page Label    : {metadata.get('page_label')}")
        print(f"Page Physical : {metadata.get('page_physical')}")

        print("\nText Preview:")
        print(r.get("text", "")[:500])
        print("-" * 100)

    print("=" * 100)


# =====================================================
# Pretty Print Final Answer JSON
# =====================================================

def print_answer(answer_json):

    print("\n" + "=" * 100)
    print("FINAL ANSWER (JSON OUTPUT)")
    print("=" * 100)

    print(json.dumps(answer_json, indent=4, ensure_ascii=False))

    print("=" * 100)


# =====================================================
# Run Full Pipeline
# =====================================================

def run_pipeline(query, mode="hybrid", top_k=5):

    print("\n" + "=" * 100)
    print("SMARTCHUNK-RAG — FULL ANSWERING PIPELINE")
    print("=" * 100)

    print(f"Query : {query}")
    print(f"Mode  : {mode}")
    print(f"Top K : {top_k}")

    # -------------------------------------------------
    # STEP 1 — Retrieval
    # -------------------------------------------------

    retrieval_start = time.time()

    retriever = RetrieverOrchestrator()
    retrieval_results = retriever.retrieve(
        query=query,
        mode=mode,
        top_k=top_k
    )

    retrieval_time = round(time.time() - retrieval_start, 4)

    print_retrieval(retrieval_results)

    # -------------------------------------------------
    # STEP 2 — Answering
    # -------------------------------------------------

    answering_start = time.time()

    answering_agent = AnsweringAgent()
    final_answer = answering_agent.answer(query)

    answering_time = round(time.time() - answering_start, 4)

    print_answer(final_answer)

    # -------------------------------------------------
    # Total Time
    # -------------------------------------------------

    total_time = round(retrieval_time + answering_time, 4)

    print("\n" + "=" * 100)
    print("LATENCY BREAKDOWN")
    print("=" * 100)
    print(f"Retrieval Time : {retrieval_time} seconds")
    print(f"Answering Time : {answering_time} seconds")
    print(f"Total Time     : {total_time} seconds")
    print("=" * 100 + "\n")


# =====================================================
# CLI ENTRY
# =====================================================

if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage:")
        print('python -m pipelines.test_full_pipeline "your query" [mode] [top_k]')
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

    run_pipeline(query_input, mode_input, top_k_input)