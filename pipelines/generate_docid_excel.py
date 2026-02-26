"""
Export DocID ↔ Book Name Mapping to Excel
"""

from openpyxl import Workbook
from core.registry.document_registry import DocumentRegistry


def main():

    registry = DocumentRegistry()
    rows = registry.fetch_all()

    wb = Workbook()
    ws = wb.active
    ws.title = "DocID Mapping"

    ws.append(["Doc ID", "Title", "Source Path", "Total Pages", "Created At"])

    for row in rows:
        ws.append(row)

    output = "docid_book_mapping.xlsx"
    wb.save(output)

    print(f"Exported {len(rows)} records to {output}")


if __name__ == "__main__":
    main()