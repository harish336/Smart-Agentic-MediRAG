import os
import subprocess
import time
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

# ------------------------------------------------------------------
# RUN PIPELINE
# ------------------------------------------------------------------

def run_pipeline(pdf_path: Path):
    print("=" * 90)
    print(f"Processing: {pdf_path.name}")
    print("=" * 90)

    try:
        subprocess.run(
            [
                str(VENV_PYTHON),
                "-m",
                MODULE_NAME,
                str(pdf_path)
            ],
            check=True
        )
        print("✅ Success\n")
        return 1  # Success

    except subprocess.CalledProcessError:
        print("❌ Failed\n")
        return 0  # Failure


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("\n🚀 INGESTION AUTOMATION STARTED\n")

    if not VENV_PYTHON.exists():
        print("❌ .venv Python not found!")
        return

    pdf_files = list(DATA_FOLDER.glob("*.pdf"))

    if not pdf_files:
        print("⚠ No PDF files found.")
        return

    # Create Excel Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Ingestion Report"

    # Header
    ws.append(["PDF Name", "Status (1=Success, 0=Fail)"])

    for pdf in pdf_files:
        status = run_pipeline(pdf)
        ws.append([pdf.name, status])

    wb.save(OUTPUT_EXCEL)

    print("=" * 90)
    print(f"📊 Report saved to: {OUTPUT_EXCEL}")
    print("🎯 Automation Completed")
    print("=" * 90)


if __name__ == "__main__":
    main()