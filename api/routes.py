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
import threading
import zipfile
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple, List
import xml.etree.ElementTree as ET

from flask import g, jsonify, request, send_file
from werkzeug.utils import secure_filename
import fitz

from answering.answering_agent import AnsweringAgent
from answering.chat_orchestrator import ChatOrchestrator
from answering.uploaded_document_agent import UploadedDocumentAgent
from api.auth.middleware import require_auth, require_role
from memory.memory_wrapper import MemoryWrappedAnsweringAgent
from retriever.orchestrator import RetrieverOrchestrator
from core.media.ocr import OCRProcessor
from core.registry.document_registry import DocumentRegistry
from core.vector.store import ChromaStore
from core.graph.store import GraphStore
from core.utils.logging_utils import get_component_logger

from database.app_store import (
    create_thread,
    delete_thread,
    delete_messages_from_message_id,
    delete_user_upload,
    get_admin_statistics,
    get_thread_preferences,
    get_thread_summary,
    get_thread_messages,
    get_user_global_preferences,
    get_user_threads,
    get_user_upload,
    list_all_conversations,
    list_user_uploads,
    list_users,
    save_message,
    thread_belongs_to_user,
    create_user_upload,
    update_user_upload_status,
    update_latest_assistant_message,
    upsert_thread_preferences,
    upsert_thread_summary,
    upsert_user_global_preferences,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
CHAT_UPLOAD_DIR = PROJECT_ROOT / "data" / "user_uploads"
ALLOWED_UPLOAD_EXTENSIONS = {".pdf"}
ALLOWED_CHAT_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".gif",
}
logger = get_component_logger("api.routes", component="ingestion")
DEFAULT_ADMIN_INGEST_MAX_WORKERS = max(2, min(8, (os.cpu_count() or 4)))
ADMIN_INGEST_JOB_TTL_SECONDS = 12 * 60 * 60
_admin_ingest_jobs: dict[str, dict] = {}
_admin_ingest_jobs_lock = threading.Lock()


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


