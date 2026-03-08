"""
Mode-aware chat orchestrator for upload-first and retrieval-first flows.
"""

import re
from typing import Dict, List, Optional, Tuple

from answering.uploaded_document_agent import UploadedDocumentAgent
from core.utils.logging_utils import get_component_logger
from memory.memory_wrapper import MemoryWrappedAnsweringAgent


logger = get_component_logger("ChatOrchestrator", component="answering")


class ChatOrchestrator:
    _FAST_PROFILE = {
        "mode": "hybrid",
        "top_k": 6,
        "initial_k": 16,
        "max_sub_queries": 1,
    }
    _PRO_PROFILE = {
        "mode": "hybrid",
        "top_k": 10,
        "initial_k": 30,
        "max_sub_queries": 3,
    }

    def __init__(
        self,
        memory_agent: MemoryWrappedAnsweringAgent,
        uploaded_doc_agent: UploadedDocumentAgent,
    ):
        self.memory_agent = memory_agent
        self.uploaded_doc_agent = uploaded_doc_agent

    def answer(
        self,
        *,
        user_id: str,
        user_role: str,
        query: str,
        thread_id: str,
        query_mode: str,
        context_prefix_base: str,
        upload_context: str,
        selected_doc_ids: List[str],
        agent_hint: str,
        retrieval_filters: Optional[Dict],
        thread_messages: Optional[List[Dict]],
    ) -> Tuple[Dict, str]:
        mode = (query_mode or "fast").strip().lower()
        if mode not in {"fast", "pro"}:
            mode = "fast"
        is_pro_mode = mode == "pro"

        profile = self._PRO_PROFILE if mode == "pro" else self._FAST_PROFILE
        scoped_filters = self._with_doc_scope(
            retrieval_filters=retrieval_filters,
            selected_doc_ids=selected_doc_ids,
        )

        context_prefix = context_prefix_base
        if upload_context:
            context_prefix = "\n\n".join(
                part for part in [context_prefix, "### Uploaded Context\n" + upload_context] if part
            )

        # Transformation commands must use previous assistant response as source,
        # not fresh retrieval from uploads/index.
        if self._is_transformation_query(query):
            result = self.memory_agent.answer(
                user_id=user_id,
                query=query,
                thread_id=thread_id,
                context_prefix=context_prefix,
                retrieval_filters=scoped_filters,
                thread_messages=thread_messages,
                retrieval_options=profile,
                uploaded_context="",
            )
            if (result.get("response") or "").strip():
                return result, "memory_answering_agent_transformation"

        # Questions targeted at the uploaded PDF should stay upload-only.
        if upload_context and self._is_upload_specific_query(query):
            result = self.uploaded_doc_agent.answer(
                query=query,
                uploaded_context=upload_context,
                context_prefix=context_prefix_base,
            )
            if (result.get("response") or "").strip().lower() != "dont have an answer":
                return result, "uploaded_document_agent_pdf_only"

        # Forced upload-first routing when explicitly requested.
        if upload_context and agent_hint == "uploaded_document_agent":
            result = self.uploaded_doc_agent.answer(
                query=query,
                uploaded_context=upload_context,
                context_prefix=context_prefix_base,
            )
            if (result.get("response") or "").strip().lower() != "dont have an answer":
                return result, "uploaded_document_agent"

        # Pro mode: combine indexed retrieval with uploaded chat-document evidence.
        if is_pro_mode and upload_context and agent_hint != "uploaded_document_agent":
            result = self.memory_agent.answer(
                user_id=user_id,
                query=query,
                thread_id=thread_id,
                context_prefix=context_prefix,
                retrieval_filters=scoped_filters,
                thread_messages=thread_messages,
                retrieval_options=profile,
                uploaded_context=upload_context,
            )
            if (result.get("response") or "").strip().lower() != "dont have an answer":
                return result, "memory_answering_agent_pro_hybrid"

        # Fast mode: if uploaded text is available, prefer document-grounded answering.
        upload_first = bool(upload_context) and agent_hint != "memory_answering_agent" and not is_pro_mode
        if upload_first:
            result = self.uploaded_doc_agent.answer(
                query=query,
                uploaded_context=upload_context,
                context_prefix=context_prefix_base,
            )
            if (result.get("response") or "").strip().lower() != "dont have an answer":
                return result, "uploaded_document_agent"

        result = self.memory_agent.answer(
            user_id=user_id,
            query=query,
            thread_id=thread_id,
            context_prefix=context_prefix,
            retrieval_filters=scoped_filters,
            thread_messages=thread_messages,
            retrieval_options=profile,
            uploaded_context=upload_context if is_pro_mode else "",
        )
        if (result.get("response") or "").strip().lower() != "dont have an answer":
            return result, "memory_answering_agent"

        if upload_context:
            fallback = self.uploaded_doc_agent.answer(
                query=query,
                uploaded_context=upload_context,
                context_prefix=context_prefix_base,
            )
            if (fallback.get("response") or "").strip().lower() != "dont have an answer":
                return fallback, "uploaded_document_agent_fallback"

        if user_role == "admin" and upload_context and agent_hint != "uploaded_document_agent":
            # Admins may not have owner-scoped retrieval filters. One final direct pass can recover.
            fallback = self.uploaded_doc_agent.answer(
                query=query,
                uploaded_context=upload_context,
                context_prefix=context_prefix_base,
            )
            if (fallback.get("response") or "").strip().lower() != "dont have an answer":
                return fallback, "uploaded_document_agent_admin_fallback"

        return result, "memory_answering_agent"

    @staticmethod
    def _with_doc_scope(
        *,
        retrieval_filters: Optional[Dict],
        selected_doc_ids: List[str],
    ) -> Optional[Dict]:
        scoped = dict(retrieval_filters or {})
        clean_doc_ids = [str(doc_id).strip() for doc_id in (selected_doc_ids or []) if str(doc_id).strip()]
        if clean_doc_ids:
            scoped["doc_ids"] = clean_doc_ids
        return scoped or None

    @staticmethod
    def _is_upload_specific_query(query: str) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False

        # Formatting/structure conversions should not be hijacked by upload routing.
        if ChatOrchestrator._is_transformation_query(query):
            return False

        summary_markers = [
            "summary",
            "summarize",
            "summarise",
            "brief",
            "tl;dr",
            "key points",
            "main points",
            "overview",
            "gist",
            "abstract",
        ]
        upload_markers = [
            "pdf",
            "uploaded",
            "upload",
            "document",
            "file",
            "attached",
            "chapter",
            "page",
            "section",
        ]
        marker_hit = any(marker in text for marker in upload_markers)

        if marker_hit:
            return True

        # Direct imperative summary prompts in upload chat mode are likely PDF-targeted.
        if re.search(r"^(summari[sz]e|give (me )?(a )?summary|short summary)\b", text):
            return True

        # Summary request with explicit "this/that" can refer to the uploaded file in chat flow.
        if any(marker in text for marker in summary_markers) and re.search(r"\b(this|that|above)\b", text):
            return True

        return False

    @staticmethod
    def _is_transformation_query(query: str) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False
        has_transform_verb = bool(
            re.search(
                r"\b(make|convert|reformat|transform|rewrite|summari[sz]e|shorten|simplify|format|structure)\b",
                text,
            )
        )
        has_target_format = bool(
            re.search(r"\b(table|tabular|table format|as a table|bullets?|list|steps?|markdown|json|format)\b", text)
        )
        has_reference = bool(
            re.search(r"\b(above|previous|earlier|that|this|it|response|answer)\b", text)
        )
        has_inline_source = bool(
            re.search(r"\b(text in canvas|canvas text|source text|raw text)\b", text)
            and ("\n" in text or len(text) > 220)
            and has_target_format
        )
        return (has_transform_verb and has_reference) or (has_transform_verb and has_target_format) or has_inline_source
