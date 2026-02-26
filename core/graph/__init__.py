"""
Smart Medirag — Graph Module

Provides:
- GraphStore (Neo4j connection)
- GraphValidator (structure validation)
- GraphOrchestrator (ingestion engine)

Usage:
    from core.graph import GraphOrchestrator
"""

from .store import GraphStore
from .validator import GraphValidator
from .orchestrator import GraphOrchestrator
from .schema import (
    DOCUMENT,
    CHAPTER,
    SUBHEADING,
    CHUNK,
    HAS_CHAPTER,
    HAS_SUBHEADING,
    HAS_CHUNK,
    NEXT,
)

__all__ = [
    "GraphStore",
    "GraphValidator",
    "GraphOrchestrator",
    "DOCUMENT",
    "CHAPTER",
    "SUBHEADING",
    "CHUNK",
    "HAS_CHAPTER",
    "HAS_SUBHEADING",
    "HAS_CHUNK",
    "NEXT",
]