"""
PDF Renderer Module (Standalone Runnable)

Responsibilities:
- Render PDF pages into images
- Support base64 conversion (for LLM vision / OCR)
- Save rendered images for verification
- Print debug logs for each step

This file CAN be run independently.
"""

import sys
import os
import base64
import fitz  # PyMuPDF
import webbrowser

from core.utils.logging_utils import get_component_logger

logger = get_component_logger("PDFRenderer", component="ingestion")


class PDFRenderer:
    def __init__(self, pdf_path: str, dpi: int = 200):
        self.pdf_path = pdf_path
        self.dpi = dpi
        self.doc = None  # Lazy loaded document

    # -------------------------------------------------
    # Internal Lazy Loader (Load Only Once)
    # -------------------------------------------------
    def _ensure_loaded(self):
        if self.doc is None:
            logger.info("Lazy loading PDF for rendering...")
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
        logger.info("STEP 1: Loading PDF for rendering...")
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
    # STEP 2: Render Page to Image
    # -------------------------------------------------
    def render_page(
        self,
        page_index: int,
        output_dir: str = "./debug_renders",
        open_image: bool = False
    ):
        logger.info(f"STEP 2: Rendering page {page_index + 1}...")

        try:
            self._ensure_loaded()

            if page_index < 0 or page_index >= self.doc.page_count:
                logger.error("Invalid page index")
                return None

            os.makedirs(output_dir, exist_ok=True)

            page = self.doc.load_page(page_index)
            pix = page.get_pixmap(dpi=self.dpi)

            image_path = os.path.join(
                output_dir,
                f"page_{page_index + 1}.png"
            )

            pix.save(image_path)
            logger.info(f"Image saved at: {image_path}")

            if open_image:
                logger.info("Opening image in default viewer...")
                webbrowser.open(f"file:///{os.path.abspath(image_path)}")

            return image_path

        except Exception as e:
            logger.exception(f"Page rendering failed: {e}")
            return None

    # -------------------------------------------------
    # STEP 3: Convert Image to Base64
    # -------------------------------------------------
    def image_to_base64(self, image_path: str) -> str:
        logger.info("STEP 3: Converting image to base64...")

        try:
            if not os.path.exists(image_path):
                logger.error("Image file not found")
                return ""

            with open(image_path, "rb") as img_file:
                encoded = base64.b64encode(img_file.read()).decode("utf-8")

            logger.info(f"Base64 conversion completed (length={len(encoded)})")
            return encoded

        except Exception as e:
            logger.exception(f"Base64 conversion failed: {e}")
            return ""

    # -------------------------------------------------
    # STEP 4: Render Multiple Pages
    # -------------------------------------------------
    def render_pages(
        self,
        start_page: int = 0,
        max_pages: int = 5,
        output_dir: str = "./debug_renders"
    ):
        try:
            self._ensure_loaded()

            logger.info(
                f"STEP 4: Rendering pages "
                f"{start_page + 1} to "
                f"{min(start_page + max_pages, self.doc.page_count)}..."
            )

            rendered = []

            end_page = min(start_page + max_pages, self.doc.page_count)

            for page_index in range(start_page, end_page):
                path = self.render_page(
                    page_index,
                    output_dir=output_dir,
                    open_image=False
                )
                if path:
                    rendered.append(path)

            logger.info(f"Rendered {len(rendered)} pages successfully")
            return rendered

        except Exception as e:
            logger.exception(f"Multiple page rendering failed: {e}")
            return []


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python renderer.py <pdf_path> [page_number]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_number = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0

    logger.info("=" * 70)
    logger.info("PDF RENDERER VERIFICATION STARTED")
    logger.info(f"PDF Path   : {pdf_path}")
    logger.info(f"Page Index : {page_number + 1}")
    logger.info("=" * 70)

    renderer = PDFRenderer(pdf_path, dpi=200)

    renderer.load_pdf()

    image_path = renderer.render_page(
        page_index=page_number,
        open_image=True
    )

    if image_path:
        b64 = renderer.image_to_base64(image_path)
        logger.info("Base64 preview (first 120 chars):")
        logger.info(b64[:120] + "...")

    logger.info("=" * 70)
    logger.info("PDF RENDERER VERIFICATION COMPLETED SUCCESSFULLY")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