def _trim_text(value: str, limit: int) -> str:
    text = " ".join((value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _word_count(value: str) -> int:
    return len([token for token in (value or "").split() if token.strip()])


def _effective_preferences(user_id: str, thread_id: str) -> dict:
    global_pref = get_user_global_preferences(user_id)
    thread_pref = get_thread_preferences(thread_id)
    effective = dict(global_pref)
    effective.update(thread_pref)
    return effective


def _preferences_context_block(user_id: str, thread_id: str) -> str:
    global_pref = get_user_global_preferences(user_id)
    thread_pref = get_thread_preferences(thread_id)
    summary_row = get_thread_summary(thread_id) or {}
    summary = (summary_row.get("summary") or "").strip()

    lines = []
    if thread_pref:
        lines.append("### User Preferences")
        for key in sorted(thread_pref.keys()):
            lines.append(f"- {key}: {thread_pref[key]}")

    if global_pref:
        if lines:
            lines.append("")
        lines.append("### User Global Preferences")
        for key in sorted(global_pref.keys()):
            lines.append(f"- {key}: {global_pref[key]}")

    if summary:
        lines.append("")
        lines.append("### Conversation Summary")
        lines.append(summary)

    return "\n".join(lines).strip()


def _build_thread_summary(messages: list[dict], max_pairs: int = 4) -> str:
    if not messages:
        return ""

    pairs = []
    pending_user = None

    for msg in messages:
        role = (msg.get("role") or "").strip().lower()
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            pending_user = content
            continue

        if role == "assistant" and pending_user:
            pairs.append((pending_user, content))
            pending_user = None

    if not pairs:
        return _trim_text(messages[-1].get("content", ""), 500)

    selected = pairs[-max_pairs:]
    bullets = []
    for idx, (q, a) in enumerate(selected, start=1):
        q_short = _trim_text(q, 140)
        a_short = _trim_text(a, 200)
        bullets.append(f"{idx}. User asked: {q_short} | Assistant answered: {a_short}")

    summary = "Recent discussion summary:\n" + "\n".join(bullets)
    return _trim_text(summary, 1200)


def _run_ingestion(
    pdf_path: str,
    owner_user_id: str | None = None,
    scope: str = "global",
    ingest_id: str | None = None,
) -> dict:
    start_time = time.time()
    run_id = ingest_id or uuid.uuid4().hex[:8]
    pdf_name = Path(pdf_path).name
    logger.info(
        "ingestion_start ingest_id=%s scope=%s owner_user_id=%s file=%s",
        run_id,
        scope,
        owner_user_id,
        pdf_name,
    )

    from pipelines.full_ingestion_pipeline import FullIngestionPipeline

    try:
        pipeline = FullIngestionPipeline(
            pdf_path,
            owner_user_id=owner_user_id,
            scope=scope,
        )
        pipeline.run()
        payload = {
            "pdf_path": pdf_path,
            "document_id": getattr(getattr(pipeline, "vector_orch", None), "document_id", None),
            "ingestion_time_seconds": round(time.time() - start_time, 4),
            "ingest_id": run_id,
        }
        logger.info(
            "ingestion_done ingest_id=%s scope=%s file=%s doc_id=%s time_s=%s",
            run_id,
            scope,
            pdf_name,
            payload.get("document_id"),
            payload.get("ingestion_time_seconds"),
        )
        return payload
    except Exception:
        logger.exception(
            "ingestion_failed ingest_id=%s scope=%s owner_user_id=%s file=%s",
            run_id,
            scope,
            owner_user_id,
            pdf_name,
        )
        raise


def _is_allowed_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS


def _is_allowed_chat_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_CHAT_UPLOAD_EXTENSIONS


def _to_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on", "y"}


def _admin_ingest_max_workers(total_files: int) -> int:
    configured = os.getenv("ADMIN_INGEST_MAX_WORKERS", str(DEFAULT_ADMIN_INGEST_MAX_WORKERS))
    try:
        requested = int(configured)
    except (TypeError, ValueError):
        requested = DEFAULT_ADMIN_INGEST_MAX_WORKERS
    return max(1, min(total_files, requested))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_admin_ingest_jobs(now_ts: float | None = None) -> None:
    cutoff = (now_ts or time.time()) - ADMIN_INGEST_JOB_TTL_SECONDS
    stale = []
    for job_id, job in _admin_ingest_jobs.items():
        finished_at_ts = job.get("finished_at_ts")
        if finished_at_ts and finished_at_ts < cutoff:
            stale.append(job_id)
    for job_id in stale:
        _admin_ingest_jobs.pop(job_id, None)


def _admin_ingest_snapshot(job: dict) -> dict:
    total = int(job.get("total", 0))
    processed = int(job.get("processed", 0))
    progress_percent = 0 if total <= 0 else int(round((processed / total) * 100))
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "uploaded_count": total,
        "processed_count": processed,
        "ingested_count": int(job.get("succeeded", 0)),
        "failed_count": int(job.get("failed_count", 0)),
        "current_file": job.get("current_file", ""),
        "started_at": job.get("started_at"),
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
        "elapsed_seconds": int(job.get("elapsed_seconds", 0)),
        "progress_percent": max(0, min(100, progress_percent)),
        "ingested": list(job.get("ingested", [])),
        "failed": list(job.get("failed", [])),
    }


def _admin_ingest_finalize(job: dict) -> None:
    succeeded = int(job.get("succeeded", 0))
    failed_count = int(job.get("failed_count", 0))
    if succeeded > 0 and failed_count == 0:
        status = "success"
    elif succeeded > 0:
        status = "partial"
    else:
        status = "failed"
    job["status"] = status
    job["current_file"] = ""
    job["finished_at"] = _utc_now_iso()
    job["finished_at_ts"] = time.time()


def _start_admin_ingest_job(
    job_id: str,
    saved_files: list[tuple[str, str]],
    *,
    admin_id: str | None = None,
) -> None:
    start_ts = time.time()
    with _admin_ingest_jobs_lock:
        job = _admin_ingest_jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["started_at"] = _utc_now_iso()
        if not saved_files and int(job.get("processed", 0)) >= int(job.get("total", 0)):
            job["elapsed_seconds"] = max(1, int(round(time.time() - start_ts)))
            _admin_ingest_finalize(job)
            return

    workers = _admin_ingest_max_workers(len(saved_files)) if saved_files else 1
    if saved_files:
        logger.info(
            "admin_ingest_job running job_id=%s user_id=%s files=%s workers=%s",
            job_id,
            admin_id,
            len(saved_files),
            workers,
        )

    def _ingest_one(item: tuple[str, str]) -> tuple[str, str, dict]:
        safe_name_local, target_path_local = item
        ingest_id = uuid.uuid4().hex[:8]
        result_local = _run_ingestion(target_path_local, ingest_id=ingest_id)
        return safe_name_local, target_path_local, result_local

    if saved_files:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_file = {executor.submit(_ingest_one, item): item for item in saved_files}
            for future in as_completed(future_to_file):
                safe_name, target_path = future_to_file[future]
                elapsed = max(1, int(round(time.time() - start_ts)))
                try:
                    done_name, done_path, result = future.result()
                    logger.info(
                        "admin_ingest_job success job_id=%s user_id=%s filename=%s doc_id=%s path=%s",
                        job_id,
                        admin_id,
                        done_name,
                        result.get("document_id"),
                        done_path,
                    )
                    with _admin_ingest_jobs_lock:
                        job = _admin_ingest_jobs.get(job_id)
                        if not job:
                            continue
                        job["processed"] = int(job.get("processed", 0)) + 1
                        job["succeeded"] = int(job.get("succeeded", 0)) + 1
                        job["current_file"] = done_name
                        job["elapsed_seconds"] = elapsed
                        job.setdefault("ingested", []).append({"filename": done_name, **result})
                except Exception as exc:
                    logger.exception(
                        "admin_ingest_job failed job_id=%s user_id=%s filename=%s error=%s",
                        job_id,
                        admin_id,
                        safe_name,
                        str(exc),
                    )
                    with _admin_ingest_jobs_lock:
                        job = _admin_ingest_jobs.get(job_id)
                        if not job:
                            continue
                        job["processed"] = int(job.get("processed", 0)) + 1
                        job["failed_count"] = int(job.get("failed_count", 0)) + 1
                        job["current_file"] = safe_name
                        job["elapsed_seconds"] = elapsed
                        job.setdefault("failed", []).append({"filename": safe_name, "error": str(exc)})

    with _admin_ingest_jobs_lock:
        job = _admin_ingest_jobs.get(job_id)
        if not job:
            return
        job["elapsed_seconds"] = max(1, int(round(time.time() - start_ts)))
        _admin_ingest_finalize(job)
        logger.info(
            "admin_ingest_job summary job_id=%s user_id=%s uploaded=%s processed=%s ingested=%s failed=%s status=%s",
            job_id,
            admin_id,
            job.get("total", 0),
            job.get("processed", 0),
            job.get("succeeded", 0),
            job.get("failed_count", 0),
            job.get("status"),
        )


def _normalize_thread_messages(payload) -> list[dict]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("thread_messages must be an array")

    normalized = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        if not content:
            continue
        normalized.append({"role": role, "content": content})

    return normalized[-8:]


def _normalize_user_message_meta(payload) -> dict:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("user_message_meta must be an object")

    meta: dict = {}

    upload_ids = payload.get("upload_ids")
    if isinstance(upload_ids, list):
        cleaned_ids = [str(item or "").strip() for item in upload_ids if str(item or "").strip()]
        if cleaned_ids:
            meta["upload_ids"] = cleaned_ids

    attached_files = payload.get("attached_files")
    if isinstance(attached_files, list):
        cleaned_files = []
        for item in attached_files:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("original_name") or "").strip()
            file_type = str(item.get("type") or item.get("media_type") or "").strip()
            upload_id = str(item.get("uploadId") or item.get("upload_id") or item.get("id") or "").strip()
            if not name:
                continue
            cleaned_files.append(
                {
                    "name": name,
                    "type": file_type,
                    "upload_id": upload_id,
                }
            )
        if cleaned_files:
            meta["attached_files"] = cleaned_files

    return meta


