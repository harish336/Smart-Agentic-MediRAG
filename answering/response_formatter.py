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
        self.meta_reference_sentence_pattern: Pattern = re.compile(
            r"(?im)^[^\n.!?]*\b(?:context|content|document|source)\b[^\n.!?]*\b"
            r"(?:says|mentions|states|provided|given|available|shared)\b[^\n.!?]*[.!?]?\s*$"
        )
        self.table_intro_pattern: Pattern = re.compile(
            r"(?i)^\s*(?:here(?:'s| is)\s+)?(?:the\s+)?(?:formatted\s+)?response(?:\s+as)?\s+a?\s*markdown\s+table:?\s*$"
        )
        self.references_heading_pattern: Pattern = re.compile(
            r"(?im)^\s*(references?|sources?)\s*:?\s*$"
        )
        self.key_value_line_pattern: Pattern = re.compile(
            r"^([A-Za-z][A-Za-z0-9 /&()'\-]{2,60}):\s+(.+)$"
        )
        self.fenced_code_pattern: Pattern = re.compile(r"```[\s\S]*?```")

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

        # Transformation outputs should be preserved as-authored as much as possible.
        if (intent or "").strip().lower() == "transformation":
            text = self._normalize_common_generation_artifacts(text)
            text = self._clean_spacing(text)
            text = self._normalize_list_layout(text)
            text = self._remove_orphan_pipe_rows(text)
            text = self._clean_spacing(text)
            if "dont have an answer" in text.lower():
                return "dont have an answer"
            return text.strip()

        # 8. collapse excessive blank lines and trailing spaces
        text = self._remove_meta_grounding_language(text)
        text = self._clean_spacing(text)

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

    def _contains_fenced_code(self, text: str) -> bool:
        return bool(self.fenced_code_pattern.search(text or ""))

    def _normalize_reference_sections(self, text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        lines = raw.split("\n")
        normalized: List[str] = []
        in_references = False

        def _last_non_empty(items: List[str]) -> str:
            for item in reversed(items):
                if item.strip():
                    return item.strip()
            return ""

        for line in lines:
            stripped = line.strip()
            if self.references_heading_pattern.match(stripped):
                if in_references:
                    # Ignore duplicated heading while already inside references.
                    continue
                last_non_empty = _last_non_empty(normalized)
                if last_non_empty.lower() == "## references":
                    in_references = True
                    continue
                if normalized and normalized[-1].strip():
                    normalized.append("")
                normalized.append("## References")
                normalized.append("")
                in_references = True
                continue

            if not in_references:
                normalized.append(line)
                continue

            if not stripped:
                normalized.append("")
                continue
            if stripped in {"-", "*"}:
                continue

            # End references section if a new heading starts.
            if re.match(r"^\s*#{1,6}\s+", line):
                in_references = False
                normalized.append(line)
                continue

            if re.match(r"^\s*[-*]\s+", line):
                normalized_bullet = re.sub(r"^\s*[-*]\s+", "- ", line).strip()
                if normalized_bullet in {"-", "- .", "- -"}:
                    continue
                normalized.append(normalized_bullet)
                continue

            if re.match(r"^https?://", stripped):
                normalized.append(f"- {stripped}")
                continue

            normalized.append(f"- {stripped}")

        return "\n".join(normalized).strip()

    def _normalize_key_value_lines(self, text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        lines = raw.split("\n")
        normalized_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                normalized_lines.append("")
                continue
            # Preserve markdown structures.
            if stripped.startswith(("```", "#", "- ", "* ", "|")) or re.match(r"^\d+\.\s+", stripped):
                normalized_lines.append(line)
                continue

            match = self.key_value_line_pattern.match(stripped)
            if not match:
                normalized_lines.append(line)
                continue

            label = match.group(1).strip()
            value = match.group(2).strip()
            # Avoid forcing long narrative sentences into key-value markdown.
            if len(label.split()) > 6 or len(value) > 450:
                normalized_lines.append(line)
                continue

            normalized_lines.append(f"**{label}:** {value}")

        return "\n".join(normalized_lines).strip()

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

    def _normalize_pipe_structured_output(self, text: str) -> str:
        """
        Normalize malformed pipe-structured two-column output into Markdown tables.
        Handles cases like:
        Topic | Details | | Guideline Title | Value | | Published | 2011
        """
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        # Skip only when content already includes a proper markdown table separator row.
        # Require pipes so plain horizontal rules do not disable table normalization.
        if re.search(r"(?m)^\s*\|.*\|\s*$", raw) and re.search(
            r"(?m)^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
            raw,
        ):
            return raw

        def _split_cells(line: str) -> List[str]:
            core = (line or "").strip()
            if "|" not in core:
                return []
            if core.startswith("|"):
                core = core[1:]
            if core.endswith("|"):
                core = core[:-1]
            return [part.strip() for part in core.split("|")]

        candidate_rows = (
            raw.replace("\n| |", "\n||")
            .replace("\n|\t|", "\n||")
        )
        lines = [ln.strip() for ln in re.split(r"\s*\|\|\s*|\n+", candidate_rows) if ln.strip()]
        parsed_rows: List[List[str]] = []
        for line in lines:
            if "|" not in line:
                continue
            cells = [c for c in _split_cells(line) if c]
            if len(cells) >= 2:
                parsed_rows.append(cells)

        if len(parsed_rows) < 2:
            return raw

        rows = [[row[0].strip(), " | ".join(cell.strip() for cell in row[1:] if cell and cell.strip())] for row in parsed_rows]
        if len(rows) >= 2 and self.table_intro_pattern.match(rows[0][0]) and rows[0][1]:
            rows = rows[1:]
            if len(rows) < 2:
                return raw
        first_row = [cell.strip().lower() for cell in rows[0]]
        has_header_hint = any(
            re.search(r"(topic|section|field|aspect|title|description|detail|summary|item|name)", cell)
            for cell in first_row
        )
        looks_like_header = has_header_hint
        headers = rows[0] if looks_like_header else ["Aspect", "Details"]
        data_rows = rows[1:] if looks_like_header else rows

        def _format_cell(value: str) -> str:
            cleaned = re.sub(r"\s{2,}", " ", value or "").strip()
            cleaned = cleaned.replace("|", r"\|")
            return cleaned

        if not data_rows:
            return raw

        md_header = "| " + " | ".join(_format_cell(h) for h in headers) + " |"
        md_sep = "| " + " | ".join(["---"] * len(headers)) + " |"
        md_rows = [f"| {_format_cell(row[0])} | {_format_cell(row[1])} |" for row in data_rows]
        return "\n".join([md_header, md_sep, *md_rows]).strip()

    def _parse_markdown_table_line(self, line: str) -> List[str]:
        text = (line or "").strip()
        if text.startswith("|"):
            text = text[1:]
        if text.endswith("|"):
            text = text[:-1]
        return [cell.strip() for cell in text.split("|")]

    def _is_markdown_table_separator(self, line: str) -> bool:
        text = (line or "").strip()
        if not text:
            return False
        return bool(
            re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", text)
        )

    def _normalize_table_shape(self, headers: List[str], rows: List[List[str]]) -> Dict[str, List[List[str]]]:
        header_cells = list(headers or [])
        row_cells = [list(row or []) for row in (rows or [])]
        max_cols = max([len(header_cells)] + [len(row) for row in row_cells] + [1])
        padded_headers = header_cells + [""] * (max_cols - len(header_cells))
        padded_rows = [row + [""] * (max_cols - len(row)) for row in row_cells]
        return {"headers": padded_headers[:max_cols], "rows": [row[:max_cols] for row in padded_rows]}

    def _build_markdown_table(self, headers: List[str], rows: List[List[str]]) -> str:
        normalized = self._normalize_table_shape(headers, rows)

        def _escape_cell(value: str) -> str:
            return str(value or "").replace("|", r"\|").strip()

        header_line = "| " + " | ".join(_escape_cell(cell) for cell in normalized["headers"]) + " |"
        separator_line = "| " + " | ".join(["---"] * len(normalized["headers"])) + " |"
        row_lines = [
            "| " + " | ".join(_escape_cell(cell) for cell in row) + " |"
            for row in normalized["rows"]
        ]
        return "\n".join([header_line, separator_line, *row_lines]).strip()

    def _parse_markdown_tables(self, text: str) -> List[Dict]:
        raw = (text or "").replace("\r\n", "\n")
        lines = raw.split("\n")
        tables: List[Dict] = []
        i = 0

        while i < len(lines) - 1:
            header_line = lines[i]
            separator_line = lines[i + 1]
            if "|" not in header_line or not self._is_markdown_table_separator(separator_line):
                i += 1
                continue

            headers = self._parse_markdown_table_line(header_line)
            row_index = i + 2
            rows: List[List[str]] = []
            while row_index < len(lines):
                row_line = lines[row_index]
                if not row_line.strip() or "|" not in row_line:
                    break
                rows.append(self._parse_markdown_table_line(row_line))
                row_index += 1

            if not rows:
                i += 1
                continue

            normalized = self._normalize_table_shape(headers, rows)
            tables.append(
                {
                    "start_line": i,
                    "end_line": row_index - 1,
                    "headers": normalized["headers"],
                    "rows": normalized["rows"],
                }
            )
            i = row_index

        return tables

    def _split_narrative_table_cell(self, cell: str) -> Optional[List[str]]:
        text = re.sub(r"\s+", " ", str(cell or "")).strip()
        if not text:
            return None
        colon_match = re.match(r"^(.{3,90}?):\s+(.{10,})$", text)
        if colon_match:
            return [colon_match.group(1).strip(), colon_match.group(2).strip()]
        dash_match = re.match(r"^(.{3,120}?)\s+-\s+(.{10,})$", text)
        if dash_match:
            return [dash_match.group(1).strip(), dash_match.group(2).strip()]
        return None

    def _repair_sparse_two_column_tables(self, text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        tables = self._parse_markdown_tables(raw)
        if not tables:
            return raw

        lines = raw.split("\n")
        chunks: List[str] = []
        cursor = 0

        for table in tables:
            start_line = int(table["start_line"])
            end_line = int(table["end_line"])
            if start_line > cursor:
                chunks.append("\n".join(lines[cursor:start_line]))

            headers = [str(cell or "").strip() for cell in table.get("headers", [])]
            rows = [[str(cell or "").strip() for cell in row] for row in table.get("rows", [])]
            if len(headers) != 2:
                chunks.append("\n".join(lines[start_line:end_line + 1]))
                cursor = end_line + 1
                continue

            section_heading = ""
            if self.table_intro_pattern.match(headers[0]) and headers[1]:
                section_heading = f"## {headers[1]}"
                headers = ["Aspect", "Details"]

            repaired = False
            normalized_rows: List[List[str]] = []
            pending_heading = ""
            pending_items: List[str] = []

            def flush_pending() -> None:
                nonlocal pending_heading, pending_items
                if not pending_heading:
                    return
                details = "; ".join(item for item in pending_items if item).strip()
                normalized_rows.append([pending_heading, details])
                pending_heading = ""
                pending_items = []

            for row in rows:
                raw_aspect = str(row[0] if len(row) > 0 else "").strip()
                raw_details = str(row[1] if len(row) > 1 else "").strip()
                if not raw_aspect and not raw_details:
                    continue

                is_aspect_bullet = bool(re.match(r"^[-*•]\s+", raw_aspect))
                aspect = re.sub(r"^[-*•]\s+", "", raw_aspect).strip().strip(":")
                details = re.sub(r"^[-*•]\s+", "", raw_details).strip()

                if not details:
                    split = self._split_narrative_table_cell(aspect)
                    if split:
                        aspect, details = split
                        repaired = True

                if details:
                    flush_pending()
                    normalized_rows.append([aspect, details])
                    continue

                if not is_aspect_bullet:
                    flush_pending()
                    pending_heading = aspect
                    pending_items = []
                    repaired = True
                    continue

                if pending_heading:
                    pending_items.append(aspect)
                    repaired = True
                else:
                    normalized_rows.append([aspect, ""])

            flush_pending()

            if repaired or section_heading:
                table_markdown = self._build_markdown_table(headers, normalized_rows)
                if section_heading:
                    chunks.append(f"{section_heading}\n\n{table_markdown}")
                else:
                    chunks.append(table_markdown)
            else:
                chunks.append("\n".join(lines[start_line:end_line + 1]))
            cursor = end_line + 1

        if cursor < len(lines):
            chunks.append("\n".join(lines[cursor:]))

        return "\n\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip()).strip()

    def _remove_placeholder_two_column_rows(self, text: str) -> str:
        """
        Remove boilerplate rows inside two-column tables such as:
        | Sub-Topic | Description |
        These rows are structural noise, not content.
        """
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        tables = self._parse_markdown_tables(raw)
        if not tables:
            return raw

        lines = raw.split("\n")
        chunks: List[str] = []
        cursor = 0

        placeholder_left = {
            "sub-topic",
            "subtopic",
            "topic",
            "section",
            "heading",
            "title",
            "item",
        }
        placeholder_right = {
            "description",
            "details",
            "detail",
            "information",
            "info",
            "summary",
            "value",
        }

        def _norm(value: str) -> str:
            cleaned = re.sub(r"\s+", " ", str(value or "").strip().lower())
            return cleaned.replace("_", "-")

        for table in tables:
            start_line = int(table["start_line"])
            end_line = int(table["end_line"])
            if start_line > cursor:
                chunks.append("\n".join(lines[cursor:start_line]))

            headers = [str(cell or "").strip() for cell in table.get("headers", [])]
            rows = [[str(cell or "").strip() for cell in row] for row in table.get("rows", [])]

            if len(headers) != 2:
                chunks.append("\n".join(lines[start_line:end_line + 1]))
                cursor = end_line + 1
                continue

            filtered_rows: List[List[str]] = []
            for row in rows:
                left = _norm(row[0] if len(row) > 0 else "")
                right = _norm(row[1] if len(row) > 1 else "")
                is_placeholder_pair = left in placeholder_left and right in placeholder_right
                # Also drop accidental duplicate header rows embedded in body.
                is_duplicate_header = (
                    left == _norm(headers[0]) and right == _norm(headers[1])
                )
                if is_placeholder_pair or is_duplicate_header:
                    continue
                filtered_rows.append(row[:2])

            if filtered_rows:
                chunks.append(self._build_markdown_table(headers, filtered_rows))
            else:
                chunks.append("\n".join(lines[start_line:end_line + 1]))

            cursor = end_line + 1

        if cursor < len(lines):
            chunks.append("\n".join(lines[cursor:]))

        return "\n\n".join(chunk.strip() for chunk in chunks if chunk and chunk.strip()).strip()

    def _remove_meta_grounding_language(self, text: str) -> str:
        cleaned = self.meta_grounding_sentence_pattern.sub("", text)
        cleaned = self.meta_grounding_phrase_pattern.sub("", cleaned)
        cleaned = self.meta_reference_sentence_pattern.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    def _improve_readability_layout(self, text: str) -> str:
        cleaned = (text or "").replace("\r\n", "\n").strip()
        if not cleaned:
            return ""

        # If numbered items were generated inline, put each on its own line.
        cleaned = re.sub(r"(?<=[\.\:\;])\s+(\d+\.\s+)", r"\n\1", cleaned)
        cleaned = self._split_inline_numbered_sequences(cleaned)
        cleaned = self._normalize_numbered_dash_delimited_items(cleaned)
        cleaned = self._split_inline_bullet_sequences(cleaned)

        # If response is one long paragraph, split it into short readable blocks.
        if "\n" not in cleaned and len(cleaned) > 260:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
            if len(sentences) >= 4:
                blocks: List[str] = []
                for i in range(0, len(sentences), 2):
                    blocks.append(" ".join(sentences[i:i + 2]))
                cleaned = "\n\n".join(blocks)

        return cleaned.strip()

    def _split_inline_numbered_sequences(self, text: str) -> str:
        """
        Split long inline numbered sequences into one item per line.
        Example:
        "1. A ... 2. B ... 3. C ..."
        =>
        "1. A ..."
        "2. B ..."
        "3. C ..."
        """
        lines = (text or "").split("\n")
        if not lines:
            return ""

        out: List[str] = []
        item_pattern = re.compile(r"\b\d+\.\s+")

        for line in lines:
            raw = str(line or "")
            stripped = raw.strip()
            if not stripped:
                out.append(raw)
                continue

            # Skip markdown/table/list lines.
            if "|" in stripped or re.match(r"^\s*[-*]\s+", raw):
                out.append(raw)
                continue

            matches = list(item_pattern.finditer(raw))
            if len(matches) < 2:
                out.append(raw)
                continue

            prefix = raw[: matches[0].start()].strip()
            if prefix:
                out.append(prefix)

            for idx, match in enumerate(matches):
                start = match.start()
                end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
                segment = raw[start:end].strip()
                if segment:
                    out.append(segment)

        return "\n".join(out).strip()

    def _normalize_numbered_dash_delimited_items(self, text: str) -> str:
        """
        Improve readability for long numbered lines like:
        1. Topic - Point A - Point B - Point C

        Output:
        1. Topic
           - Point A
           - Point B
           - Point C
        """
        lines = (text or "").replace("\r\n", "\n").split("\n")
        if not lines:
            return ""

        normalized: List[str] = []
        numbered_pattern = re.compile(r"^(\s*\d+\.\s+)(.+)$")

        for line in lines:
            match = numbered_pattern.match(line or "")
            if not match:
                normalized.append(line)
                continue

            marker, body = match.groups()
            stripped_body = body.strip()
            if " - " not in stripped_body:
                normalized.append(line)
                continue

            parts = [part.strip() for part in re.split(r"\s+-\s+", stripped_body) if part.strip()]
            if len(parts) < 3 or len(stripped_body) < 90:
                normalized.append(line)
                continue

            normalized.append(f"{marker}{parts[0]}")
            continuation_indent = " " * len(marker)
            normalized.extend(f"{continuation_indent}- {part}" for part in parts[1:])

        return "\n".join(normalized).strip()

    def _split_inline_bullet_sequences(self, text: str) -> str:
        """
        Split long inline bullet chains into one markdown bullet per line.
        Example:
        Intro - A - B - C
        =>
        Intro

        - A
        - B
        - C
        """
        lines = (text or "").split("\n")
        if not lines:
            return ""

        out: List[str] = []
        inline_bullet_splitter = re.compile(r"\s+[-*•]\s+")

        for line in lines:
            raw = str(line or "")
            stripped = raw.strip()
            if not stripped:
                out.append(raw)
                continue

            if "|" in stripped or re.match(r"^\s*[-*]\s+", raw) or re.match(r"^\s*\d+\.\s+", raw):
                out.append(raw)
                continue

            parts = [part.strip() for part in inline_bullet_splitter.split(stripped) if part.strip()]
            if len(parts) < 4 or len(stripped) < 120:
                out.append(raw)
                continue

            out.append(parts[0])
            out.append("")
            out.extend(f"- {part}" for part in parts[1:])

        return "\n".join(out).strip()

    def _normalize_pipe_delimited_bullets(self, text: str) -> str:
        """
        Convert malformed bullets like:
        - Item A | Item B | Item C
        into:
        - Item A
        - Item B
        - Item C
        """
        lines = (text or "").splitlines()
        if not lines:
            return ""

        normalized_lines: List[str] = []
        bullet_line = re.compile(r"^(\s*[-*]\s+)(.+)$")

        for line in lines:
            match = bullet_line.match(line)
            if not match:
                normalized_lines.append(line)
                continue

            prefix, body = match.groups()
            if "|" not in body:
                normalized_lines.append(line)
                continue

            parts = [part.strip() for part in body.split("|") if part.strip()]
            if len(parts) <= 1:
                normalized_lines.append(line)
                continue

            indent = re.match(r"^\s*", prefix).group(0)
            normalized_lines.extend([f"{indent}- {part}" for part in parts])

        return "\n".join(normalized_lines).strip()

    def _normalize_dash_delimited_narrative(self, text: str) -> str:
        """
        Convert long dash-delimited lines into readable markdown bullets.
        Example:
        Intro - Item A - Item B - Item C
        =>
        Intro

        - Item A
        - Item B
        - Item C
        """
        lines = (text or "").replace("\r\n", "\n").split("\n")
        if not lines:
            return ""

        normalized_lines: List[str] = []
        for line in lines:
            stripped = (line or "").strip()
            if not stripped:
                normalized_lines.append("")
                continue

            is_likely_markdown = "|" in stripped or stripped.startswith(("- ", "* ")) or bool(
                re.match(r"^\d+\.\s+", stripped)
            )
            if is_likely_markdown or " - " not in stripped or len(stripped) < 180:
                normalized_lines.append(line)
                continue

            parts = [part.strip() for part in re.split(r"\s+-\s+", stripped) if part.strip()]
            if len(parts) < 4:
                normalized_lines.append(line)
                continue

            normalized_lines.append(parts[0])
            normalized_lines.append("")
            normalized_lines.extend(f"- {part}" for part in parts[1:])

        return "\n".join(normalized_lines).strip()

    def _normalize_common_generation_artifacts(self, text: str) -> str:
        cleaned = (text or "").replace("\r\n", "\n")
        if not cleaned:
            return ""

        # Common malformed separators seen in model output:
        # "Title: * Value" -> "Title: Value"
        cleaned = re.sub(r":[ \t]*\*[ \t]+", ": ", cleaned)
        # "Heading:- detail" -> "Heading: detail"
        cleaned = re.sub(r":[ \t]*-[ \t]+", ": ", cleaned)
        # "Sentence. - Next" -> "Sentence. Next"
        cleaned = re.sub(r"\.[ \t]*-[ \t]+", ". ", cleaned)
        # Deduplicate accidental bullet markers: "- - item" -> "- item"
        cleaned = re.sub(r"(?m)^([ \t]*)-[ \t]+-[ \t]+", r"\1- ", cleaned)

        return cleaned.strip()

    def _merge_numbered_item_continuations(self, text: str) -> str:
        """
        Merge standalone numbered headings followed by paragraph lines into
        a single numbered markdown item for cleaner rendering.
        Example:
        1. Topic:
        Detail sentence one.
        Detail sentence two.
        =>
        1. Topic: Detail sentence one. Detail sentence two.
        """
        lines = (text or "").replace("\r\n", "\n").split("\n")
        if not lines:
            return ""

        output: List[str] = []
        i = 0
        numbered_re = re.compile(r"^(\s*\d+\.\s+)(.+)$")
        list_or_heading_re = re.compile(r"^\s*(?:\d+\.\s+|[-*]\s+|#{1,6}\s+|\|)")

        while i < len(lines):
            current = lines[i]
            current_stripped = (current or "").strip()
            match = numbered_re.match(current_stripped)
            if not match:
                output.append(current)
                i += 1
                continue

            marker, head = match.groups()
            merged_chunks: List[str] = [head.strip()]
            j = i + 1
            saw_continuation = False

            while j < len(lines):
                next_line = lines[j]
                next_stripped = (next_line or "").strip()
                if not next_stripped:
                    if saw_continuation:
                        j += 1
                        break
                    j += 1
                    continue
                if list_or_heading_re.match(next_stripped):
                    break
                merged_chunks.append(re.sub(r"\s+", " ", next_stripped))
                saw_continuation = True
                j += 1

            if saw_continuation:
                heading = merged_chunks[0]
                detail = " ".join(merged_chunks[1:]).strip()
                output.append(f"{marker}{heading}")
                if detail:
                    marker_indent = len(marker) - len(marker.lstrip(" "))
                    output.append(f"{' ' * (marker_indent + 3)}- {detail}")
                i = j
                continue

            output.append(current)
            i += 1

        return "\n".join(output).strip()

    def _convert_long_paragraphs_to_bullets(self, text: str) -> str:
        """
        If model output is long and split across multiple paragraphs, convert
        each paragraph into one markdown bullet for scannability.
        """
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        # Preserve explicit list/table outputs.
        if "|" in raw:
            return raw

        lines = raw.split("\n")
        has_list_line = any(re.match(r"^\s*(?:[-*]\s+|\d+\.\s+)", line) for line in lines)
        if has_list_line:
            changed = False
            adjusted_lines: List[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    adjusted_lines.append("")
                    continue
                if re.match(r"^\s*(?:[-*]\s+|\d+\.\s+|#{1,6}\s+)", stripped):
                    adjusted_lines.append(line)
                    continue
                if len(stripped) >= 160 and not re.search(r"(?<!\])\|", stripped):
                    compact = re.sub(r"\s+", " ", stripped)
                    adjusted_lines.append(f"- {compact}")
                    changed = True
                    continue
                adjusted_lines.append(line)

            # Preserve list structure and avoid flattening paragraphs that include lists.
            if changed:
                return "\n".join(adjusted_lines).strip()
            return raw

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
        if len(paragraphs) < 2 or len(raw) < 320:
            return raw

        has_list = bool(re.search(r"(?m)^\s*(?:[-*]\s+|\d+\.\s+)", raw))
        converted_items: List[str] = []
        for paragraph in paragraphs:
            one_line = re.sub(r"\s+", " ", paragraph).strip()
            if not one_line:
                continue

            is_list_paragraph = bool(re.match(r"^\s*(?:[-*]\s+|\d+\.\s+)", paragraph))
            if has_list and is_list_paragraph:
                converted_items.append(one_line)
                continue

            if len(one_line) >= 120:
                converted_items.append(f"- {one_line}")
            else:
                converted_items.append(one_line if is_list_paragraph else f"- {one_line}")

        return "\n".join(converted_items).strip()

    def _normalize_long_plain_narrative(self, text: str) -> str:
        """
        Break extremely dense plain-text responses into markdown bullets
        when no explicit markdown structure is present.
        """
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""
        if self._contains_fenced_code(raw):
            return raw

        has_markdown_structure = bool(
            re.search(r"(?m)^\s*(?:[-*]\s+|\d+\.\s+|#{1,6}\s+|\|)", raw)
        )
        if has_markdown_structure:
            return raw

        if len(raw) < 360:
            return raw

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw) if s.strip()]
        if len(sentences) < 5:
            return raw

        return "\n".join(f"- {sentence}" for sentence in sentences).strip()

    def _canonicalize_ordered_section_blocks(self, text: str) -> str:
        """
        Ensure ordered section blocks render as true markdown list items by
        folding detached paragraph lines into the numbered item and emitting
        an indented detail bullet for readability.
        """
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""

        lines = raw.split("\n")
        out: List[str] = []
        i = 0
        number_re = re.compile(r"^(\d+)\.\s+(.+)$")
        stop_re = re.compile(r"^(?:\d+\.\s+|[-*]\s+|#{1,6}\s+|\|)")

        while i < len(lines):
            line = lines[i].strip()
            match = number_re.match(line)
            if not match:
                out.append(lines[i])
                i += 1
                continue

            idx = match.group(1)
            head = match.group(2).strip()
            details: List[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    if details:
                        break
                    continue
                if stop_re.match(nxt):
                    break
                details.append(re.sub(r"\s+", " ", nxt))
                j += 1

            if details:
                out.append(f"{idx}. {head}")
                out.append(f"   - {' '.join(details)}")
                i = j
                continue

            # Inline form: "1. Subtopic: long narrative..."
            colon_split = re.match(r"^(.{3,140}?):\s+(.+)$", head)
            if colon_split:
                subtopic = colon_split.group(1).strip() + ":"
                narrative = re.sub(r"\s+", " ", colon_split.group(2)).strip()
                if len(narrative) >= 40:
                    out.append(f"{idx}. {subtopic}")
                    out.append(f"   - {narrative}")
                    i += 1
                    continue

            out.append(lines[i])
            i += 1

        return "\n".join(out).strip()

    def _normalize_markdown_layout(self, text: str) -> str:
        """
        Stateful markdown layout normalization that preserves structure:
        - headings
        - ordered/unordered lists (including nested)
        - markdown tables
        - tables nested under list items
        - paragraph spacing between structural blocks
        """
        raw = (text or "").replace("\r\n", "\n").replace("\t", "    ").strip()
        if not raw:
            return ""

        lines = raw.split("\n")

        def leading_spaces(value: str) -> int:
            return len(value) - len(value.lstrip(" "))

        def is_blank(value: str) -> bool:
            return not value.strip()

        def is_heading(value: str) -> bool:
            return bool(re.match(r"^\s{0,3}#{1,6}\s+\S", value))

        def parse_list_marker(value: str) -> Optional[Dict[str, int]]:
            match = re.match(r"^(\s*)(?:([-*+])|(\d+\.))\s+(\S.*)?$", value)
            if not match:
                return None
            indent = len(match.group(1) or "")
            marker = match.group(2) or match.group(3) or "-"
            content = match.group(4) or ""
            return {
                "indent": indent,
                "marker_len": len(marker) + 1,  # marker + space
                "ordered": 1 if bool(match.group(3)) else 0,
                "has_content": 1 if bool(content.strip()) else 0,
            }

        def is_table_row(value: str) -> bool:
            stripped = value.strip()
            if "|" not in stripped:
                return False
            if re.match(r"^\s*[-*+]\s+", stripped) or re.match(r"^\s*\d+\.\s+", stripped):
                return False
            if stripped.startswith("|") and stripped.endswith("|"):
                return True
            # Also allow compact forms like "A | B"
            return stripped.count("|") >= 1

        def is_table_separator(value: str) -> bool:
            stripped = value.strip()
            return bool(re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", stripped))

        def is_structural_start(value: str) -> bool:
            if is_blank(value):
                return True
            if is_heading(value):
                return True
            if parse_list_marker(value):
                return True
            if is_table_row(value):
                return True
            return False

        # Pass 1: Attach loose paragraph/table lines to preceding list items.
        attached: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            marker = parse_list_marker(line)
            if not marker:
                attached.append(line.rstrip())
                i += 1
                continue

            list_indent = int(marker["indent"])
            child_indent = list_indent + 3
            attached.append(line.rstrip())
            i += 1

            pending_blank = False
            while i < len(lines):
                nxt = lines[i]
                nxt_stripped = nxt.strip()

                if not nxt_stripped:
                    pending_blank = True
                    i += 1
                    continue

                nxt_indent = leading_spaces(nxt)
                nxt_marker = parse_list_marker(nxt)
                next_is_heading = is_heading(nxt)
                next_is_table = is_table_row(nxt)

                # New sibling or parent-level structural block -> stop attaching.
                if (nxt_marker and nxt_indent <= list_indent) or (next_is_heading and nxt_indent <= list_indent):
                    break

                # If a table starts immediately after list item, nest it under the item.
                if next_is_table and not nxt_marker:
                    if pending_blank:
                        attached.append("")
                        pending_blank = False
                    table_indent = max(child_indent, list_indent + 2)
                    while i < len(lines) and lines[i].strip() and is_table_row(lines[i]):
                        attached.append((" " * table_indent) + lines[i].strip())
                        i += 1
                    continue

                # Plain continuation text at same/outer indent: nest under current item.
                if not nxt_marker and not next_is_heading and nxt_indent <= list_indent:
                    if pending_blank:
                        attached.append("")
                        pending_blank = False
                    attached.append((" " * child_indent) + re.sub(r"\s+", " ", nxt_stripped))
                    i += 1
                    continue

                # Already nested content under this item; preserve as-is.
                if nxt_indent > list_indent:
                    if pending_blank:
                        attached.append("")
                        pending_blank = False
                    attached.append(nxt.rstrip())
                    i += 1
                    continue

                break

        # Pass 2: Standardize spacing between block types.
        def classify(value: str) -> str:
            if is_blank(value):
                return "blank"
            if is_heading(value):
                return "heading"
            if parse_list_marker(value):
                return "list"
            if is_table_row(value):
                return "table"
            return "paragraph"

        normalized: List[str] = []
        for idx, line in enumerate(attached):
            current_type = classify(line)
            prev_type = classify(normalized[-1]) if normalized else "blank"

            if current_type == "blank":
                if normalized and normalized[-1] != "":
                    normalized.append("")
                continue

            needs_break = False
            if current_type == "heading" and normalized and normalized[-1] != "":
                needs_break = True
            if current_type == "table" and prev_type in {"paragraph", "list", "heading"}:
                needs_break = True
            if current_type == "paragraph" and prev_type in {"heading", "table"}:
                needs_break = True
            if current_type == "list" and prev_type in {"heading", "table", "paragraph"}:
                if prev_type == "paragraph":
                    # Keep tight list under immediate intro line ending with ':'.
                    intro = (normalized[-1] or "").strip()
                    if not intro.endswith(":"):
                        needs_break = True
                else:
                    needs_break = True

            if needs_break and normalized and normalized[-1] != "":
                normalized.append("")

            normalized.append(line.rstrip())

        # Remove excess blank lines and trailing blanks.
        compact: List[str] = []
        for line in normalized:
            if not line.strip():
                if compact and compact[-1] != "":
                    compact.append("")
                continue
            compact.append(line)

        while compact and compact[-1] == "":
            compact.pop()

        return "\n".join(compact).strip()

    def _remove_orphan_pipe_rows(self, text: str) -> str:
        """
        Remove standalone pipe-delimited lines that are not part of a valid
        markdown table block (header + separator). This prevents broken table
        fragments from leaking into the rendered output.
        """
        raw = (text or "").replace("\r\n", "\n")
        if not raw:
            return ""

        lines = raw.split("\n")
        keep = [True] * len(lines)
        valid_table_lines = set()
        for table in self._parse_markdown_tables(raw):
            start = int(table.get("start_line", 0))
            end = int(table.get("end_line", -1))
            for idx in range(start, end + 1):
                valid_table_lines.add(idx)
            valid_table_lines.add(start + 1)  # separator line

        for idx, line in enumerate(lines):
            if idx in valid_table_lines:
                continue
            stripped = (line or "").strip()
            if not stripped:
                continue
            if self._is_markdown_table_separator(stripped):
                keep[idx] = False
                continue
            if "|" not in stripped:
                continue
            # Remove boundary-style pipe rows that are outside valid table blocks.
            if stripped.startswith("|") or stripped.endswith("|") or stripped.count("|") >= 2:
                keep[idx] = False

        filtered = [line for idx, line in enumerate(lines) if keep[idx]]
        return "\n".join(filtered).strip()


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
