"""
SmartChunk-RAG — API Routes

Endpoints:
- GET  /health
- POST /ingest
- POST /retrieve
- POST /answer (with memory)
"""

import os
import time
from flask import request, jsonify

from retriever.orchestrator import RetrieverOrchestrator
from answering.answering_agent import AnsweringAgent
from memory.memory_wrapper import MemoryWrappedAnsweringAgent
from core.vector.orchestrator import VectorOrchestrator
from core.graph.orchestrator import GraphOrchestrator


# ============================================================
# REGISTER ROUTES
# ============================================================

def register_routes(app):

    # ============================================================
    # AGENT INITIALIZATION (Singleton - IMPORTANT)
    # ============================================================

    base_agent = AnsweringAgent()
    agent = MemoryWrappedAnsweringAgent(base_agent)

    # ============================================================
    # HEALTH CHECK
    # ============================================================

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "SmartChunk-RAG API"
        })


    # ============================================================
    # INGEST ENDPOINT (Pipeline Version)
    # ============================================================

    @app.route("/ingest", methods=["POST"])
    def ingest():

        start_time = time.time()
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        pdf_path = data.get("pdf_path")

        if not pdf_path:
            return jsonify({"error": "pdf_path required"}), 400

        if not os.path.exists(pdf_path):
            return jsonify({"error": "PDF file not found"}), 400

        try:
            # 🔥 Run Full Pipeline
            from pipelines.full_ingestion_pipeline import FullIngestionPipeline

            pipeline = FullIngestionPipeline(pdf_path)
            pipeline.run()

            total_time = round(time.time() - start_time, 4)

            return jsonify({
                "status": "success",
                "pdf_path": pdf_path,
                "ingestion_time_seconds": total_time
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # ============================================================
    # RETRIEVE ENDPOINT
    # ============================================================

    @app.route("/retrieve", methods=["POST"])
    def retrieve():

        start_time = time.time()
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        query = data.get("query")
        mode = data.get("mode", "hybrid")
        top_k = data.get("top_k", 5)

        if not query:
            return jsonify({"error": "query required"}), 400

        try:
            retriever = RetrieverOrchestrator()

            results = retriever.retrieve(
                query=query,
                mode=mode,
                top_k=top_k
            )

            total_time = round(time.time() - start_time, 4)

            return jsonify({
                "query": query,
                "mode": mode,
                "top_k": top_k,
                "latency_seconds": total_time,
                "results": results
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500


    # ============================================================
    # ANSWER ENDPOINT (WITH MEMORY SUPPORT)
    # ============================================================

    @app.route("/answer", methods=["POST"])
    def answer():

        start_time = time.time()
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        query = data.get("query")
        user_id = data.get("user_id")
        thread_id = data.get("thread_id")  # Optional now

        if not query:
            return jsonify({"error": "query required"}), 400

        if not user_id:
            return jsonify({"error": "user_id required"}), 400

        try:
            result = agent.answer(
                user_id=user_id,
                query=query,
                thread_id=thread_id
            )

            total_time = round(time.time() - start_time, 4)

            return jsonify({
                "query": query,
                "user_id": user_id,
                "thread_id": result.get("thread_id"),  # Return actual thread
                "latency_seconds": total_time,
                "response": result.get("response"),
                "citations": result.get("citations")
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500