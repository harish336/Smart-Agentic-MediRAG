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


class ImageHandler:
    def __init__(self, pdf_path: str, temp_dir: str = ".tmp_images"):
        self.pdf_path = pdf_path
        self.temp_dir = temp_dir
        self.doc = None
        self.images = []

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF...")
        self.doc = fitz.open(self.pdf_path)
        print("[OK] PDF loaded")
        print(f"[INFO] Total pages: {self.doc.page_count}")

    # -------------------------------------------------
    # STEP 2: Scan pages for images
    # -------------------------------------------------
    def scan_images(self):
        print("\n[STEP 2] Scanning pages for images...")

        os.makedirs(self.temp_dir, exist_ok=True)

        for page_idx in range(self.doc.page_count):
            page = self.doc.load_page(page_idx)
            image_list = page.get_images(full=True)

            if not image_list:
                continue

            print(f"[PAGE {page_idx + 1}] Images found: {len(image_list)}")

            for img_idx, img in enumerate(image_list):
                self.process_image(page, page_idx, img_idx, img)

        print(f"\n[INFO] Total images processed: {len(self.images)}")

    # -------------------------------------------------
    # STEP 3: Process single image
    # -------------------------------------------------
    def process_image(self, page, page_idx, img_idx, img):
        xref = img[0]
        base_image = self.doc.extract_image(xref)
        image_bytes = base_image["image"]
        image_ext = base_image["ext"]

        image_id = str(uuid.uuid4())
        temp_path = os.path.join(self.temp_dir, f"{image_id}.{image_ext}")

        with open(temp_path, "wb") as f:
            f.write(image_bytes)

        print(f"  [IMAGE] Page {page_idx + 1} | Image {img_idx + 1} | Saved temp")

        # Attempt text extraction from image area
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

        print(f"    → Text detected: {'YES' if extracted_text else 'NO'}")

        # Cleanup temp file
        os.remove(temp_path)

    # -------------------------------------------------
    # STEP 4: Try extracting text near image
    # -------------------------------------------------
    def try_extract_text(self, page) -> str:
        """
        NOTE:
        This is NOT OCR.
        It extracts selectable text around images (captions, embedded text).
        OCR can be plugged here later.
        """
        text = page.get_text("text").strip()
        return text if len(text) < 300 else ""

    # -------------------------------------------------
    # STEP 5: Generate reference URL
    # -------------------------------------------------
    def generate_reference_url(self, image_id, ext):
        """
        URL-style reference.
        In production, this maps to:
        - S3
        - MinIO
        - CDN
        - Signed endpoint
        """
        return f"image://{image_id}.{ext}"

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    def run(self):
        self.load_pdf()
        self.scan_images()
        return self.images


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python image_handler.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    print("=" * 100)
    print("IMAGE HANDLER STARTED")
    print(f"PDF Path: {pdf_path}")
    print("=" * 100)

    handler = ImageHandler(pdf_path)
    images = handler.run()

    print("\n[FINAL IMAGE METADATA]")
    pprint(images, width=130)

    import json
    with open("images_output.json", "w", encoding="utf-8") as f:
        json.dump(images, f, indent=2)

    print("\n[OUTPUT] Saved to images_output.json")
    print("=" * 100)
    print("IMAGE HANDLER COMPLETED")
    print("=" * 100)


if __name__ == "__main__":
    main()
