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
        "mode": "vector",
        "top_k": 4,
        "initial_k": 12,
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
        intent_policy: str,
        context_prefix_base: str,
        upload_context: str,
        selected_doc_ids: List[str],
        agent_hint: str,
        retrieval_filters: Optional[Dict],
        thread_messages: Optional[List[Dict]],
        has_uploaded_pdf: bool = False,
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

        has_upload = bool(upload_context.strip()) or bool(has_uploaded_pdf)
        is_transform_request = self._is_transformation_query(query)

        # Transformation requests should operate on prior assistant output, not re-answer.
        if is_transform_request:
            result = self.memory_agent.answer(
                user_id=user_id,
                query=query,
                thread_id=thread_id,
                context_prefix=context_prefix,
                retrieval_filters=scoped_filters,
                thread_messages=thread_messages,
                retrieval_options=profile,
                uploaded_context="",
                query_type_override="transformation",
                intent_override="",
            )
            return result, "transformation_agent"

        pdf_only_needed = has_upload and self._is_pdf_question(query, thread_messages)

        # If query is clearly PDF-scoped, answer directly from uploaded PDF (fast + pro).
        if pdf_only_needed:
            result = self.uploaded_doc_agent.answer(
                query=query,
                uploaded_context=upload_context,
                context_prefix=context_prefix_base,
            )
            return result, "uploaded_document_agent_pdf_only"

        # Non PDF-only queries:
        # - pro => knowledge (+pdf when uploaded)
        # - fast => general (+pdf when uploaded)
        uploaded_context_for_memory = upload_context if has_upload else ""
        # UI intent-policy flag is authoritative when provided.
        ui_intent = (intent_policy or "").strip().lower()
        if ui_intent in {"general", "knowledge"}:
            forced_intent = ui_intent
        else:
            forced_intent = "knowledge" if is_pro_mode else "general"
        result = self.memory_agent.answer(
            user_id=user_id,
            query=query,
            thread_id=thread_id,
            context_prefix=context_prefix,
            retrieval_filters=scoped_filters,
            thread_messages=thread_messages,
            retrieval_options=profile,
            uploaded_context=uploaded_context_for_memory,
            query_type_override="knowledge",
            intent_override=forced_intent,
        )
        if has_upload and forced_intent == "knowledge":
            return result, "memory_answering_agent_knowledge_upload"
        if has_upload and forced_intent == "general":
            return result, "memory_answering_agent_general_upload"
        if forced_intent == "knowledge":
            return result, "memory_answering_agent_knowledge_only"
        return result, "memory_answering_agent_general_only"

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
        has_upload_marker = bool(
            re.search(r"\b(pdf|uploaded|upload|document|file|attached|chapter|page|section)\b", text)
        )
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
        if has_inline_source:
            return True
        # If query is explicitly about uploaded PDF/file content, treat it as QA unless
        # user clearly references transforming prior assistant output.
        if has_upload_marker and not has_reference:
            return False
        return (has_transform_verb and has_reference) or (has_transform_verb and has_target_format and not has_upload_marker)

    @staticmethod
    def _is_explicit_pdf_query(query: str) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False
        return bool(re.search(r"\bpdf\b", text))

    @staticmethod
    def _is_pdf_question(query: str, thread_messages: Optional[List[Dict]] = None) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False
        if ChatOrchestrator._is_explicit_pdf_query(query):
            return True
        if ChatOrchestrator._is_upload_specific_query(query):
            return True
        # Pronoun-heavy follow-ups in an upload thread are usually PDF-scoped.
        if re.search(r"\b(this|that|it|above|from this|from that)\b", text):
            recent_user = [
                (m.get("content") or "").strip().lower()
                for m in (thread_messages or [])
                if (m.get("role") or "").strip().lower() == "user" and (m.get("content") or "").strip()
            ]
            if recent_user:
                return True
        return False

    @staticmethod
    def _is_general_knowledge_query(query: str, thread_messages: Optional[List[Dict]] = None) -> bool:
        text = (query or "").strip().lower()
        if not text:
            return False

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
            "this",
            "that",
            "above",
            "from here",
        ]
        if any(marker in text for marker in upload_markers):
            return False

        if ChatOrchestrator._is_transformation_query(query):
            return False

        explicit_general_markers = [
            "in general",
            "generally",
            "general knowledge",
            "overall concept",
            "what is",
            "define ",
            "explain ",
            "difference between",
        ]
        if any(marker in text for marker in explicit_general_markers):
            return True

        # Follow-up pronouns should stay upload-aware if conversation is ongoing.
        if re.search(r"\b(it|this|that|they|those|these)\b", text):
            recent_user = [
                (m.get("content") or "").strip()
                for m in (thread_messages or [])
                if (m.get("role") or "").strip().lower() == "user" and (m.get("content") or "").strip()
            ]
            if recent_user:
                return False

        question_starts_general = bool(
            re.search(r"^\s*(what|why|how|who|when|where)\b", text)
        )
        return question_starts_general

    @staticmethod
    def _classify_pro_route(query: str, thread_messages: Optional[List[Dict]] = None) -> str:
        """
        Returns:
        - "pdf_only" when the question is clearly about uploaded file details
        - "hybrid" otherwise (uploaded evidence + indexed knowledge)
        """
        text = (query or "").strip().lower()
        if not text:
            return "hybrid"

        if ChatOrchestrator._is_upload_specific_query(query):
            return "pdf_only"

        # Pronoun-heavy follow-ups in an upload thread are usually PDF-scoped.
        if re.search(r"\b(this|that|it|above|from this|from that)\b", text):
            recent_user = [
                (m.get("content") or "").strip().lower()
                for m in (thread_messages or [])
                if (m.get("role") or "").strip().lower() == "user" and (m.get("content") or "").strip()
            ]
            if recent_user:
                return "pdf_only"

        return "hybrid"
