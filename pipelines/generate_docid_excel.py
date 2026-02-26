"""
SmartChunk-RAG — Generate DocID ↔ Book Name Excel

Scans local PDF folder
Computes SHA256-based doc_id (same as VectorOrchestrator)
Exports Excel mapping

Usage:
    python -m pipelines.generate_docid_excel
"""

import os
import hashlib
from openpyxl import Workbook


# =====================================================
# CONFIG
# =====================================================

PDF_FOLDER = r"C:\Users\Harish\Downloads\Smart Medirag\data"
OUTPUT_FILE = r"C:\Users\Harish\Downloads\Smart Medirag\docid_book_mapping.xlsx"


# =====================================================
# GENERATE DOC ID (Same Logic As VectorOrchestrator)
# =====================================================

def generate_doc_id(file_path):

    with open(file_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    return file_hash[:16]


# =====================================================
# MAIN
# =====================================================

def main():

    print("=" * 80)
    print("SMARTCHUNK-RAG — DOCID EXCEL GENERATOR")
    print("=" * 80)

    if not os.path.exists(PDF_FOLDER):
        print("PDF folder not found.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "DocID Mapping"

    # Header
    ws.append(["Doc ID", "Book Name (File)", "Full Path", "File Size (MB)"])

    count = 0

    for root, _, files in os.walk(PDF_FOLDER):

        for file in files:

            if not file.lower().endswith(".pdf"):
                continue

            full_path = os.path.join(root, file)

            try:
                doc_id = generate_doc_id(full_path)
                file_size = round(os.path.getsize(full_path) / (1024 * 1024), 2)

                ws.append([
                    doc_id,
                    file,
                    full_path,
                    file_size
                ])

                print(f"Processed: {file}")
                count += 1

            except Exception as e:
                print(f"Error processing {file}: {e}")

    wb.save(OUTPUT_FILE)

    print("\n" + "=" * 80)
    print(f"Total PDFs Processed: {count}")
    print(f"Excel Saved At: {OUTPUT_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    main()