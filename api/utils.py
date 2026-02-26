"""
SmartChunk-RAG — Answering Utilities

Utility helpers for:
- Unicode cleaning
- Safe formatting
- DocID validation
- Hash generation
- Citation deduplication
- Text normalization
- JSON safety
"""

import re
import os
import json
import hashlib
from typing import List, Dict


# ============================================================
# UNICODE CLEANER
# ============================================================

def clean_unicode(text: str) -> str:
    """
    Normalize Unicode and remove problematic characters.
    """

    if not text:
        return ""

    # Normalize quotes and dashes
    replacements = {
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "\u00a0": " "
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    return text.strip()


# ============================================================
# WHITESPACE NORMALIZATION
# ============================================================

def normalize_whitespace(text: str) -> str:
    """
    Collapse multiple spaces and normalize newlines.
    """

    if not text:
        return ""

    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ============================================================
# SAFE TEXT PREVIEW
# ============================================================

def text_preview(text: str, limit: int = 500) -> str:
    """
    Return safe preview of text.
    """

    if not text:
        return ""

    return clean_unicode(text[:limit])


# ============================================================
# DOC ID VALIDATION
# ============================================================

def is_hex_doc_id(doc_id: str) -> bool:
    """
    Check if doc_id is a 16-character hexadecimal string.
    """

    if not doc_id:
        return False

    return bool(re.fullmatch(r'[0-9a-fA-F]{16}', doc_id))


# ============================================================
# HASH FILE TO DOC ID
# ============================================================

def generate_doc_id_from_path(path: str) -> str:
    """
    Generate deterministic doc_id from file.
    """

    if not os.path.exists(path):
        return None

    with open(path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    return file_hash[:16]


# ============================================================
# DEDUPLICATE CITATIONS
# ============================================================

def deduplicate_citations(citations: List[Dict]) -> List[Dict]:
    """
    Remove duplicate citations by chunk_id.
    """

    if not citations:
        return []

    seen = set()
    unique = []

    for c in citations:
        key = (
            c.get("doc_id"),
            c.get("chunk_id"),
            c.get("page_physical")
        )

        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


# ============================================================
# STRIP HALLUCINATED CITATIONS
# ============================================================

def strip_fake_citations(text: str) -> str:
    """
    Remove fake bracket citations like [1], [2] etc.
    """

    if not text:
        return ""

    return re.sub(r'\[\d+\]', '', text)


# ============================================================
# BULLET FORMATTER
# ============================================================

def format_as_bullets(items: List[str]) -> str:
    """
    Convert list of strings to bullet format.
    """

    if not items:
        return ""

    return "\n".join([f"- {clean_unicode(i)}" for i in items])


# ============================================================
# SAFE JSON SERIALIZER
# ============================================================

def safe_json(data: Dict) -> str:
    """
    Ensure safe JSON serialization.
    """

    return json.dumps(
        data,
        ensure_ascii=False,
        indent=4
    )


# ============================================================
# REMOVE EMPTY FIELDS
# ============================================================

def remove_none_fields(data: Dict) -> Dict:
    """
    Remove keys with None values.
    """

    return {
        k: v for k, v in data.items()
        if v is not None
    }


# ============================================================
# VALIDATE CONTEXT PRESENCE
# ============================================================

def has_valid_context(results: List[Dict]) -> bool:
    """
    Check if retrieved results contain usable text.
    """

    if not results:
        return False

    for r in results:
        if r.get("text"):
            return True

    return False