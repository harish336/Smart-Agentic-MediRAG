"""
OCR Module (Standalone)

Purpose:
- Perform OCR on images or PDF pages
- Extract text from scanned documents
- Designed for fallback when selectable text is unavailable

Dependencies:
- pytesseract
- pillow
- pymupdf

This file CAN be run independently.
"""

import sys
import os
import fitz  # PyMuPDF
from PIL import Image
from pprint import pprint
from typing import List, Dict
import uuid
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class OCRProcessor:
    def __init__(self, input_path: str, dpi: int = 300):
        self.input_path = input_path
        self.dpi = dpi
        self.results = []

    # -------------------------------------------------
    # STEP 1: Detect input type
    # -------------------------------------------------
    def detect_input_type(self):
        if self.input_path.lower().endswith(".pdf"):
            print("[INFO] Input detected as PDF")
            return "pdf"
        elif self.input_path.lower().endswith((".png", ".jpg", ".jpeg", ".tiff")):
            print("[INFO] Input detected as IMAGE")
            return "image"
        else:
            raise ValueError("Unsupported input type")

    # -------------------------------------------------
    # STEP 2A: OCR IMAGE FILE
    # -------------------------------------------------
    def ocr_image(self):
        print("\n[STEP 2] Performing OCR on image...")
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

        print("[OCR RESULT]")
        print(text[:300])

    # -------------------------------------------------
    # STEP 2B: OCR PDF FILE
    # -------------------------------------------------
    def ocr_pdf(self):
        print("\n[STEP 2] Performing OCR on PDF...")
        doc = fitz.open(self.input_path)

        for page_index in range(doc.page_count):
            print(f"\n[PAGE {page_index + 1}] Rendering page for OCR...")

            page = doc.load_page(page_index)
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

            print(f"[OCR TEXT LENGTH] {len(text)} characters")

            os.remove(temp_img)

    # -------------------------------------------------
    # STEP 3: Confidence estimation (simple heuristic)
    # -------------------------------------------------
    def estimate_confidence(self, text: str) -> float:
        if not text.strip():
            return 0.0

        letters = sum(c.isalpha() for c in text)
        spaces = sum(c.isspace() for c in text)
        confidence = min(1.0, (letters + spaces) / max(len(text), 1))
        return round(confidence, 2)

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        print("[STEP 1] Detecting input type...")
        input_type = self.detect_input_type()

        if input_type == "image":
            self.ocr_image()
        else:
            self.ocr_pdf()

        print("\n[INFO] OCR completed")
        print(f"[INFO] Total OCR records: {len(self.results)}")

        return self.results


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python ocr.py <image_or_pdf_path>")
        sys.exit(1)

    input_path = sys.argv[1]

    print("=" * 100)
    print("OCR PROCESSOR STARTED")
    print(f"Input Path: {input_path}")
    print("=" * 100)

    try:
        processor = OCRProcessor(input_path)
        results = processor.run()
    except Exception as e:
        print(f"[ERROR] OCR failed: {e}")
        sys.exit(1)

    print("\n[FINAL OCR OUTPUT]")
    pprint(results, width=120)

    import json
    with open("ocr_output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n[OUTPUT] Saved to ocr_output.json")
    print("=" * 100)
    print("OCR PROCESSOR COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
