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


class PDFRenderer:
    def __init__(self, pdf_path: str, dpi: int = 200):
        self.pdf_path = pdf_path
        self.dpi = dpi
        self.doc = None

    # -------------------------------------------------
    # STEP 1: Load PDF
    # -------------------------------------------------
    def load_pdf(self):
        print("[STEP 1] Loading PDF for rendering...")
        try:
            self.doc = fitz.open(self.pdf_path)
            print("[OK] PDF loaded successfully")
            print(f"[INFO] Total pages: {self.doc.page_count}")
        except Exception as e:
            print(f"[ERROR] Failed to load PDF: {e}")
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
        print(f"[STEP 2] Rendering page {page_index + 1}...")

        if page_index < 0 or page_index >= self.doc.page_count:
            print("[ERROR] Invalid page index")
            return None

        os.makedirs(output_dir, exist_ok=True)

        page = self.doc.load_page(page_index)
        pix = page.get_pixmap(dpi=self.dpi)

        image_path = os.path.join(
            output_dir,
            f"page_{page_index + 1}.png"
        )

        pix.save(image_path)

        print(f"[OK] Image saved at: {image_path}")

        if open_image:
            print("[INFO] Opening image in default viewer...")
            webbrowser.open(f"file:///{os.path.abspath(image_path)}")

        return image_path

    # -------------------------------------------------
    # STEP 3: Convert Image to Base64
    # -------------------------------------------------
    def image_to_base64(self, image_path: str) -> str:
        print("[STEP 3] Converting image to base64...")

        if not os.path.exists(image_path):
            print("[ERROR] Image file not found")
            return ""

        with open(image_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode("utf-8")

        print(f"[OK] Base64 conversion completed "
              f"(length={len(encoded)})")

        return encoded

    # -------------------------------------------------
    # STEP 4: Render Multiple Pages
    # -------------------------------------------------
    def render_pages(
        self,
        start_page: int = 0,
        max_pages: int = 5,
        output_dir: str = "./debug_renders"
    ):
        print(
            f"[STEP 4] Rendering pages "
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

        print(f"[OK] Rendered {len(rendered)} pages")
        return rendered


# ============================================================
# STANDALONE RUNNER
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python renderer.py <pdf_path> [page_number]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_number = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0

    print("=" * 70)
    print("PDF RENDERER VERIFICATION STARTED")
    print(f"PDF Path   : {pdf_path}")
    print(f"Page Index : {page_number + 1}")
    print("=" * 70)

    renderer = PDFRenderer(pdf_path, dpi=200)

    renderer.load_pdf()

    image_path = renderer.render_page(
        page_index=page_number,
        open_image=True
    )

    if image_path:
        b64 = renderer.image_to_base64(image_path)
        print(f"[INFO] Base64 preview (first 120 chars):")
        print(b64[:120] + "...")

    print("=" * 70)
    print("PDF RENDERER VERIFICATION COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    main()
