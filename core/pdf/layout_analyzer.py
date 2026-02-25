import sys
import fitz
from collections import Counter
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


class StyleAnalyzer:

    def __init__(self, pdf_path, toc_start_page):
        self.pdf_path = pdf_path
        self.toc_start_page = toc_start_page  # physical page index (0-based)
        self.doc = None
        self.font_counter = Counter()
        self.blocks = []
    
    def load_llm(self):
        print("[LLM] Loading local Ollama model...")
        self.llm = ChatOllama(
            model="mistral",   # or llama3, phi
            temperature=0
    )

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        self.doc = fitz.open(self.pdf_path)
        print(f"[OK] Loaded PDF | Pages: {self.doc.page_count}")

    # -------------------------------------------------
    # STEP 2: Detect consecutive TOC pages
    # -------------------------------------------------
    def detect_consecutive_toc(self):

        print("[STEP 2] Detecting consecutive TOC pages using LLM...")

        self.load_llm()

        prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a highly accurate document classification AI.\n"
     "Your only task is to determine if the provided text from a PDF page constitutes a 'Table of Contents' (TOC).\n\n"
     "CHARACTERISTICS OF A TOC PAGE:\n"
     "1. Contains a structured list of chapters, sections, or headings.\n"
     "2. Pairs these headings with specific page numbers (e.g., 'Introduction .... 5').\n"
     "3. Usually features words like 'Contents', 'Table of Contents', or 'Brief Contents' near the top.\n\n"
     "EXCLUSIONS (Respond NO):\n"
     "- A page that simply mentions the phrase 'Table of Contents' in standard prose/paragraphs.\n"
     "- An alphabetical keyword index or glossary at the end of a book.\n"
     "- A title page, copyright page, or preface.\n\n"
     "OUTPUT FORMAT:\n"
     "Respond with exactly one word: YES or NO. Do not add punctuation, markdown, or explanations."
    ),
    ("user",
     "Analyze the following PDF page text and classify it:\n\n"
     "--- PAGE TEXT START ---\n"
     "{page_text}\n"
     "--- PAGE TEXT END ---\n\n"
     "Is this a Table of Contents page? (YES/NO):")
])

        chain = prompt | self.llm | StrOutputParser()

        page_index = self.toc_start_page
        toc_pages = 0

        while page_index < self.doc.page_count:

            page = self.doc.load_page(page_index)
            text = page.get_text("text")

            # Avoid sending entire page if very long
            text = text[:2000]

            print(f"[LLM] Checking page {page_index + 1}...")

            response = chain.invoke({"page_text": text}).strip().upper()

            print(f"[LLM Response] {response}")

            if response.startswith("YES"):
                toc_pages += 1
                page_index += 1
            else:
                break

        toc_end_page = self.toc_start_page + toc_pages

        print(f"[INFO] Consecutive TOC pages detected: {toc_pages}")
        print(f"[INFO] Content analysis will start from page: {toc_end_page + 1}")

        return toc_end_page

    # -------------------------------------------------
    # STEP 3: Extract fonts AFTER TOC
    # -------------------------------------------------
    def extract_fonts_after_toc(self, start_page):

        print("[STEP 3] Extracting font styles after TOC...")

        for page_index in range(start_page, self.doc.page_count):

            page = self.doc.load_page(page_index)
            blocks = page.get_text("dict")["blocks"]

            for block in blocks:
                if block["type"] != 0:
                    continue

                for line in block["lines"]:
                    for span in line["spans"]:

                        text = span["text"].strip()
                        size = round(span["size"], 1)

                        if not text:
                            continue

                        self.font_counter[size] += 1

                        self.blocks.append({
                            "text": text,
                            "size": size,
                            "page": page_index + 1
                        })

        print("[OK] Font extraction complete")

    # -------------------------------------------------
    # STEP 4: Analyze font sizes
    # -------------------------------------------------
    def analyze_styles(self):

        print("\n[STEP 4] Analyzing font distribution...\n")

        for size, count in self.font_counter.most_common():
            print(f"Font Size {size} → {count} occurrences")

        if len(self.font_counter) < 2:
            print("[ERROR] Not enough font variation")
            return

        # Body = most frequent
        body_size = self.font_counter.most_common(1)[0][0]

        # Unique sorted sizes
        unique_sizes = sorted(self.font_counter.keys())

        chapter_size = unique_sizes[-1]
        subheading_size = unique_sizes[-2] if len(unique_sizes) > 1 else body_size

        print("\n[DETECTED STRUCTURE]")
        print(f"  Chapter Font Size    : {chapter_size}")
        print(f"  Subheading Font Size : {subheading_size}")
        print(f"  Body Font Size       : {body_size}")

        self.show_examples(chapter_size, subheading_size, body_size)

    # -------------------------------------------------
    # STEP 5: Show examples
    # -------------------------------------------------
    def show_examples(self, chapter_size, subheading_size, body_size):

        print("\n[SAMPLE OUTPUT]\n")

        printed = {
            "chapter": 0,
            "subheading": 0,
            "body": 0
        }

        for block in self.blocks:

            if printed["chapter"] < 5 and block["size"] == chapter_size:
                print(f"[CHAPTER] Page {block['page']} | {block['text']}")
                printed["chapter"] += 1

            elif printed["subheading"] < 5 and block["size"] == subheading_size:
                print(f"[SUBHEADING] Page {block['page']} | {block['text']}")
                printed["subheading"] += 1

            elif printed["body"] < 5 and block["size"] == body_size:
                print(f"[BODY] Page {block['page']} | {block['text']}")
                printed["body"] += 1

            if all(v >= 5 for v in printed.values()):
                break

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):

        print("\n" + "=" * 80)
        print("POST-TOC STYLE ANALYZER")
        print("=" * 80)

        self.load_pdf()

        toc_end = self.detect_consecutive_toc()

        self.extract_fonts_after_toc(toc_end)

        self.analyze_styles()

        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETED")
        print("=" * 80)


# -------------------------------------------------
# CLI
# -------------------------------------------------
def main():

    if len(sys.argv) < 3:
        print("Usage:")
        print("  python style_analyzer.py <pdf_path> <toc_start_page>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    toc_start_page = int(sys.argv[2]) - 1  # convert to 0-based

    analyzer = StyleAnalyzer(pdf_path, toc_start_page)
    analyzer.run()


if __name__ == "__main__":
    main()