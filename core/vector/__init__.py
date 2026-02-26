"""
SmartChunk-RAG — Vector Module

This module provides the complete vector layer for SmartChunk-RAG.

Components:
    - VectorEmbedder        → Generates embeddings (config-driven)
    - ChromaStore           → Persistent vector database handler
    - VectorChunkValidator  → Validates chunks before insertion
    - VectorOrchestrator    → Full ingestion controller for vectors

Design Principles:
    - Config-driven behavior
    - Deterministic document IDs
    - Idempotent upsert
    - Clean metadata handling
    - Separation of concerns
    - Fail-soft compatible

Example Usage:

    from core.vector import VectorOrchestrator

    vector = VectorOrchestrator(pdf_path="data/book.pdf")
    document_id = vector.ingest(chunks)

Author: SmartChunk-RAG System
"""

# -------------------------------------------------
# Public API Imports
# -------------------------------------------------

from .embedder import VectorEmbedder
from .store import ChromaStore
from .validator import VectorChunkValidator
from .orchestrator import VectorOrchestrator


# -------------------------------------------------
# Public Interface Control
# -------------------------------------------------

__all__ = [
    "VectorEmbedder",
    "ChromaStore",
    "VectorChunkValidator",
    "VectorOrchestrator",
]


# -------------------------------------------------
# Versioning (Useful for production deployments)
# -------------------------------------------------

__version__ = "1.0.0"