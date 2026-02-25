"""
PDF Loader Module (Standalone Runnable)

Responsibilities:
- Load PDF
- Validate PDF
- Extract basic metadata
- Count pages
- Extract text per page
- Render page images (for TOC / OCR later)

This file CAN be run independently for verification.
"""

import os
import sys
from typing import List, Dict

import fitz  # PyMuPDF


class PDFLoader:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = None

    # ------------------------------
    # Step 1: Validate PDF Path
    # ------------------------------
    def validate(self) -> bool:
        print("[STEP 1] Validating PDF path...")
        if not os.path.exists(self.pdf_path):
            print(f"[ERROR] File not found: {self.pdf_path}")
            return False

        if not self.pdf_path.lower().endswith(".pdf"):
            print("[ERROR] File is not a PDF")
            return False

        print("[OK] PDF path validated")
        return True

    # ------------------------------
    # Step 2: Load PDF
    # ------------------------------
    def load(self) -> bool:
        print("[STEP 2] Loading PDF document...")
        try:
            self.doc = fitz.open(self.pdf_path)
            print("[OK] PDF loaded successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to load PDF: {e}")
            return False

    # ------------------------------
    # Step 3: Extract Metadata
    # ------------------------------
    def extract_metadata(self) -> Dict:
        print("[STEP 3] Extracting PDF metadata...")
        metadata = self.doc.metadata
        for k, v in metadata.items():
            print(f"  - {k}: {v}")
        return metadata

    # ------------------------------
    # Step 4: Page Count
    # ------------------------------
    def page_count(self) -> int:
        count = self.doc.page_count
        print(f"[STEP 4] Total pages detected: {count}")
        return count

    # ------------------------------
    # Step 5: Extract Text Per Page
    # ------------------------------
    def extract_text(self, max_pages: int = 5) -> List[Dict]:
        print("[STEP 5] Extracting text from pages...")
        pages = []

        for i in range(min(max_pages, self.doc.page_count)):
            page = self.doc.load_page(i)
            text = page.get_text("text")

            print(f"[PAGE {i+1}] Text length: {len(text)} characters")

            pages.append({
                "page_index": i,
                "text": text.strip()
            })

        print("[OK] Text extraction completed")
        return pages

    # ------------------------------
    # Step 6: Render Page Images
    # ------------------------------
    def render_images(self, output_dir: str = "./debug_images", max_pages: int = 3):
        print("[STEP 6] Rendering page images...")
        os.makedirs(output_dir, exist_ok=True)

        for i in range(min(max_pages, self.doc.page_count)):
            page = self.doc.load_page(i)
            pix = page.get_pixmap(dpi=200)

            image_path = os.path.join(output_dir, f"page_{i+1}.png")
            pix.save(image_path)

            print(f"[PAGE {i+1}] Image saved: {image_path}")

        print("[OK] Image rendering completed")


# ============================================================
# Standalone Runner
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python loader.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print("=" * 60)
    print("PDF LOADER VERIFICATION STARTED")
    print("=" * 60)

    loader = PDFLoader(pdf_path)

    if not loader.validate():
        sys.exit(1)

    if not loader.load():
        sys.exit(1)

    loader.extract_metadata()
    loader.page_count()
    loader.extract_text(max_pages=5)
    loader.render_images(max_pages=3)

    print("=" * 60)
    print("PDF LOADER VERIFICATION COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
