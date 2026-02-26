import re
import unicodedata

class ResponseFormatter:
    """
    Industry-Optimized Response Formatter for RAG Pipelines.
    Ensures JSON-safe, chatter-free, and cleanly formatted outputs.
    """

    def __init__(self):
        # ============================================================
        # COMPILED REGEX PATTERNS (Compiled once for performance)
        # ============================================================
        
        # 1. Chatter Pattern: Catches variations of introductory fluff
        # Handles: "Sure!", "Here's the answer:", "Based on the context," etc.
        self.chatter_pattern = re.compile(
            r"^(?:(?:certainly|sure|yes|absolutely)[.,!]*\s*)?"
            r"(?:here(?: is|'s)? (?:the|your) (?:answer|response|information|explanation)|"
            r"based on (?:the )?(?:provided )?context|"
            r"according to (?:the )?(?:provided )?(?:context|text|document|book)|"
            r"to answer (?:the|your) question|"
            r"as stated in).*?[:,-]?\s*\n*",
            re.IGNORECASE
        )

        # 2. Markdown Link Pattern: [link text](https://...)
        self.md_link_pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")
        
        # 3. Raw URL Pattern: https://... (ignoring trailing punctuation)
        self.raw_url_pattern = re.compile(r"(?<!\]\()(https?://[a-zA-Z0-9./?=_%&+-]+)")

        # 4. Spacing Pattern: Catches 3 or more newlines
        self.spacing_pattern = re.compile(r"\n{3,}")

        # 5. Trailing Whitespace Pattern (per line)
        self.trailing_ws_pattern = re.compile(r"[ \t]+$", re.MULTILINE)

    # ============================================================
    # PUBLIC FORMAT METHOD
    # ============================================================

    def format(self, text: str) -> str:
        if not text or not isinstance(text, str):
            return ""

        text = text.strip()

        # Execute cleaning pipeline
        text = self._remove_prefixes(text)
        text = self._normalize_unicode(text)
        text = self._separate_links(text)
        text = self._clean_spacing(text)

        return text.strip()

    # ============================================================
    # PIPELINE METHODS
    # ============================================================

    def _remove_prefixes(self, text: str) -> str:
        """Removes conversational filler using a robust regex pattern."""
        # re.sub replaces the matched chatter at the start (^) with nothing
        return self.chatter_pattern.sub("", text).strip()

    def _normalize_unicode(self, text: str) -> str:
        """
        Normalizes Unicode to NFKC and strips JSON-breaking control characters.
        """
        # 1. Standardize character representations (fixes weird typographic quotes/dashes)
        text = unicodedata.normalize("NFKC", text)

        # 2. Manual fallbacks for common smart quotes just in case NFKC misses them
        replacements = {
            '"': '"', '"': '"', "”": '"', "“": '"',
            "'": "'", "'": "'", "’": "'", "‘": "'",
            "–": "-", "—": "-"
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        # 3. Strip unprintable control characters that break JSON serialization 
        # (Allows standard carriage returns, newlines, and tabs)
        text = "".join(
            ch for ch in text 
            if unicodedata.category(ch)[0] != "C" or ch in "\r\n\t"
        )

        return text

    def _clean_spacing(self, text: str) -> str:
        """Ensures consistent line breaks and removes trailing line whitespaces."""
        # Replace 3+ newlines with exactly 2
        text = self.spacing_pattern.sub("\n\n", text)
        # Remove trailing whitespace from individual lines
        text = self.trailing_ws_pattern.sub("", text)
        return text

    def _separate_links(self, text: str) -> str:
        """
        Intelligently extracts URLs, prevents dangling markdown brackets, 
        and builds a clean reference list at the bottom.
        """
        extracted_urls = []

        # Handler for Markdown links: converts "[click here](url)" to "click here"
        def md_replacer(match):
            link_text = match.group(1)
            url = match.group(2)
            if url not in extracted_urls:
                extracted_urls.append(url)
            return link_text

        # 1. Process and remove markdown links first
        text = self.md_link_pattern.sub(md_replacer, text)

        # 2. Process remaining raw URLs
        for raw_url in self.raw_url_pattern.findall(text):
            if raw_url not in extracted_urls:
                extracted_urls.append(raw_url)
        
        # 3. Remove raw URLs from the text
        text = self.raw_url_pattern.sub("", text)

        # 4. Append a cleanly formatted references section if URLs exist
        if extracted_urls:
            links_block = "\n\nREFERENCES:\n" + "\n".join(f"- {url}" for url in extracted_urls)
            return text.strip() + links_block

        return text