def _serialize_upload_row(row: dict | None) -> dict | None:
    if not row:
        return None
    payload = dict(row)
    payload["index_enabled"] = bool(payload.get("index_enabled"))
    payload["indexed"] = bool(payload.get("indexed"))
    return payload


def _extract_text_from_upload(file_path: str, media_type: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if media_type == "image" or suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"}:
        results = OCRProcessor(file_path).run()
        parts = [str(item.get("text") or "").strip() for item in results]
        return "\n\n".join([p for p in parts if p])

    if suffix == ".pdf":
        doc = fitz.open(file_path)
        try:
            pages = []
            for page in doc:
                text = page.get_text("text").strip()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
        finally:
            doc.close()

    if suffix == ".docx":
        with zipfile.ZipFile(file_path) as archive:
            try:
                xml_payload = archive.read("word/document.xml")
            except KeyError:
                return ""

        root = ET.fromstring(xml_payload)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for para in root.findall(".//w:p", ns):
            runs = [node.text for node in para.findall(".//w:t", ns) if node.text]
            if runs:
                paragraphs.append("".join(runs))
        return "\n".join(paragraphs).strip()

    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def _build_upload_context(user_id: str, upload_ids: list[str], max_chars: int = 12000) -> str:
    if not upload_ids:
        return ""

    context_parts = []
    consumed = 0
    for upload_id in upload_ids:
        row = get_user_upload(upload_id, user_id)
        if not row:
            continue
        if row.get("status") != "completed":
            continue
        if row.get("indexed"):
            continue

        text = (row.get("extracted_text") or "").strip()
        if not text:
            continue

        remaining = max_chars - consumed
        if remaining <= 0:
            break

        snippet = text[:remaining]
        context_parts.append(
            f"### Uploaded File: {row.get('original_name')}\n{snippet}"
        )
        consumed += len(snippet)

    return "\n\n".join(context_parts).strip()


def _collect_upload_bundle(
    user_id: str,
    upload_ids: list[str],
    max_chars: int = 12000,
    include_indexed_text: bool = False,
) -> Tuple[str, List[str]]:
    """
    Returns:
    - upload_context from completed uploads (non-indexed by default; optionally indexed too)
    - selected indexed doc_ids for retrieval scoping
    """
    if not upload_ids:
        return "", []

    context_parts = []
    selected_doc_ids: List[str] = []
    consumed = 0

    for upload_id in upload_ids:
        row = get_user_upload(upload_id, user_id)
        if not row:
            continue
        if row.get("status") != "completed":
            continue

        if row.get("indexed"):
            doc_id = str(row.get("doc_id") or "").strip()
            if doc_id:
                selected_doc_ids.append(doc_id)
            if not include_indexed_text:
                continue

        text = (row.get("extracted_text") or "").strip()
        if not text:
            continue

        remaining = max_chars - consumed
        if remaining <= 0:
            break

        snippet = text[:remaining]
        context_parts.append(f"### Uploaded File: {row.get('original_name')}\n{snippet}")
        consumed += len(snippet)

    deduped_doc_ids = list(dict.fromkeys(selected_doc_ids))
    return "\n\n".join(context_parts).strip(), deduped_doc_ids


def _build_regeneration_context(thread_id: str, rewrite_from_message_id: str) -> str:
    target_thread_id = (thread_id or "").strip()
    target_message_id = (rewrite_from_message_id or "").strip()
    if not target_thread_id or not target_message_id:
        return ""

    try:
        rows = get_thread_messages(target_thread_id)
        if not rows:
            return ""

        for idx, row in enumerate(rows):
            if str(row.get("id") or "").strip() != target_message_id:
                continue
            user_question = (row.get("content") or "").strip()
            prior_answer = ""
            if idx + 1 < len(rows):
                next_row = rows[idx + 1]
                if str(next_row.get("role") or "").strip().lower() == "assistant":
                    prior_answer = (next_row.get("content") or "").strip()
            if not user_question and not prior_answer:
                return ""

            sections = ["### Regeneration Guidance"]
            if user_question:
                sections.append("Original user question:")
                sections.append(user_question)
            if prior_answer:
                sections.append("Previous assistant answer to improve:")
                sections.append(prior_answer)
            sections.append(
                "Generate a better answer for the same user request while preserving factual grounding."
            )
            return "\n\n".join(sections).strip()
    except Exception:
        logger.exception("Failed building regeneration context | thread_id=%s", target_thread_id)
        return ""

    return ""


def _run_user_upload_job(upload_id: str, user_id: str) -> None:
    row = get_user_upload(upload_id, user_id)
    if not row:
        return

    try:
        if (row.get("status") or "").strip().lower() == "cancelled":
            return
        update_user_upload_status(upload_id, status="processing", error_message="")

        file_path = row.get("file_path")
        if not file_path or not Path(file_path).exists():
            raise FileNotFoundError("Uploaded file not found")

        index_enabled = bool(row.get("index_enabled"))
        media_type = (row.get("media_type") or "").strip().lower()
        if index_enabled:
            if Path(file_path).suffix.lower() != ".pdf":
                raise ValueError("Indexing is only supported for PDF files")

            result = _run_ingestion(
                file_path,
                owner_user_id=user_id,
                scope="user",
            )
            update_user_upload_status(
                upload_id,
                status="completed",
                indexed=True,
                doc_id=result.get("document_id"),
                extracted_text="",
                error_message="",
            )
            return

        extracted = _extract_text_from_upload(file_path, media_type=media_type)
        update_user_upload_status(
            upload_id,
            status="completed",
            indexed=False,
            doc_id="",
            extracted_text=(extracted or "")[:50000],
            error_message="",
        )
    except Exception as exc:
        logger.exception("user upload job failed upload_id=%s error=%s", upload_id, str(exc))
        update_user_upload_status(
            upload_id,
            status="failed",
            error_message=str(exc),
        )


def _start_user_upload_job(upload_id: str, user_id: str) -> None:
    worker = threading.Thread(
        target=_run_user_upload_job,
        args=(upload_id, user_id),
        daemon=True,
    )
    worker.start()


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
    uploaded_doc_agent = UploadedDocumentAgent()
    chat_orchestrator = ChatOrchestrator(agent, uploaded_doc_agent)

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
        async_mode = _to_bool(request.args.get("async"), default=False)
        files = request.files.getlist("files")
        if not files and request.files.get("file"):
            files = [request.files.get("file")]

        if not files:
            return jsonify({"error": "At least one PDF file is required in form-data field 'files'"}), 400

        ADMIN_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        saved_files = []
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
                saved_files.append((safe_name, str(target_path)))
            except Exception as exc:
                logger.exception(
                    "admin_ingest_upload failed user_id=%s filename=%s error=%s",
                    admin_id,
                    safe_name,
                    str(exc),
                )
                failed.append({"filename": safe_name, "error": str(exc)})

        if async_mode:
            job_id = uuid.uuid4().hex[:12]
            with _admin_ingest_jobs_lock:
                _cleanup_admin_ingest_jobs()
                _admin_ingest_jobs[job_id] = {
                    "job_id": job_id,
                    "status": "queued",
                    "total": len(files),
                    "processed": len(failed),
                    "succeeded": 0,
                    "failed_count": len(failed),
                    "current_file": "",
                    "created_at": _utc_now_iso(),
                    "started_at": None,
                    "finished_at": None,
                    "finished_at_ts": None,
                    "elapsed_seconds": 0,
                    "ingested": [],
                    "failed": list(failed),
                }
                snapshot = _admin_ingest_snapshot(_admin_ingest_jobs[job_id])

            if saved_files:
                threading.Thread(
                    target=_start_admin_ingest_job,
                    args=(job_id, saved_files),
                    kwargs={"admin_id": admin_id},
                    daemon=True,
                ).start()
            else:
                with _admin_ingest_jobs_lock:
                    job = _admin_ingest_jobs.get(job_id)
                    if job:
                        job["status"] = "running"
                        job["started_at"] = _utc_now_iso()
                        job["elapsed_seconds"] = 1
                        _admin_ingest_finalize(job)
                        snapshot = _admin_ingest_snapshot(job)

            return jsonify(
                {
                    "status": "accepted",
                    "job_id": job_id,
                    **snapshot,
                }
            ), 202

        ingested = []
        if saved_files:
            workers = _admin_ingest_max_workers(len(saved_files))
            logger.info(
                "admin_ingest_upload running parallel ingestion user_id=%s files=%s workers=%s",
                admin_id,
                len(saved_files),
                workers,
            )

            def _ingest_one(item: tuple[str, str]) -> tuple[str, dict]:
                safe_name_local, target_path_local = item
                ingest_id = uuid.uuid4().hex[:8]
                result_local = _run_ingestion(target_path_local, ingest_id=ingest_id)
                return safe_name_local, result_local

            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_file = {
                    executor.submit(_ingest_one, item): item for item in saved_files
                }
                for future in as_completed(future_to_file):
                    safe_name, target_path = future_to_file[future]
                    try:
                        _, result = future.result()
                        logger.info(
                            "admin_ingest_upload success user_id=%s filename=%s doc_id=%s path=%s",
                            admin_id,
                            safe_name,
                            result.get("document_id"),
                            target_path,
                        )
                        ingested.append({"filename": safe_name, **result})
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

    @app.route("/admin/ingest/jobs/<job_id>", methods=["GET"])
    @require_role("admin")
    def admin_ingest_job_status(job_id: str):
        resolved = (job_id or "").strip()
        if not resolved:
            return jsonify({"error": "job_id required"}), 400
        with _admin_ingest_jobs_lock:
            _cleanup_admin_ingest_jobs()
            job = _admin_ingest_jobs.get(resolved)
            if not job:
                return jsonify({"error": "job not found"}), 404
            snapshot = _admin_ingest_snapshot(job)
        return jsonify(snapshot)

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

    @app.route("/chat/uploads", methods=["POST"])
    @require_auth
    def chat_uploads_create():
        user_id = g.user["user_id"]
        files = request.files.getlist("files")
        if not files and request.files.get("file"):
            files = [request.files.get("file")]
        if not files:
            return jsonify({"error": "At least one file is required in form-data field 'files'"}), 400

        index_enabled = _to_bool(request.form.get("index"), default=False)
        thread_id = (request.form.get("thread_id") or "").strip() or None
        if thread_id and not thread_belongs_to_user(thread_id, user_id):
            return jsonify({"error": "thread access denied"}), 403

        user_dir = CHAT_UPLOAD_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        queued = []
        failed = []
        for uploaded in files:
            original_name = uploaded.filename or ""
            safe_name = secure_filename(original_name)
            if not safe_name:
                failed.append({"filename": original_name, "error": "Invalid filename"})
                continue
            if not _is_allowed_chat_filename(safe_name):
                failed.append({"filename": safe_name, "error": "Unsupported file type"})
                continue

            suffix = Path(safe_name).suffix.lower()
            media_type = "image" if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".gif"} else "document"
            if index_enabled and suffix != ".pdf":
                failed.append({"filename": safe_name, "error": "Indexing is supported only for PDF files"})
                continue

            target_path = user_dir / f"{uuid.uuid4().hex}_{safe_name}"
            try:
                uploaded.save(str(target_path))
                row = create_user_upload(
                    user_id=user_id,
                    thread_id=thread_id,
                    original_name=safe_name,
                    media_type=media_type,
                    file_path=str(target_path),
                    index_enabled=index_enabled,
                )
                _start_user_upload_job(row["id"], user_id=user_id)
                queued.append(_serialize_upload_row(row))
            except Exception as exc:
                logger.exception("chat_uploads_create failed user_id=%s file=%s error=%s", user_id, safe_name, str(exc))
                failed.append({"filename": safe_name, "error": str(exc)})

        status = "success" if queued and not failed else "partial" if queued else "failed"
        code = 200 if status == "success" else 207 if status == "partial" else 400
        return jsonify(
            {
                "status": status,
                "queued_count": len(queued),
                "failed_count": len(failed),
                "queued": queued,
                "failed": failed,
            }
        ), code

    @app.route("/chat/uploads", methods=["GET"])
    @require_auth
    def chat_uploads_list():
        user_id = g.user["user_id"]
        thread_id = (request.args.get("thread_id") or "").strip() or None
        limit_raw = request.args.get("limit", 50)
        try:
            limit = max(1, min(200, int(limit_raw)))
        except (TypeError, ValueError):
            return jsonify({"error": "limit must be an integer"}), 400

        rows = list_user_uploads(user_id=user_id, thread_id=thread_id, limit=limit)
        return jsonify({"uploads": [_serialize_upload_row(row) for row in rows]})

    @app.route("/chat/uploads/<upload_id>", methods=["GET"])
    @require_auth
    def chat_uploads_get(upload_id: str):
        user_id = g.user["user_id"]
        row = get_user_upload(upload_id, user_id)
        if not row:
            return jsonify({"error": "upload not found"}), 404
        return jsonify({"upload": _serialize_upload_row(row)})

    @app.route("/chat/uploads/<upload_id>/file", methods=["GET"])
    @require_auth
    def chat_uploads_get_file(upload_id: str):
        user_id = g.user["user_id"]
        row = get_user_upload(upload_id, user_id)
        if not row:
            return jsonify({"error": "upload not found"}), 404

        file_path = Path(str(row.get("file_path") or "").strip())
        if not file_path.exists() or not file_path.is_file():
            return jsonify({"error": "uploaded file is unavailable"}), 404

        download_name = str(row.get("original_name") or file_path.name or "upload").strip()
        guessed_mime, _ = mimetypes.guess_type(download_name)
        return send_file(
            str(file_path),
            as_attachment=False,
            mimetype=guessed_mime or "application/octet-stream",
            download_name=download_name,
            conditional=True,
        )

    @app.route("/chat/uploads/<upload_id>", methods=["DELETE"])
    @require_auth
    def chat_uploads_delete(upload_id: str):
        user_id = g.user["user_id"]
        row = get_user_upload(upload_id, user_id)
        if not row:
            return jsonify({"error": "upload not found"}), 404

        doc_id = (row.get("doc_id") or "").strip()
        file_path = (row.get("file_path") or "").strip()
        indexed_deleted = False

        if doc_id:
            try:
                registry = DocumentRegistry()
                registry_row = registry.fetch_by_doc_id(doc_id)
                source_path = (registry_row[2] if registry_row else None) or file_path
                _delete_indexed_document(doc_id=doc_id, source_path=source_path)
                registry.delete(doc_id)
                indexed_deleted = True
            except Exception:
                logger.exception(
                    "chat_uploads_delete index cleanup failed user_id=%s upload_id=%s doc_id=%s",
                    user_id,
                    upload_id,
                    doc_id,
                )

        if file_path:
            try:
                target_file = Path(file_path)
                if target_file.exists() and target_file.is_file():
                    target_file.unlink()
            except Exception:
                logger.exception(
                    "chat_uploads_delete file cleanup failed user_id=%s upload_id=%s path=%s",
                    user_id,
                    upload_id,
                    file_path,
                )

        deleted_row = delete_user_upload(upload_id=upload_id, user_id=user_id)
        if not deleted_row:
            return jsonify({"error": "upload not found"}), 404

        return jsonify(
            {
                "status": "deleted",
                "upload_id": upload_id,
                "indexed_deleted": indexed_deleted,
            }
        )

    def _handle_chat_ask():
        start_time = time.time()
        data = request.get_json() or {}

        query = (data.get("query") or "").strip()
        requested_thread_id = (data.get("thread_id") or "").strip()
        upload_ids_raw = data.get("upload_ids") or []
        thread_messages_raw = data.get("thread_messages")
        user_message_meta_raw = data.get("user_message_meta")
        rewrite_from_message_id = (data.get("rewrite_from_message_id") or "").strip()
        agent_hint = (data.get("agent_hint") or "").strip().lower()
        query_mode = (data.get("query_mode") or "fast").strip().lower()
        global_pref_update = data.get("user_global_preference")
        thread_pref_update = data.get("thread_preference")
        if not query:
            return jsonify({"error": "query required"}), 400
        if not isinstance(upload_ids_raw, list):
            return jsonify({"error": "upload_ids must be an array"}), 400
        try:
            thread_messages = _normalize_thread_messages(thread_messages_raw)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        try:
            user_message_meta = _normalize_user_message_meta(user_message_meta_raw)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if agent_hint and agent_hint not in {"memory_answering_agent", "uploaded_document_agent"}:
            return jsonify({"error": "agent_hint must be memory_answering_agent or uploaded_document_agent"}), 400
        if query_mode not in {"fast", "pro"}:
            return jsonify({"error": "query_mode must be fast or pro"}), 400

        user_id = g.user["user_id"]
        user_role = g.user["role"]
        upload_ids = [str(item or "").strip() for item in upload_ids_raw if str(item or "").strip()]

        if requested_thread_id:
            if user_role != "admin" and not thread_belongs_to_user(requested_thread_id, user_id):
                return jsonify({"error": "thread access denied"}), 403
            try:
                thread_id = create_thread(user_id=user_id, thread_id=requested_thread_id, title=query)
            except ValueError:
                return jsonify({"error": "thread access denied"}), 403
        else:
            thread_id = create_thread(user_id=user_id, title=query)

        if global_pref_update is not None:
            if not isinstance(global_pref_update, dict):
                return jsonify({"error": "user_global_preference must be an object"}), 400
            upsert_user_global_preferences(user_id=user_id, preferences=global_pref_update)

        if thread_pref_update is not None:
            if not isinstance(thread_pref_update, dict):
                return jsonify({"error": "thread_preference must be an object"}), 400
            if not thread_belongs_to_user(thread_id, user_id):
                return jsonify({"error": "thread preference update denied"}), 403
            upsert_thread_preferences(
                user_id=user_id,
                thread_id=thread_id,
                preferences=thread_pref_update,
            )

        regeneration_context = ""
        if rewrite_from_message_id:
            regeneration_context = _build_regeneration_context(
                thread_id=thread_id,
                rewrite_from_message_id=rewrite_from_message_id,
            )
            deleted_count = delete_messages_from_message_id(
                thread_id=thread_id,
                message_id=rewrite_from_message_id,
            )
            if deleted_count == 0:
                logger.warning(
                    "rewrite_from_message_id not found; continuing as normal ask | thread_id=%s message_id=%s user_id=%s",
                    thread_id,
                    rewrite_from_message_id,
                    user_id,
                )
                regeneration_context = ""

        context_prefix_base = _preferences_context_block(user_id=user_id, thread_id=thread_id)
        if regeneration_context:
            context_prefix_base = "\n\n".join(
                [part for part in [context_prefix_base, regeneration_context] if part]
            )
        upload_context_chars = 24000 if query_mode == "pro" else 12000
        upload_context, selected_doc_ids = _collect_upload_bundle(
            user_id=user_id,
            upload_ids=upload_ids,
            max_chars=upload_context_chars,
            include_indexed_text=(agent_hint == "uploaded_document_agent"),
        )
        retrieval_filters = {"owner_user_id": user_id} if user_role != "admin" else None

        try:
            result, agent_used = chat_orchestrator.answer(
                user_id=user_id,
                user_role=user_role,
                query=query,
                thread_id=thread_id,
                query_mode=query_mode,
                context_prefix_base=context_prefix_base,
                upload_context=upload_context,
                selected_doc_ids=selected_doc_ids,
                agent_hint=agent_hint,
                retrieval_filters=retrieval_filters,
                thread_messages=thread_messages,
            )
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        assistant_response = result.get("response", "") or ""
        follow_up = result.get("follow_up", "") or ""
        citations = _structured_citations(result.get("citations", []) or [])
        if query_mode == "pro" and upload_ids:
            citations = []

        save_message(
            thread_id=thread_id,
            role="user",
            content=query,
            metadata=user_message_meta,
        )
        save_message(
            thread_id=thread_id,
            role="assistant",
            content=assistant_response,
            citations=citations,
        )

        try:
            thread_messages = get_thread_messages(thread_id)
            summary = _build_thread_summary(thread_messages)
            if summary:
                upsert_thread_summary(user_id=user_id, thread_id=thread_id, summary=summary)
        except Exception:
            logger.exception("Failed to refresh thread summary | thread_id=%s", thread_id)

        total_time = round(time.time() - start_time, 4)
        summary_row = get_thread_summary(thread_id) or {}
        effective_pref = _effective_preferences(user_id=user_id, thread_id=thread_id)
        return jsonify(
            {
                "query": query,
                "thread_id": thread_id,
                "latency_seconds": total_time,
                "response": assistant_response,
                "response_word_count": _word_count(assistant_response),
                "follow_up": follow_up,
                "citations": citations,
                "agent_used": agent_used,
                "query_mode": query_mode,
                "chat_summary": summary_row.get("summary", ""),
                "effective_preferences": effective_pref,
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

    @app.route("/chat/citations/<doc_id>/pdf", methods=["GET"])
    @require_auth
    def chat_citation_pdf(doc_id: str):
        resolved_doc_id = (doc_id or "").strip()
        if not resolved_doc_id:
            return jsonify({"error": "doc_id required"}), 400

        try:
            registry = DocumentRegistry()
            row = registry.fetch_by_doc_id(resolved_doc_id)
            if not row:
                return jsonify({"error": "document not found"}), 404

            source_path = row[2]
            if not source_path:
                return jsonify({"error": "source path not found"}), 404

            pdf_path = Path(source_path).resolve()
            if not pdf_path.exists() or not pdf_path.is_file():
                return jsonify({"error": "PDF file not found"}), 404
            if pdf_path.suffix.lower() != ".pdf":
                return jsonify({"error": "source file is not a PDF"}), 400

            return send_file(
                str(pdf_path),
                mimetype="application/pdf",
                as_attachment=False,
                download_name=pdf_path.name,
            )
        except Exception as exc:
            logger.exception("chat_citation_pdf failed doc_id=%s error=%s", resolved_doc_id, str(exc))
            return jsonify({"error": str(exc)}), 500

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

    @app.route("/chat/summary/<thread_id>", methods=["GET"])
    @require_auth
    def chat_summary(thread_id: str):
        user_id = g.user["user_id"]
        if g.user["role"] != "admin" and not thread_belongs_to_user(thread_id, user_id):
            return jsonify({"error": "thread access denied"}), 403
        row = get_thread_summary(thread_id) or {}
        return jsonify(
            {
                "thread_id": thread_id,
                "summary": row.get("summary", ""),
                "updated_at": row.get("updated_at"),
            }
        )

    @app.route("/chat/canvas/<thread_id>", methods=["PUT"])
    @require_auth
    def chat_canvas_save(thread_id: str):
        user_id = g.user["user_id"]
        if not thread_belongs_to_user(thread_id, user_id):
            return jsonify({"error": "thread access denied"}), 403

        payload = request.get_json() or {}
        content = (payload.get("content") or "").strip()
        if not content:
            return jsonify({"error": "content required"}), 400

        saved = update_latest_assistant_message(
            thread_id=thread_id,
            content=content,
            citations=[],
        )
        if not saved:
            save_message(thread_id=thread_id, role="assistant", content=content, citations=[])

        upsert_thread_summary(user_id=user_id, thread_id=thread_id, summary=content)

        try:
            agent.memory.upsert_latest_assistant_stm(
                user_id=user_id,
                thread_id=thread_id,
                content=content
            )
            agent.memory.store_ltm(
                user_id=user_id,
                content=content,
                category="edited_summary",
                metadata={"thread_id": thread_id, "source": "canvas"},
            )
        except Exception:
            logger.exception("Failed to persist canvas edit into memory | thread_id=%s", thread_id)

        row = get_thread_summary(thread_id) or {}
        return jsonify(
            {
                "thread_id": thread_id,
                "saved": True,
                "summary": row.get("summary", ""),
                "updated_at": row.get("updated_at"),
            }
        )

    @app.route("/chat/preferences/global", methods=["GET", "PUT"])
    @require_auth
    def chat_global_preferences():
        user_id = g.user["user_id"]
        if request.method == "GET":
            return jsonify({"user_id": user_id, "preferences": get_user_global_preferences(user_id)})

        payload = request.get_json() or {}
        preferences = payload.get("preferences")
        if not isinstance(preferences, dict):
            return jsonify({"error": "preferences must be an object"}), 400
        upsert_user_global_preferences(user_id=user_id, preferences=preferences)
        return jsonify({"user_id": user_id, "preferences": get_user_global_preferences(user_id)})

    @app.route("/chat/preferences/thread/<thread_id>", methods=["GET", "PUT"])
    @require_auth
    def chat_thread_preferences(thread_id: str):
        user_id = g.user["user_id"]
        if g.user["role"] != "admin" and not thread_belongs_to_user(thread_id, user_id):
            return jsonify({"error": "thread access denied"}), 403

        if request.method == "GET":
            return jsonify(
                {
                    "thread_id": thread_id,
                    "preferences": get_thread_preferences(thread_id),
                    "effective_preferences": _effective_preferences(user_id, thread_id),
                }
            )

        payload = request.get_json() or {}
        preferences = payload.get("preferences")
        if not isinstance(preferences, dict):
            return jsonify({"error": "preferences must be an object"}), 400
        if not thread_belongs_to_user(thread_id, user_id):
            return jsonify({"error": "thread preference update denied"}), 403
        upsert_thread_preferences(user_id=user_id, thread_id=thread_id, preferences=preferences)
        return jsonify(
            {
                "thread_id": thread_id,
                "preferences": get_thread_preferences(thread_id),
                "effective_preferences": _effective_preferences(user_id, thread_id),
            }
        )

    @app.route("/admin/users", methods=["GET"])
    @require_role("admin")
    def admin_users():
        return jsonify({"users": list_users()})

    @app.route("/admin/conversations", methods=["GET"])
    @require_role("admin")
    def admin_conversations():
        return jsonify({"conversations": list_all_conversations()})
