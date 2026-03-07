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
        self.html_break_pattern: Pattern = re.compile(r"(?i)<br\s*/?>")
        self.html_tag_pattern: Pattern = re.compile(r"</?[a-zA-Z][^>]*>")
        self.meta_grounding_sentence_pattern: Pattern = re.compile(
            r"(?im)^[^\n.!?]*\b(?:provided|given)\s+"
            r"(?:context|sources?|docs?|documents?|text|content|information)\b[^\n.!?]*[.!?]?\s*$"
        )
        self.meta_grounding_phrase_pattern: Pattern = re.compile(
            r"(?i)\b(?:based on|according to|from)\s+(?:the\s+)?"
            r"(?:provided|given)\s+"
            r"(?:context|sources?|docs?|documents?|text|content|information)\b[,:\-\s]*"
        )

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
        text = self._replace_html_breaks(text)
        text = self._strip_html_tags(text)

        # 7. extract and group links (keeps original link text)
        text = self._extract_and_group_links(text)

        # 8. collapse excessive blank lines and trailing spaces
        text = self._remove_meta_grounding_language(text)
        text = self._normalize_tabular_output(text)
        text = self._improve_readability_layout(text)
        text = self._clean_spacing(text)
        text = self._normalize_list_layout(text)

        # 9. stable behavior for "dont have an answer"
        if "dont have an answer" in text.lower():
            return "dont have an answer"

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

    def _replace_html_breaks(self, text: str) -> str:
        return self.html_break_pattern.sub("\n", text)

    def _strip_html_tags(self, text: str) -> str:
        return self.html_tag_pattern.sub("", text)

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

    def _normalize_tabular_output(self, text: str) -> str:
        """
        Convert tab-separated pseudo tables into proper markdown tables.
        Example handled:
        Chapter<TAB>Topic
        1<TAB>Intro
        2<TAB>Basics
        """
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        lines = [ln for ln in raw.split("\n") if ln.strip()]
        if len(lines) < 2:
            return raw

        header_line = lines[0]
        if "\t" not in header_line:
            return raw

        headers = [h.strip() for h in header_line.split("\t") if h.strip()]
        if len(headers) < 2:
            return raw

        width = len(headers)
        rows: List[List[str]] = []
        current_row: Optional[List[str]] = None

        for line in lines[1:]:
            if "\t" in line:
                parts = line.split("\t", width - 1)
                if len(parts) < width:
                    continue
                current_row = [part.strip() for part in parts]
                rows.append(current_row)
                continue

            # Continuation line for previous row's last cell
            if current_row is not None:
                current_row[-1] = f"{current_row[-1]}; {line.strip()}".strip(" ;")

        if not rows:
            return raw

        def _clean_cell(cell: str) -> str:
            cleaned = re.sub(r"\s{2,}", " ", str(cell or "")).strip()
            return cleaned.replace("|", r"\|")

        md_header = "| " + " | ".join(_clean_cell(h) for h in headers) + " |"
        md_sep = "| " + " | ".join(["---"] * len(headers)) + " |"
        md_rows = []
        for row in rows:
            padded = row + [""] * max(0, width - len(row))
            md_rows.append("| " + " | ".join(_clean_cell(c) for c in padded[:width]) + " |")

        return "\n".join([md_header, md_sep, *md_rows]).strip()

    def _remove_meta_grounding_language(self, text: str) -> str:
        cleaned = self.meta_grounding_sentence_pattern.sub("", text)
        cleaned = self.meta_grounding_phrase_pattern.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    def _improve_readability_layout(self, text: str) -> str:
        cleaned = (text or "").replace("\r\n", "\n").strip()
        if not cleaned:
            return ""

        # If numbered items were generated inline, put each on its own line.
        cleaned = re.sub(r"(?<=[\.\:\;])\s+(\d+\.\s+)", r"\n\1", cleaned)

        # If response is one long paragraph, split it into short readable blocks.
        if "\n" not in cleaned and len(cleaned) > 260:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
            if len(sentences) >= 4:
                blocks: List[str] = []
                for i in range(0, len(sentences), 2):
                    blocks.append(" ".join(sentences[i:i + 2]))
                cleaned = "\n\n".join(blocks)

        return cleaned.strip()


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
