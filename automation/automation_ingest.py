import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from openpyxl import Workbook

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------

PROJECT_ROOT = Path(r"C:\Users\Harish\Downloads\Smart Medirag")
DATA_FOLDER = PROJECT_ROOT / "data"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
MODULE_NAME = "pipelines.full_ingestion_pipeline"

OUTPUT_EXCEL = PROJECT_ROOT / "ingestion_report.xlsx"
DEFAULT_MAX_WORKERS = 3


# ------------------------------------------------------------------
# RUN PIPELINE
# ------------------------------------------------------------------

def run_pipeline(pdf_path: Path) -> int:
    print("=" * 90)
    print(f"Processing: {pdf_path.name}")
    print("=" * 90)

    try:
        subprocess.run(
            [str(VENV_PYTHON), "-m", MODULE_NAME, str(pdf_path)],
            check=True,
        )
        print(f"[OK] {pdf_path.name}\n")
        return 1
    except subprocess.CalledProcessError:
        print(f"[FAIL] {pdf_path.name}\n")
        return 0
    except Exception:
        print(f"[ERROR] {pdf_path.name}\n")
        return 0


def get_max_workers(total_books: int) -> int:
    configured = os.getenv("INGEST_MAX_WORKERS", str(DEFAULT_MAX_WORKERS))
    try:
        requested = int(configured)
    except ValueError:
        requested = DEFAULT_MAX_WORKERS
    return max(1, min(total_books, requested))


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("\nINGESTION AUTOMATION STARTED\n")

    if not VENV_PYTHON.exists():
        print("[FAIL] .venv Python not found")
        return

    pdf_files = list(DATA_FOLDER.glob("*.pdf"))
    if not pdf_files:
        print("[WARN] No PDF files found")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Ingestion Report"
    ws.append(["PDF Name", "Status (1=Success, 0=Fail)"])

    max_workers = get_max_workers(len(pdf_files))
    print(f"Found {len(pdf_files)} PDFs; running with {max_workers} worker(s)")

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pdf = {executor.submit(run_pipeline, pdf): pdf for pdf in pdf_files}
        for future in as_completed(future_to_pdf):
            pdf = future_to_pdf[future]
            results[pdf.name] = future.result()

    # Keep report rows stable (same order as file discovery).
    for pdf in pdf_files:
        ws.append([pdf.name, results.get(pdf.name, 0)])

    wb.save(OUTPUT_EXCEL)
    print("=" * 90)
    print(f"Report saved to: {OUTPUT_EXCEL}")
    print("Automation completed")
    print("=" * 90)


if __name__ == "__main__":
    main()
