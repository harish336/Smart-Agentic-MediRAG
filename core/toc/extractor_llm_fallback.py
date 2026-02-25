"""
LLM-based TOC Extractor (FALLBACK)

- Uses FREE local LLM via Ollama
- LangChain-based
- Strict structured output
- Verbose step-by-step printing
- Standalone runnable

REQUIREMENTS:
- Ollama installed
- A model pulled (e.g. mistral, llama3, phi)
"""
import sys
import json
import fitz
import re

from pydoc import text
from pprint import pprint
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from concurrent.futures import ThreadPoolExecutor, as_completed


# -------------------------------------------------
# CONFIG (FREE + LOCAL)
# -------------------------------------------------
OLLAMA_MODEL = "mistral"   # or llama3, phi, gemma


class LLMTOCExtractor:
    def __init__(self, pdf_path: str, toc_start_page: int, max_pages: int = 3):
        self.pdf_path = pdf_path
        self.toc_start_page = toc_start_page
        self.max_pages = max_pages
        self.doc = None
        self.llm = None

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        self.doc = fitz.open(self.pdf_path)
        print("[OK] PDF loaded successfully")
        print(f"[INFO] Total pages: {self.doc.page_count}")

    # -------------------------------------------------
    # STEP 2: Load LLM
    # -------------------------------------------------
    def load_llm(self):
        print("[STEP 2] Loading local Ollama LLM...")
        self.llm = ChatOllama(
            model=OLLAMA_MODEL,
            temperature=0,
            num_predict=4096
        )
        print(f"[OK] Ollama model loaded: {OLLAMA_MODEL}")

    # -------------------------------------------------
    # STEP 3: Collect TOC text (limited pages)
    # -------------------------------------------------
    def collect_toc_text(self):
        print("[STEP 3] Collecting TOC page text...")
        pages = []

        for i in range(self.toc_start_page,
                       min(self.toc_start_page + self.max_pages, self.doc.page_count)):
            page = self.doc.load_page(i)
            text = page.get_text("text")
            print(f"[INFO] Page {i + 1} text length: {len(text)}")
            pages.append({
                "page": i + 1,
                "text": text
            })

        return pages

    # -------------------------------------------------
    # STEP 4: Build prompt
    # -------------------------------------------------
    def build_prompt(self):
        print("[STEP 4] Building LLM prompt...")

        system_prompt = """
    You are a strict JSON generator.

    Your task is to extract Table of Contents entries from raw PDF text.

    Rules:
    1. Use ONLY text that appears in the input.
    2. Do NOT invent titles.
    3. Do NOT invent page numbers.
    4. Each TOC entry must be a separate JSON object.
    5. Ignore dotted leaders (.....).
    6. Merge split title + page number correctly.
    7. If page number is missing, set page_label to null.
    8. Allowed levels:
    - chapter
    - section
    - subsection
    - unknown
    9. Output MUST be valid JSON.
    10. Do NOT include explanations.
    11. Do NOT include markdown.
    12. Do NOT truncate output.
    """

        user_prompt = """
    Extract all TOC entries from this text:

    {toc_text}

    Return EXACTLY this JSON structure:

    [
    {{
        "title": "string",
        "page_label": "string or null",
        "level": "chapter|section|subsection|unknown"
    }}
    ]

    Return ONLY valid JSON.
    """

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt.strip()),
                ("user", user_prompt.strip()),
            ]
        )


    # -------------------------------------------------
    # STEP 5: Run LLM
    # -------------------------------------------------
    def run_llm(self, toc_pages):
        print("[STEP 5] Running LLM extraction...")

        combined_text = ""
        for p in toc_pages:
            combined_text += f"\n--- PAGE {p['page']} ---\n"
            combined_text += p["text"]

        prompt = self.build_prompt()

        chain = (
            prompt
            | self.llm
            | StrOutputParser()
        )

        response = chain.invoke({"toc_text": combined_text})

        print("[RAW LLM OUTPUT]")
        print(response)

        return response

    # -------------------------------------------------
    # STEP 6: Parse + Validate output
    # -------------------------------------------------
    def parse_output(self, raw_output: str):
        print("[STEP 6] Parsing LLM output safely...")

        if not raw_output:
            print("[ERROR] Empty LLM output")
            return []

        # -----------------------------------------
        # Step 1: Extract JSON array safely
        # -----------------------------------------
        start = raw_output.find("[")
        end = raw_output.rfind("]")

        if start == -1 or end == -1:
            print("[ERROR] No JSON array found in LLM output")
            return []

        json_str = raw_output[start:end + 1]

        # -----------------------------------------
        # Step 2: Remove invalid patterns
        # -----------------------------------------
        json_str = re.sub(r"\.\.\..*", "", json_str)  # remove ... lines
        json_str = re.sub(r",\s*]", "]", json_str)    # remove trailing commas

        try:
            parsed = json.loads(json_str)
            print(f"[SUCCESS] Parsed {len(parsed)} TOC entries from LLM")
            return parsed

        except Exception as e:
            print("[ERROR] Failed to parse cleaned JSON")
            print(e)
            return []
    
    def roman_to_int(self, roman):
        roman = roman.lower()
        roman_map = {
            'i': 1, 'v': 5, 'x': 10,
            'l': 50, 'c': 100,
            'd': 500, 'm': 1000
        }

        total = 0
        prev = 0

        for char in reversed(roman):
            value = roman_map.get(char, 0)
            if value < prev:
                total -= value
            else:
                total += value
            prev = value

        return total

    def sort_key(self, entry):
        label = entry.get("page_label")

        if label is None:
            return (2, float("inf"))

        # Roman numeral
        if re.fullmatch(r"[ivxlcdmIVXLCDM]+", label):
            return (0, self.roman_to_int(label))

        # Numeric
        if re.fullmatch(r"\d+", label):
            return (1, int(label))

        # Complex labels like 2-1
        match = re.match(r"(\d+)", label)
        if match:
            return (1, int(match.group(1)))

        return (2, float("inf"))

    
    def is_toc_page(self, text):
        """
        Layout-friendly TOC detection.
        Works for WHO-style PDFs.
        """

        lower = text.lower()

        # Strong signal: explicit word
        if "content" in lower:
            print("[DEBUG] Keyword 'content' detected")
            return True

        lines = text.splitlines()
        score = 0

        for line in lines:
            line = line.strip()

            # Skip short lines
            if len(line) < 5:
                continue

            # Case 1: ends with number
            if re.search(r"\s(\d+|[ivxlcdm]+)$", line.lower()):
                score += 1

            # Case 2: numbered section like 1.1
            if re.search(r"^\d+(\.\d+)+", line):
                score += 1

            # Case 3: line starts with CHAPTER
            if line.lower().startswith("chapter"):
                score += 1

        print(f"[DEBUG] TOC detection score: {score}")

        return score >= 3


    def collect_toc_text(self):
        print("[STEP 3] Detecting consecutive TOC pages...")

        pages = []
        page_index = self.toc_start_page
        scanned = 0

        while page_index < self.doc.page_count and scanned < 15:
            page = self.doc.load_page(page_index)
            text = page.get_text("text")

            print(f"[SCAN] Page {page_index + 1} length: {len(text)}")

            if not self.is_toc_page(text):
                print("[STOP] Page does not match TOC pattern")
                break

            print("[INFO] TOC page confirmed")
            pages.append({
                "page": page_index + 1,
                "text": text
            })

            page_index += 1
            scanned += 1

        print(f"[INFO] Total consecutive TOC pages detected: {len(pages)}")

        return pages


    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        self.load_pdf()
        self.load_llm()
        toc_pages = self.collect_toc_text()

        all_entries = []

        print("\n[STEP 5] Running LLM extraction using threads...")

        def process_page(page):
            print(f"[THREAD] Processing page {page['page']}")
            raw = self.run_llm([page])
            parsed = self.parse_output(raw)
            return parsed

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(process_page, page) for page in toc_pages]

            for future in as_completed(futures):
                result = future.result()
                all_entries.extend(result)

        print("\n[STEP 7] Sorting entries by page number...")

        all_entries = sorted(all_entries, key=self.sort_key)

        print("[INFO] Sorting completed")

        return all_entries

# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    print("=" * 100)
    print("LLM TOC EXTRACTOR (FALLBACK) STARTED")
    print("=" * 100)

    # -------------------------------------------------
    # Validate CLI arguments
    # -------------------------------------------------
    if len(sys.argv) < 3:
        print("\nUsage:")
        print("  python extractor_llm_fallback.py <pdf_path> <toc_start_page>")
        print("\nExample:")
        print('  python extractor_llm_fallback.py "data/book.pdf" 6\n')
        sys.exit(1)

    pdf_path = sys.argv[1]

    # -------------------------------------------------
    # Validate file exists
    # -------------------------------------------------
    if not os.path.exists(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        sys.exit(1)

    # -------------------------------------------------
    # Validate TOC page number
    # -------------------------------------------------
    try:
        toc_start_page = int(sys.argv[2]) - 1
        if toc_start_page < 0:
            raise ValueError
    except ValueError:
        print("[ERROR] TOC start page must be a positive integer")
        sys.exit(1)

    print(f"PDF Path       : {pdf_path}")
    print(f"TOC Start Page : {toc_start_page + 1}")
    print("=" * 100)

    # -------------------------------------------------
    # Run extractor
    # -------------------------------------------------
    try:
        extractor = LLMTOCExtractor(pdf_path, toc_start_page)
        entries = extractor.run()

        print("\n[FINAL TOC STRUCTURE]")
        pprint(entries, width=130)

        # -------------------------------------------------
        # Save output automatically
        # -------------------------------------------------
        output_file = "toc_output_llm.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        print(f"\n[OUTPUT] Saved to {output_file}")

    except Exception as e:
        print("\n[CRITICAL ERROR]")
        print(e)
        sys.exit(1)

    print("=" * 100)
    print("LLM TOC EXTRACTOR COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    import os
    main()