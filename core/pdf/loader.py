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

from core.utils.logging_utils import get_component_logger

logger = get_component_logger("PDFLoader", component="ingestion")


class PDFLoader:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = None  # Lazy loaded document

    # ------------------------------------------------------------
    # Internal Lazy Loader (Load Only Once)
    # ------------------------------------------------------------
    def _ensure_loaded(self):
        """
        Ensures the PDF is loaded only once.
        """
        if self.doc is None:
            logger.info("Lazy loading PDF document...")
            try:
                self.doc = fitz.open(self.pdf_path)
                logger.info("PDF loaded successfully (lazy init)")
            except Exception as e:
                logger.exception(f"Failed during lazy loading: {e}")
                raise

    # ------------------------------
    # Step 1: Validate PDF Path
    # ------------------------------
    def validate(self) -> bool:
        logger.info("STEP 1: Validating PDF path...")
        try:
            if not os.path.exists(self.pdf_path):
                logger.error(f"File not found: {self.pdf_path}")
                return False

            if not self.pdf_path.lower().endswith(".pdf"):
                logger.error("File is not a PDF")
                return False

            logger.info("PDF path validated successfully")
            return True

        except Exception as e:
            logger.exception(f"Validation error: {e}")
            return False

    # ------------------------------
    # Step 2: Load PDF (Explicit)
    # ------------------------------
    def load(self) -> bool:
        logger.info("STEP 2: Loading PDF document...")
        try:
            if self.doc is not None:
                logger.info("PDF already loaded. Skipping reload.")
                return True

            self.doc = fitz.open(self.pdf_path)
            logger.info("PDF loaded successfully")
            return True

        except Exception as e:
            logger.exception(f"Failed to load PDF: {e}")
            return False

    # ------------------------------
    # Step 3: Extract Metadata
    # ------------------------------
    def extract_metadata(self) -> Dict:
        logger.info("STEP 3: Extracting PDF metadata...")
        try:
            self._ensure_loaded()
            metadata = self.doc.metadata

            for k, v in metadata.items():
                logger.info(f"Metadata - {k}: {v}")

            return metadata

        except Exception as e:
            logger.exception(f"Metadata extraction failed: {e}")
            return {}

    # ------------------------------
    # Step 4: Page Count
    # ------------------------------
    def page_count(self) -> int:
        try:
            self._ensure_loaded()
            count = self.doc.page_count
            logger.info(f"STEP 4: Total pages detected: {count}")
            return count

        except Exception as e:
            logger.exception(f"Failed to get page count: {e}")
            return 0

    # ------------------------------
    # Step 5: Extract Text Per Page
    # ------------------------------
    def extract_text(self, max_pages: int = 5) -> List[Dict]:
        logger.info("STEP 5: Extracting text from pages...")
        pages = []

        try:
            self._ensure_loaded()

            for i in range(min(max_pages, self.doc.page_count)):
                page = self.doc.load_page(i)
                text = page.get_text("text")

                logger.info(f"PAGE {i+1}: Text length {len(text)} characters")

                pages.append({
                    "page_index": i,
                    "text": text.strip()
                })

            logger.info("Text extraction completed successfully")
            return pages

        except Exception as e:
            logger.exception(f"Text extraction failed: {e}")
            return []

    # ------------------------------
    # Step 6: Render Page Images
    # ------------------------------
    def render_images(self, output_dir: str = "./debug_images", max_pages: int = 3):
        logger.info("STEP 6: Rendering page images...")

        try:
            self._ensure_loaded()
            os.makedirs(output_dir, exist_ok=True)

            for i in range(min(max_pages, self.doc.page_count)):
                page = self.doc.load_page(i)
                pix = page.get_pixmap(dpi=200)

                image_path = os.path.join(output_dir, f"page_{i+1}.png")
                pix.save(image_path)

                logger.info(f"PAGE {i+1}: Image saved -> {image_path}")

            logger.info("Image rendering completed successfully")

        except Exception as e:
            logger.exception(f"Image rendering failed: {e}")


# ============================================================
# Standalone Runner
# ============================================================
def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python loader.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    logger.info("=" * 60)
    logger.info("PDF LOADER VERIFICATION STARTED")
    logger.info("=" * 60)

    loader = PDFLoader(pdf_path)

    if not loader.validate():
        sys.exit(1)

    if not loader.load():
        sys.exit(1)

    loader.extract_metadata()
    loader.page_count()
    loader.extract_text(max_pages=5)
    loader.render_images(max_pages=3)

    logger.info("=" * 60)
    logger.info("PDF LOADER VERIFICATION COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
