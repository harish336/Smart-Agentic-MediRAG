import hashlib
from typing import Optional

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config.system_loader import get_model_config
from core.utils.logging_utils import get_component_logger


# =====================================================
# LOGGER SETUP
# =====================================================

logger = get_component_logger("EmotionExtractor", component="ingestion")


# =====================================================
# Lazy Singleton for ChatOllama (LOAD ONLY ONCE)
# =====================================================

_llm_instance: Optional[ChatOllama] = None


def get_emotion_llm(model_name: str) -> ChatOllama:
    global _llm_instance

    if _llm_instance is None:
        try:
            logger.info("Loading Emotion LLM (lazy load)...")
            _llm_instance = ChatOllama(
                model=model_name,
                temperature=0.0,
                num_predict=10
            )
            logger.info("Emotion LLM loaded successfully.")
        except Exception:
            logger.exception("Failed to load Emotion LLM")
            raise

    return _llm_instance


class EmotionExtractor:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        try:
            model_config = get_model_config()
            model_name = model_config.get("emotion_model", "phi")

            # Lazy-loaded LLM
            self.llm = get_emotion_llm(model_name)

            self.prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "You are a human emotion classifier.\n"
                    "Choose ONE emotion only from:\n"
                    "Joy, Sadness, Anger, Fear, Love, Surprise, Disgust, Neutral.\n"
                    "Return only the emotion word."
                ),
                ("user", "{text}")
            ])

            self.chain = self.prompt | self.llm | StrOutputParser()

            self.allowed = {
                "Joy", "Sadness", "Anger",
                "Fear", "Love", "Surprise",
                "Disgust", "Neutral"
            }

            self.cache = {}

            logger.info("EmotionExtractor initialized successfully.")

        except Exception:
            logger.exception("EmotionExtractor initialization failed")
            raise

    # =====================================================
    # HASHING FOR CACHE
    # =====================================================

    def _hash_text(self, text: str) -> str:
        try:
            return hashlib.md5(text.encode()).hexdigest()
        except Exception:
            logger.exception("Text hashing failed")
            return ""

    # =====================================================
    # SINGLE EXTRACTION
    # =====================================================

    def extract(self, text: str) -> str:

        if not text:
            return "Neutral"

        short_text = text[:800]
        key = self._hash_text(short_text)

        if key in self.cache:
            logger.debug("Emotion cache hit")
            return self.cache[key]

        try:
            result = self.chain.invoke(
                {"text": short_text},
                config={"timeout": 20}
            ).strip()

            if result not in self.allowed:
                logger.debug(f"Invalid emotion '{result}' — defaulting to Neutral")
                result = "Neutral"

        except Exception:
            logger.exception("Emotion extraction failed")
            result = "Neutral"

        self.cache[key] = result

        return result

    # =====================================================
    # BATCH EXTRACTION
    # =====================================================

    def extract_batch(self, texts: list) -> list:

        results = []

        try:
            for text in texts:
                results.append(self.extract(text))

        except Exception:
            logger.exception("Batch emotion extraction failed")

        return results
