"""
Application API routes.

Includes:
- health / ingest / retrieve
- chat APIs (JWT protected)
- admin APIs (RBAC)
"""

import os
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from flask import g, jsonify, request
from werkzeug.utils import secure_filename

from answering.answering_agent import AnsweringAgent
from api.auth.middleware import require_auth, require_role
from memory.memory_wrapper import MemoryWrappedAnsweringAgent
from retriever.orchestrator import RetrieverOrchestrator
from core.registry.document_registry import DocumentRegistry
from core.vector.store import ChromaStore
from core.graph.store import GraphStore
from core.utils.logging_utils import get_component_logger

from database.app_store import (
    create_thread,
    delete_thread,
    get_admin_statistics,
    get_thread_messages,
    get_user_threads,
    list_all_conversations,
    list_users,
    save_message,
    thread_belongs_to_user,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
ALLOWED_UPLOAD_EXTENSIONS = {".pdf"}
logger = get_component_logger("api.routes", component="ingestion")


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


def _run_ingestion(pdf_path: str) -> dict:
    start_time = time.time()

    from pipelines.full_ingestion_pipeline import FullIngestionPipeline

    pipeline = FullIngestionPipeline(pdf_path)
    pipeline.run()

    return {
        "pdf_path": pdf_path,
        "document_id": getattr(getattr(pipeline, "vector_orch", None), "document_id", None),
        "ingestion_time_seconds": round(time.time() - start_time, 4),
    }


def _is_allowed_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS


def _compute_admin_statistics() -> dict:
    stats = get_admin_statistics()

    try:
        registry = DocumentRegistry()
        documents_count = len(registry.fetch_all())
    except Exception:
        documents_count = 0

    vector_chunks_count = 0
    try:
        vector_store = ChromaStore()
        if vector_store.collection is not None:
            vector_chunks_count = int(vector_store.collection.count())
    except Exception:
        vector_chunks_count = 0

    return {
        **stats,
        "documents_count": documents_count,
        "vector_chunks_count": vector_chunks_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _delete_indexed_document(doc_id: str, source_path: Optional[str]) -> dict:
    vector_deleted = False
    graph_deleted = False
    source_deleted = False

    vector_store = ChromaStore()
    vector_store.delete_document(doc_id)
    vector_deleted = True

    graph_store = GraphStore()
    try:
        graph_store.delete_document(doc_id)
        graph_deleted = True
    finally:
        graph_store.close()

    if source_path:
        source_file = Path(source_path)
        if source_file.exists() and source_file.is_file():
            source_file.unlink()
            source_deleted = True

    return {
        "doc_id": doc_id,
        "vector_deleted": vector_deleted,
        "graph_deleted": graph_deleted,
        "source_deleted": source_deleted,
    }


def register_routes(app):
    base_agent = AnsweringAgent()
    agent = MemoryWrappedAnsweringAgent(base_agent)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "SmartChunk-RAG API"})

    @app.route("/ingest", methods=["POST"])
    @require_role("admin")
    def ingest():
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON body required"}), 400

        pdf_path = data.get("pdf_path")
        if not pdf_path:
            return jsonify({"error": "pdf_path required"}), 400
        if not os.path.exists(pdf_path):
            return jsonify({"error": "PDF file not found"}), 400

        if Path(pdf_path).suffix.lower() != ".pdf":
            return jsonify({"error": "Only PDF files are supported"}), 400

        try:
            result = _run_ingestion(pdf_path)
            return jsonify({"status": "success", **result})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/admin/ingest/upload", methods=["POST"])
    @require_role("admin")
    def admin_ingest_upload():
        admin_user = (getattr(g, "user", None) or {})
        admin_id = admin_user.get("user_id")
        files = request.files.getlist("files")
        if not files and request.files.get("file"):
            files = [request.files.get("file")]

        if not files:
            return jsonify({"error": "At least one PDF file is required in form-data field 'files'"}), 400

        ADMIN_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        ingested = []
        failed = []

        for uploaded in files:
            original_name = uploaded.filename or ""
            safe_name = secure_filename(original_name)

            if not safe_name:
                failed.append({"filename": original_name, "error": "Invalid filename"})
                continue

            if not _is_allowed_filename(safe_name):
                failed.append({"filename": safe_name, "error": "Only PDF files are supported"})
                continue

            target_path = ADMIN_UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"

            try:
                uploaded.save(str(target_path))
                result = _run_ingestion(str(target_path))
                logger.info(
                    "admin_ingest_upload success user_id=%s filename=%s doc_id=%s path=%s",
                    admin_id,
                    safe_name,
                    result.get("document_id"),
                    str(target_path),
                )
                ingested.append({
                    "filename": safe_name,
                    **result,
                })
            except Exception as exc:
                logger.exception(
                    "admin_ingest_upload failed user_id=%s filename=%s error=%s",
                    admin_id,
                    safe_name,
                    str(exc),
                )
                failed.append({"filename": safe_name, "error": str(exc)})

        status = "success" if ingested and not failed else "partial" if ingested else "failed"
        http_code = 200 if status == "success" else 207 if status == "partial" else 400

        logger.info(
            "admin_ingest_upload summary user_id=%s uploaded=%s ingested=%s failed=%s status=%s",
            admin_id,
            len(files),
            len(ingested),
            len(failed),
            status,
        )
        return jsonify(
            {
                "status": status,
                "uploaded_count": len(files),
                "ingested_count": len(ingested),
                "failed_count": len(failed),
                "ingested": ingested,
                "failed": failed,
            }
        ), http_code

    @app.route("/admin/documents", methods=["GET"])
    @require_role("admin")
    def admin_documents():
        try:
            registry = DocumentRegistry()
            rows = registry.fetch_all()
            documents = [
                {
                    "doc_id": row[0],
                    "title": row[1],
                    "source_path": row[2],
                    "total_pages": row[3],
                    "created_at": row[4],
                }
                for row in rows
            ]
            admin_user = (getattr(g, "user", None) or {})
            logger.info(
                "admin_documents list user_id=%s count=%s",
                admin_user.get("user_id"),
                len(documents),
            )
            return jsonify({"documents": documents})
        except Exception as exc:
            logger.exception("admin_documents list failed error=%s", str(exc))
            return jsonify({"error": str(exc)}), 500

    @app.route("/admin/documents/<doc_id>", methods=["DELETE"])
    @require_role("admin")
    def admin_delete_document(doc_id: str):
        admin_user = (getattr(g, "user", None) or {})
        admin_id = admin_user.get("user_id")
        resolved_doc_id = (doc_id or "").strip()
        if not resolved_doc_id:
            return jsonify({"error": "doc_id required"}), 400

        try:
            registry = DocumentRegistry()
            row = registry.fetch_by_doc_id(resolved_doc_id)
            if not row:
                return jsonify({"error": "document not found"}), 404

            source_path = row[2]
            deletion_result = _delete_indexed_document(
                doc_id=resolved_doc_id,
                source_path=source_path,
            )
            registry.delete(resolved_doc_id)
            logger.info(
                "admin_delete_document success user_id=%s doc_id=%s source_deleted=%s",
                admin_id,
                resolved_doc_id,
                deletion_result.get("source_deleted"),
            )

            return jsonify(
                {
                    "status": "deleted",
                    **deletion_result,
                }
            )
        except Exception as exc:
            logger.exception(
                "admin_delete_document failed user_id=%s doc_id=%s error=%s",
                admin_id,
                resolved_doc_id,
                str(exc),
            )
            return jsonify({"error": str(exc)}), 500

    @app.route("/admin/documents/bulk-delete", methods=["POST"])
    @require_role("admin")
    def admin_bulk_delete_documents():
        admin_user = (getattr(g, "user", None) or {})
        admin_id = admin_user.get("user_id")
        data = request.get_json() or {}
        doc_ids_raw = data.get("doc_ids")

        if not isinstance(doc_ids_raw, list) or len(doc_ids_raw) == 0:
            return jsonify({"error": "doc_ids must be a non-empty array"}), 400

        doc_ids = []
        seen = set()
        for value in doc_ids_raw:
            item = str(value or "").strip()
            if not item or item in seen:
                continue
            seen.add(item)
            doc_ids.append(item)

        if len(doc_ids) == 0:
            return jsonify({"error": "No valid doc_ids provided"}), 400

        deleted = []
        failed = []
        registry = DocumentRegistry()

        for resolved_doc_id in doc_ids:
            try:
                row = registry.fetch_by_doc_id(resolved_doc_id)
                if not row:
                    failed.append({"doc_id": resolved_doc_id, "error": "document not found"})
                    logger.warning(
                        "admin_bulk_delete_documents missing user_id=%s doc_id=%s",
                        admin_id,
                        resolved_doc_id,
                    )
                    continue

                source_path = row[2]
                deletion_result = _delete_indexed_document(
                    doc_id=resolved_doc_id,
                    source_path=source_path,
                )
                registry.delete(resolved_doc_id)
                deleted.append(deletion_result)
                logger.info(
                    "admin_bulk_delete_documents success user_id=%s doc_id=%s source_deleted=%s",
                    admin_id,
                    resolved_doc_id,
                    deletion_result.get("source_deleted"),
                )
            except Exception as exc:
                failed.append({"doc_id": resolved_doc_id, "error": str(exc)})
                logger.exception(
                    "admin_bulk_delete_documents failed user_id=%s doc_id=%s error=%s",
                    admin_id,
                    resolved_doc_id,
                    str(exc),
                )

        status = "success" if deleted and not failed else "partial" if deleted else "failed"
        http_code = 200 if status == "success" else 207 if status == "partial" else 400
        logger.info(
            "admin_bulk_delete_documents summary user_id=%s requested=%s deleted=%s failed=%s status=%s",
            admin_id,
            len(doc_ids),
            len(deleted),
            len(failed),
            status,
        )
        return jsonify(
            {
                "status": status,
                "requested_count": len(doc_ids),
                "deleted_count": len(deleted),
                "failed_count": len(failed),
                "deleted": deleted,
                "failed": failed,
            }
        ), http_code

    @app.route("/admin/statistics", methods=["GET"])
    @require_role("admin")
    def admin_statistics():
        try:
            return jsonify({"statistics": _compute_admin_statistics()})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/admin/retrieve-chunks", methods=["POST"])
    @require_role("admin")
    def admin_retrieve_chunks():
        start_time = time.time()
        data = request.get_json() or {}

        query = (data.get("query") or "").strip()
        mode = (data.get("mode") or "hybrid").strip().lower()
        top_k_raw = data.get("top_k", 8)
        initial_k_raw = data.get("initial_k")
        filters = data.get("filters")

        try:
            top_k = int(top_k_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "top_k must be a positive integer"}), 400

        if initial_k_raw is None:
            initial_k = max(top_k, 15)
        else:
            try:
                initial_k = int(initial_k_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "initial_k must be a positive integer"}), 400

        if not query:
            return jsonify({"error": "query required"}), 400
        if mode not in {"vector", "graph", "hybrid"}:
            return jsonify({"error": "mode must be one of: vector, graph, hybrid"}), 400
        if top_k <= 0:
            return jsonify({"error": "top_k must be a positive integer"}), 400
        if initial_k <= 0:
            return jsonify({"error": "initial_k must be a positive integer"}), 400
        if filters is not None and not isinstance(filters, dict):
            return jsonify({"error": "filters must be an object"}), 400

        try:
            retriever = RetrieverOrchestrator()
            results = retriever.retrieve(
                query=query,
                mode=mode,
                top_k=top_k,
                initial_k=initial_k,
                filters=filters,
            )

            scores = [float(r.get("score", 0.0)) for r in results]
            unique_doc_ids = {r.get("doc_id") for r in results if r.get("doc_id")}
            response_results = []
            for idx, item in enumerate(results, start=1):
                text = item.get("text") or ""
                response_results.append(
                    {
                        "rank": idx,
                        "chunk_id": item.get("chunk_id"),
                        "doc_id": item.get("doc_id"),
                        "source": item.get("source"),
                        "score": item.get("score"),
                        "rerank_score": item.get("rerank_score"),
                        "text": text,
                        "preview": text[:360],
                        "metadata": item.get("metadata", {}),
                    }
                )

            admin_user = (getattr(g, "user", None) or {})
            logger.info(
                "admin_retrieve_chunks success user_id=%s query=%s mode=%s top_k=%s results=%s latency=%.4f",
                admin_user.get("user_id"),
                query,
                mode,
                top_k,
                len(response_results),
                round(time.time() - start_time, 4),
            )
            return jsonify(
                {
                    "query": query,
                    "mode": mode,
                    "top_k": top_k,
                    "initial_k": initial_k,
                    "filters": filters or {},
                    "latency_seconds": round(time.time() - start_time, 4),
                    "statistics": {
                        "result_count": len(response_results),
                        "unique_document_count": len(unique_doc_ids),
                        "avg_score": round(sum(scores) / len(scores), 6) if scores else 0.0,
                        "max_score": round(max(scores), 6) if scores else 0.0,
                        "min_score": round(min(scores), 6) if scores else 0.0,
                    },
                    "results": response_results,
                }
            )
        except Exception as exc:
            admin_user = (getattr(g, "user", None) or {})
            logger.exception(
                "admin_retrieve_chunks failed user_id=%s query=%s mode=%s error=%s",
                admin_user.get("user_id"),
                query,
                mode,
                str(exc),
            )
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
