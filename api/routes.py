"""
SmartChunk-RAG — API Routes

Endpoints:
- GET  /health
- POST /ingest
- POST /retrieve
- POST /answer
"""

import os
import time
from flask import request, jsonify

from retriever.orchestrator import RetrieverOrchestrator
from answering.answering_agent import AnsweringAgent
from core.vector.orchestrator import VectorOrchestrator
from core.graph.orchestrator import GraphOrchestrator


# ============================================================
# REGISTER ROUTES
# ============================================================

def register_routes(app):

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
    # INGEST ENDPOINT
    # ============================================================

    @app.route("/ingest", methods=["POST"])
    def ingest():

        start_time = time.time()

        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        pdf_path = data.get("pdf_path")
        chunks = data.get("chunks")

        if not pdf_path:
            return jsonify({"error": "pdf_path required"}), 400

        if not os.path.exists(pdf_path):
            return jsonify({"error": "PDF file not found"}), 400

        if not chunks:
            return jsonify({"error": "chunks required"}), 400

        try:
            # Vector Ingestion
            vector = VectorOrchestrator(pdf_path)
            doc_id = vector.ingest(chunks)

            # Graph Ingestion
            graph = GraphOrchestrator(doc_id)
            graph.ingest_chunks(chunks)

            total_time = round(time.time() - start_time, 4)

            return jsonify({
                "status": "success",
                "doc_id": doc_id,
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
    # ANSWER ENDPOINT
    # ============================================================

    @app.route("/answer", methods=["POST"])
    def answer():

        start_time = time.time()

        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        query = data.get("query")

        if not query:
            return jsonify({"error": "query required"}), 400

        try:
            agent = AnsweringAgent()
            result = agent.answer(query)

            total_time = round(time.time() - start_time, 4)

            return jsonify({
                "query": query,
                "latency_seconds": total_time,
                "response": result.get("response"),
                "citations": result.get("citations")
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500