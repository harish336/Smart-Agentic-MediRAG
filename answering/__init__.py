"""
SmartChunk-RAG — Answering Module

Provides:
- AnsweringAgent        → Main orchestration layer
- IntentRouter          → Query classification
- CitationManager       → Structured citation builder
- PromptBuilder         → LLM prompt constructor
- ResponseFormatter     → Final response formatting

Usage:

    from answering import AnsweringAgent

    agent = AnsweringAgent()
    result = agent.answer("What is psychology?")

    print(result)

Returns JSON:
{
    "response": "...",
    "citations": [...]
}
"""

from .answering_agent import AnsweringAgent
from .intent_router import IntentRouter
from .citation_manager import CitationManager
from .prompt_builder import PromptBuilder
from .response_formatter import ResponseFormatter


__all__ = [
    "AnsweringAgent",
    "IntentRouter",
    "CitationManager",
    "PromptBuilder",
    "ResponseFormatter",
]

__version__ = "1.0.0"