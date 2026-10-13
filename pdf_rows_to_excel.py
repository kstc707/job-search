"""
Dump every row of a PDF into Excel as-is: no headers, nothing skipped.

Put this script and your PDF in the same folder, then press Run in VS Code.
Creates raw_rows.xlsx next to the PDF.

Requires:  pip install pdfplumber pandas openpyxl
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

# PDF file name in this folder. "" = use the first .pdf found.
PDF_FILE = ""
OUTPUT_FILE = "raw_rows.xlsx"

folder = Path(__file__).resolve().parent
pdf_path = folder / PDF_FILE if PDF_FILE else next(iter(sorted(folder.glob("*.pdf"))), None)
if pdf_path is None or not pdf_path.exists():
    sys.exit(f"No PDF found in {folder}")

rows = []
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text = page.extract_text(layout=True) or ""
        for line in text.splitlines():
            if line.strip():
                # Split into columns wherever there are 2+ spaces
                rows.append(re.split(r"\s{2,}", line.strip()))

pd.DataFrame(rows).to_excel(folder / OUTPUT_FILE, index=False, header=False)
print(f"Wrote {len(rows)} rows from {pdf_path.name} to {OUTPUT_FILE}")
