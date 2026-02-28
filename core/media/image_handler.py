"""
Image Handler (Standalone)

Purpose:
- Detect images in PDF pages
- Attempt text extraction if image has selectable text
- If not extractable, store image as reference URL
- Do NOT store image permanently on local disk
- Output metadata suitable for vector DB + graph DB

This file CAN be run independently.
"""

import sys
import os
import uuid
import fitz  # PyMuPDF
from pprint import pprint
from typing import List, Dict

from core.utils.logging_utils import get_component_logger

logger = get_component_logger("ImageHandler", component="ingestion")


class ImageHandler:
    def __init__(self, pdf_path: str, temp_dir: str = ".tmp_images"):
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.doc = None
        self.images = []

    # -------------------------------------------------
    # Internal Lazy Loader (Load Only Once)
    # -------------------------------------------------
    def _ensure_loaded(self):
        if self.doc is None:
            logger.info("Lazy loading PDF...")
            try:
                self.doc = fitz.open(self.pdf_path)
                logger.info(f"PDF loaded successfully. Total pages: {self.doc.page_count}")
            except Exception as e:
                logger.exception(f"Failed during lazy loading: {e}")
                raise

    # -------------------------------------------------
    # STEP 1: Load PDF (Explicit)
    # -------------------------------------------------
    def load_pdf(self):
        logger.info("STEP 1: Loading PDF...")
        try:
            if self.doc is not None:
                logger.info("PDF already loaded. Skipping reload.")
                return

            self.doc = fitz.open(self.pdf_path)
            logger.info(f"PDF loaded successfully. Total pages: {self.doc.page_count}")

        except Exception as e:
            logger.exception(f"Failed to load PDF: {e}")
            sys.exit(1)

    # -------------------------------------------------
    # STEP 2: Scan pages for images
    # -------------------------------------------------
    def scan_images(self):
        logger.info("STEP 2: Scanning pages for images...")

        try:
            self._ensure_loaded()
            os.makedirs(self.temp_dir, exist_ok=True)

            for page_idx in range(self.doc.page_count):
                page = self.doc.load_page(page_idx)
                image_list = page.get_images(full=True)

                if not image_list:
                    continue

                logger.info(f"PAGE {page_idx + 1}: Images found: {len(image_list)}")

                for img_idx, img in enumerate(image_list):
                    self.process_image(page, page_idx, img_idx, img)

            logger.info(f"Total images processed: {len(self.images)}")

        except Exception as e:
            logger.exception(f"Image scanning failed: {e}")

    # -------------------------------------------------
    # STEP 3: Process single image
    # -------------------------------------------------
    def process_image(self, page, page_idx, img_idx, img):
        try:
            xref = img[0]
            base_image = self.doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            image_id = str(uuid.uuid4())
            temp_path = os.path.join(self.temp_dir, f"{image_id}.{image_ext}")

            with open(temp_path, "wb") as f:
                f.write(image_bytes)

            logger.info(f"IMAGE | Page {page_idx + 1} | Image {img_idx + 1} | Saved temp")

            extracted_text = self.try_extract_text(page)

            image_record = {
                "id": image_id,
                "page": page_idx + 1,
                "type": "image",
                "format": image_ext,
                "text": extracted_text,
                "has_text": bool(extracted_text),
                "url": self.generate_reference_url(image_id, image_ext)
            }

            self.images.append(image_record)

            logger.info(f"→ Text detected: {'YES' if extracted_text else 'NO'}")

            os.remove(temp_path)

        except Exception as e:
            logger.exception(f"Failed processing image on page {page_idx + 1}: {e}")

    # -------------------------------------------------
    # STEP 4: Try extracting text near image
    # -------------------------------------------------
    def try_extract_text(self, page) -> str:
        try:
            text = page.get_text("text").strip()
            return text if len(text) < 300 else ""
        except Exception as e:
            logger.exception(f"Text extraction around image failed: {e}")
            return ""

    # -------------------------------------------------
    # STEP 5: Generate reference URL
    # -------------------------------------------------
    def generate_reference_url(self, image_id, ext):
        return f"image://{image_id}.{ext}"

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        try:
            self.load_pdf()
            self.scan_images()
            return self.images
        except Exception as e:
            logger.exception(f"ImageHandler run failed: {e}")
            return []


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python image_handler.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    logger.info("=" * 100)
    logger.info("IMAGE HANDLER STARTED")
    logger.info(f"PDF Path: {pdf_path}")
    logger.info("=" * 100)

    handler = ImageHandler(pdf_path)
    images = handler.run()

    logger.info("FINAL IMAGE METADATA")
    pprint(images, width=130)

    import json
    try:
        with open("images_output.json", "w", encoding="utf-8") as f:
            json.dump(images, f, indent=2)
        logger.info("Output saved to images_output.json")
    except Exception as e:
        logger.exception(f"Failed saving output JSON: {e}")

    logger.info("=" * 100)
    logger.info("IMAGE HANDLER COMPLETED")
    logger.info("=" * 100)


if __name__ == "__main__":
    main()
