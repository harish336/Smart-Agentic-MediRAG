"""
OCR Module (Standalone)

Purpose:
- Perform OCR on images or PDF pages
- Extract text from scanned documents
- Designed for fallback when selectable text is unavailable
"""

import sys
import os
import fitz  # PyMuPDF
from PIL import Image
from pprint import pprint
from typing import List, Dict
import uuid
import pytesseract
from core.utils.logging_utils import get_component_logger

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


logger = get_component_logger("OCRProcessor", component="ingestion")


class OCRProcessor:
    def __init__(self, input_path: str, dpi: int = 300):
        self.input_path = input_path
        self.dpi = dpi
        self.results = []
        self.doc = None  # Lazy loaded PDF

    # -------------------------------------------------
    # Internal Lazy Loader (PDF Only)
    # -------------------------------------------------
    def _ensure_pdf_loaded(self):
        if self.doc is None:
            logger.info("Lazy loading PDF for OCR...")
            try:
                self.doc = fitz.open(self.input_path)
                logger.info(f"PDF loaded successfully. Total pages: {self.doc.page_count}")
            except Exception as e:
                logger.exception(f"Failed during PDF lazy loading: {e}")
                raise

    # -------------------------------------------------
    # STEP 1: Detect input type
    # -------------------------------------------------
    def detect_input_type(self):
        try:
            if self.input_path.lower().endswith(".pdf"):
                logger.info("Input detected as PDF")
                return "pdf"
            elif self.input_path.lower().endswith((".png", ".jpg", ".jpeg", ".tiff")):
                logger.info("Input detected as IMAGE")
                return "image"
            else:
                raise ValueError("Unsupported input type")
        except Exception as e:
            logger.exception(f"Input type detection failed: {e}")
            raise

    # -------------------------------------------------
    # STEP 2A: OCR IMAGE FILE
    # -------------------------------------------------
    def ocr_image(self):
        logger.info("STEP 2: Performing OCR on image...")
        try:
            img = Image.open(self.input_path)
            text = pytesseract.image_to_string(img)

            record = {
                "id": str(uuid.uuid4()),
                "source": os.path.basename(self.input_path),
                "page": None,
                "text": text.strip(),
                "confidence": self.estimate_confidence(text)
            }

            self.results.append(record)

            logger.info(f"OCR result length: {len(text)} characters")

        except Exception as e:
            logger.exception(f"OCR image processing failed: {e}")

    # -------------------------------------------------
    # STEP 2B: OCR PDF FILE
    # -------------------------------------------------
    def ocr_pdf(self):
        logger.info("STEP 2: Performing OCR on PDF...")

        try:
            self._ensure_pdf_loaded()

            for page_index in range(self.doc.page_count):
                logger.info(f"Rendering page {page_index + 1} for OCR...")

                page = self.doc.load_page(page_index)
                pix = page.get_pixmap(dpi=self.dpi)

                temp_img = f".ocr_tmp_{page_index}.png"
                pix.save(temp_img)

                img = Image.open(temp_img)
                text = pytesseract.image_to_string(img)

                record = {
                    "id": str(uuid.uuid4()),
                    "source": os.path.basename(self.input_path),
                    "page": page_index + 1,
                    "text": text.strip(),
                    "confidence": self.estimate_confidence(text)
                }

                self.results.append(record)

                logger.info(f"OCR text length: {len(text)} characters")

                os.remove(temp_img)

        except Exception as e:
            logger.exception(f"OCR PDF processing failed: {e}")

    # -------------------------------------------------
    # STEP 3: Confidence estimation (simple heuristic)
    # -------------------------------------------------
    def estimate_confidence(self, text: str) -> float:
        try:
            if not text.strip():
                return 0.0

            letters = sum(c.isalpha() for c in text)
            spaces = sum(c.isspace() for c in text)
            confidence = min(1.0, (letters + spaces) / max(len(text), 1))
            return round(confidence, 2)

        except Exception as e:
            logger.exception(f"Confidence estimation failed: {e}")
            return 0.0

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        logger.info("STEP 1: Detecting input type...")

        try:
            input_type = self.detect_input_type()

            if input_type == "image":
                self.ocr_image()
            else:
                self.ocr_pdf()

            logger.info("OCR completed")
            logger.info(f"Total OCR records: {len(self.results)}")

            return self.results

        except Exception as e:
            logger.exception(f"OCR run failed: {e}")
            return []


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python ocr.py <image_or_pdf_path>")
        sys.exit(1)

    input_path = sys.argv[1]

    logger.info("=" * 100)
    logger.info("OCR PROCESSOR STARTED")
    logger.info(f"Input Path: {input_path}")
    logger.info("=" * 100)

    try:
        processor = OCRProcessor(input_path)
        results = processor.run()
    except Exception as e:
        logger.exception(f"OCR failed: {e}")
        sys.exit(1)

    logger.info("FINAL OCR OUTPUT")
    pprint(results, width=120)

    import json
    try:
        with open("ocr_output.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        logger.info("Output saved to ocr_output.json")
    except Exception as e:
        logger.exception(f"Failed saving OCR output JSON: {e}")

    logger.info("=" * 100)
    logger.info("OCR PROCESSOR COMPLETED")
    logger.info("=" * 100)


if __name__ == "__main__":
    main()
