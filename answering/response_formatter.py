"""
response_formatter.py
A robust ResponseFormatter that:
- normalizes Unicode (NFKC)
- optionally repairs broken encodings with `ftfy` if available
- maps common typographic punctuation to stable equivalents
- extracts links into a REFERENCES block
- removes control characters (except \n, \r, \t)
"""

from __future__ import annotations
import re
import unicodedata
from typing import List, Pattern, Dict, Optional

# Try optional dependency to fix mojibake / badly-encoded text.
try:
    import ftfy  # type: ignore
    _HAS_FTFY = True
except Exception:
    _HAS_FTFY = False


class ResponseFormatter:
    def __init__(self) -> None:
        # Preface/chatter pattern (keeps same intention but tightened)
        self.chatter_pattern: Pattern = re.compile(
            r"^(?:(?:certainly|sure|yes|absolutely)[\.,!]*\s*)?"
            r"(?:here(?: is|'s)?(?: the| your)? (?:answer|response|information|explanation)|"
            r"based on (?:the )?(?:provided )?context|"
            r"according to (?:the )?(?:provided )?(?:context|text|document|book)|"
            r"to answer (?:the|your) question|"
            r"as stated in).*?[:\-,]?\s*\n*",
            re.IGNORECASE,
        )

        # Markdown and raw URL patterns
        self.md_link_pattern: Pattern = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")
        self.raw_url_pattern: Pattern = re.compile(
            r"(?<!\]\()(https?://[a-zA-Z0-9\-\._~:/\?#\[\]@!\$&'()*\+,;=%]+)"
        )

        # Spacing / trailing spaces
        self.spacing_pattern: Pattern = re.compile(r"\n{3,}")
        self.trailing_ws_pattern: Pattern = re.compile(r"[ \t]+$", re.MULTILINE)
        self.enumerated_item_pattern: Pattern = re.compile(r"^\s*(\d+)[\.\)]\s+", re.MULTILINE)

        # comprehensive punctuation mapping — extend as needed
        self._replacement_map: Dict[str, str] = {
            # quotes
            "“": '"', "”": '"', "„": '"', "‟": '"',
            "‹": "<", "›": ">",
            "«": '"', "»": '"',
            "‘": "'", "’": "'", "‚": "'", "‛": "'",
            # dashes / hyphens
            "–": "-",  # en dash
            "—": "-",  # em dash
            "―": "-",  # horizontal bar
            "-": "-",  # non-breaking hyphen
            "‒": "-",  # figure dash
            # ellipsis
            "…": "...",
            # spaces
            "\u00A0": " ",  # non-breaking space
            "\u200B": "",   # zero width space
            "\u200C": "",   # zero width non-joiner
            "\u200D": "",   # zero width joiner
            "\uFEFF": "",   # byte order mark
            # primes / quotes
            "″": '"', "′": "'", "‵": "'", "‶": '"',
            # bullets / list markers
            "•": "-", "‣": "-", "◦": "-",
            # other symbols often introduced by smart-typography
            "‚": "'", "†": "+", "‡": "++",
            "‰": "%", "‹": "<", "›": ">",
            # math-like characters that get pasted sometimes
            "×": "x", "÷": "/", "−": "-", "±": "+/-",
            # ordinal superscripts -> ascii approximation
            "ª": "a", "º": "o",
        }

        # Precompile a regex to replace mapping keys (escape keys properly)
        # Sort keys by length desc to avoid partial match issues
        map_keys_sorted = sorted(self._replacement_map.keys(), key=len, reverse=True)
        # Build an alternation like (…|“|”|—|…)
        alternation = "|".join(re.escape(k) for k in map_keys_sorted)
        self._map_regex: Pattern = re.compile(f"(?:{alternation})")

        # Control character categories to remove (except \n, \r, \t)
        # We'll filter by Unicode category: Cc (control), Cf (format) but allow \n \r \t
        # final removal performed in _remove_control_chars

    # -----------------------
    # Public API
    # -----------------------
    def format(self, text: str, intent: str = "general") -> str:
        """
        Clean and normalize provided text.

        :param text: raw model output
        :param intent: optional mode (e.g., "medical" or "book" to add header)
        :return: cleaned string
        """
        if not text or not isinstance(text, str):
            return ""

        # 1. initial strip
        text = text.strip()

        # 2. remove assistant-like prefixes
        text = self._remove_prefixes(text)

        # 3. try to repair broken encodings using ftfy (best-effort)
        text = self._repair_encoding(text)

        # 4. normalize unicode (compatibility decomposition -> composition)
        text = unicodedata.normalize("NFKC", text)

        # 5. replace mapped punctuation (comprehensive map)
        text = self._replace_using_map(text)

        # 6. remove control characters except \n, \r, \t
        text = self._remove_control_chars(text)

        # 7. extract and group links (keeps original link text)
        text = self._extract_and_group_links(text)

        # 8. collapse excessive blank lines and trailing spaces
        text = self._clean_spacing(text)
        text = self._normalize_list_layout(text)

        # 9. stable behavior for "dont have an answer"
        if "dont have an answer" in text.lower():
            return "dont have an answer"

        # 10. intent-based header for medical/book
        if intent in {"medical", "book"} and not text.startswith("### "):
            text = f"### Direct Answer\n{text}"

        return text.strip()

    # -----------------------
    # Internal helpers
    # -----------------------
    def _remove_prefixes(self, text: str) -> str:
        return self.chatter_pattern.sub("", text).strip()

    def _repair_encoding(self, text: str) -> str:
        """
        Use ftfy if available to fix commonly mangled text (mojibake).
        ftfy is intentionally optional; if missing, we skip.
        """
        if _HAS_FTFY:
            try:
                # ftfy fixes many broken encodings and weird multi-encoding issues
                fixed = ftfy.fix_text(text)
                # if ftfy changed something, prefer that. Otherwise keep original.
                return fixed if fixed is not None else text
            except Exception:
                # Best-effort: don't break on ftfy errors
                return text
        return text

    def _replace_using_map(self, text: str) -> str:
        """
        Replace characters found in _replacement_map using a regex
        that matches any of the keys. Replacement is done via a lambda
        to look up mapping.
        """

        def _repl(match):
            ch = match.group(0)
            return self._replacement_map.get(ch, ch)

        # Use sub to replace each matched char/sequence
        return self._map_regex.sub(_repl, text)

    def _remove_control_chars(self, text: str) -> str:
        # Filter out characters whose Unicode category starts with 'C' (Other)
        # but keep \n, \r, \t
        allowed = {"\n", "\r", "\t"}
        filtered_chars: List[str] = []
        for ch in text:
            if ch in allowed:
                filtered_chars.append(ch)
                continue
            cat = unicodedata.category(ch)
            if cat and cat[0] == "C":
                # skip control/format characters
                continue
            filtered_chars.append(ch)
        return "".join(filtered_chars)

    def _extract_and_group_links(self, text: str) -> str:
        extracted_urls: List[str] = []

        # replace markdown links with just the link text while collecting URLs
        def md_replacer(match):
            link_text, url = match.groups()
            if url not in extracted_urls:
                extracted_urls.append(url)
            return link_text

        text = self.md_link_pattern.sub(md_replacer, text)

        # find raw URLs that weren't part of markdown
        raw_urls = self.raw_url_pattern.findall(text)
        for url in raw_urls:
            if url not in extracted_urls:
                extracted_urls.append(url)

        # remove raw urls from body text
        text = self.raw_url_pattern.sub("", text)

        if extracted_urls:
            links_block = "\n\nREFERENCES:\n" + "\n".join(f"- {url}" for url in extracted_urls)
            return text.strip() + links_block

        return text

    def _clean_spacing(self, text: str) -> str:
        text = self.spacing_pattern.sub("\n\n", text)
        text = self.trailing_ws_pattern.sub("", text)
        return text.strip()

    def _normalize_list_layout(self, text: str) -> str:
        """
        Keep list output consistent for markdown rendering:
        - normalize common list bullets to '- '
        - enforce one space after numbered markers like '1.'
        """
        normalized_lines: List[str] = []
        for line in text.splitlines():
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]

            if stripped.startswith(("* ", "+ ", "\u2022 ")):
                normalized_lines.append(f"{indent}- {stripped[2:].strip()}")
                continue

            number_match = self.enumerated_item_pattern.match(line)
            if number_match:
                marker = number_match.group(1)
                item_text = self.enumerated_item_pattern.sub("", line, count=1).strip()
                normalized_lines.append(f"{indent}{marker}. {item_text}")
                continue

            normalized_lines.append(line)

        return "\n".join(normalized_lines).strip()


# -----------------------
# Example usage / quick tests
# -----------------------
if __name__ == "__main__":
    rf = ResponseFormatter()

    sample = (
        "Sure, here is the answer:\n\n"
        "This text contains “curly quotes”, an em-dash —, non-breaking space\u00A0and ellipsis…\n"
        "See [the doc](https://example.com/path?q=1) and https://other.example/page.\n\n"
        "Some control chars:\x0b\x0c End."
    )

    print("RAW:\n", sample)
    cleaned = rf.format(sample, intent="medical")
    print("\nCLEANED:\n", cleaned)
