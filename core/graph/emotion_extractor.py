import hashlib
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config.system_loader import get_model_config


class EmotionExtractor:

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):

        model_config = get_model_config()
        model_name = model_config.get("emotion_model", "phi")

        self.llm = ChatOllama(
            model=model_name,
            temperature=0.0,
            num_predict=10  # limit tokens (faster)
        )

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

        # Precomputed allowed emotions
        self.allowed = {
            "Joy", "Sadness", "Anger",
            "Fear", "Love", "Surprise",
            "Disgust", "Neutral"
        }

        # In-memory cache (huge speed gain)
        self.cache = {}

    # =====================================================
    # HASHING FOR CACHE
    # =====================================================

    def _hash_text(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    # =====================================================
    # SINGLE EXTRACTION
    # =====================================================

    def extract(self, text: str) -> str:

        if not text:
            return "Neutral"

        short_text = text[:800]
        key = self._hash_text(short_text)

        # 🔥 CACHE HIT
        if key in self.cache:
            return self.cache[key]

        try:
            result = self.chain.invoke(
                {"text": short_text},
                config={"timeout": 20}
            ).strip()

            if result not in self.allowed:
                result = "Neutral"

        except Exception:
            result = "Neutral"

        # Store in cache
        self.cache[key] = result

        return result

    # =====================================================
    # BATCH EXTRACTION (OPTIONAL)
    # =====================================================

    def extract_batch(self, texts: list) -> list:
        """
        Optimized batch emotion extraction.
        Uses caching automatically.
        """

        results = []

        for text in texts:
            results.append(self.extract(text))

        return results