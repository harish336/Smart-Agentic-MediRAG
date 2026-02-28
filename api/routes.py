"""
Application API routes.

Includes:
- health / ingest / retrieve
- chat APIs (JWT protected)
- admin APIs (RBAC)
"""

import os
import time
from flask import g, jsonify, request

from answering.answering_agent import AnsweringAgent
from api.auth.middleware import require_auth, require_role
from memory.memory_wrapper import MemoryWrappedAnsweringAgent
from retriever.orchestrator import RetrieverOrchestrator

from database.app_store import (
    create_thread,
    delete_thread,
    get_thread_messages,
    get_user_threads,
    list_all_conversations,
    list_users,
    save_message,
    thread_belongs_to_user,
)


def _structured_citations(citations: list[dict]) -> list[dict]:
    structured = []
    for index, c in enumerate(citations or [], start=1):
        structured.append(
            {
                "id": f"CIT-{index:03d}",
                "document": {
                    "doc_id": c.get("doc_id"),
                    "name": c.get("document_name"),
                },
                "location": {
                    "page_label": c.get("page_label"),
                    "page_physical": c.get("page_physical"),
                    "chapter": c.get("chapter"),
                    "subheading": c.get("subheading"),
                },
                "chunk_id": c.get("chunk_id"),
                "source": c.get("source"),
                "raw": c,
            }
        )
    return structured


def register_routes(app):
    base_agent = AnsweringAgent()
    agent = MemoryWrappedAnsweringAgent(base_agent)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "SmartChunk-RAG API"})

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
            from pipelines.full_ingestion_pipeline import FullIngestionPipeline

            pipeline = FullIngestionPipeline(pdf_path)
            pipeline.run()
            total_time = round(time.time() - start_time, 4)

            return jsonify(
                {
                    "status": "success",
                    "pdf_path": pdf_path,
                    "ingestion_time_seconds": total_time,
                }
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

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
            results = retriever.retrieve(query=query, mode=mode, top_k=top_k)
            total_time = round(time.time() - start_time, 4)
            return jsonify(
                {
                    "query": query,
                    "mode": mode,
                    "top_k": top_k,
                    "latency_seconds": total_time,
                    "results": results,
                }
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    def _handle_chat_ask():
        start_time = time.time()
        data = request.get_json() or {}

        query = (data.get("query") or "").strip()
        requested_thread_id = (data.get("thread_id") or "").strip()
        if not query:
            return jsonify({"error": "query required"}), 400

        user_id = g.user["user_id"]
        user_role = g.user["role"]

        if requested_thread_id:
            if user_role != "admin" and not thread_belongs_to_user(requested_thread_id, user_id):
                return jsonify({"error": "thread access denied"}), 403
            try:
                thread_id = create_thread(user_id=user_id, thread_id=requested_thread_id, title=query)
            except ValueError:
                return jsonify({"error": "thread access denied"}), 403
        else:
            thread_id = create_thread(user_id=user_id, title=query)

        try:
            result = agent.answer(user_id=user_id, query=query, thread_id=thread_id)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        assistant_response = result.get("response", "") or ""
        citations = _structured_citations(result.get("citations", []) or [])

        save_message(thread_id=thread_id, role="user", content=query)
        save_message(
            thread_id=thread_id,
            role="assistant",
            content=assistant_response,
            citations=citations,
        )

        total_time = round(time.time() - start_time, 4)
        return jsonify(
            {
                "query": query,
                "thread_id": thread_id,
                "latency_seconds": total_time,
                "response": assistant_response,
                "citations": citations,
            }
        )

    @app.route("/chat/ask", methods=["POST"])
    @require_auth
    def chat_ask():
        return _handle_chat_ask()

    # Backward-compatible endpoint.
    @app.route("/answer", methods=["POST"])
    @require_auth
    def answer():
        return _handle_chat_ask()

    @app.route("/chat/threads", methods=["GET"])
    @require_auth
    def chat_threads():
        return jsonify({"threads": get_user_threads(g.user["user_id"])})

    @app.route("/chat/threads/<thread_id>", methods=["DELETE"])
    @require_auth
    def chat_delete_thread(thread_id: str):
        user_id = g.user["user_id"]
        user_role = g.user["role"]

        if user_role == "admin":
            deleted = delete_thread(thread_id=thread_id, user_id=None)
        else:
            deleted = delete_thread(thread_id=thread_id, user_id=user_id)

        if not deleted:
            return jsonify({"error": "thread not found or access denied"}), 404

        return jsonify({"status": "deleted", "thread_id": thread_id})

    @app.route("/chat/messages/<thread_id>", methods=["GET"])
    @require_auth
    def chat_messages(thread_id: str):
        user_id = g.user["user_id"]
        if g.user["role"] != "admin" and not thread_belongs_to_user(thread_id, user_id):
            return jsonify({"error": "thread access denied"}), 403
        return jsonify({"thread_id": thread_id, "messages": get_thread_messages(thread_id)})

    @app.route("/admin/users", methods=["GET"])
    @require_role("admin")
    def admin_users():
        return jsonify({"users": list_users()})

    @app.route("/admin/conversations", methods=["GET"])
    @require_role("admin")
    def admin_conversations():
        return jsonify({"conversations": list_all_conversations()})
