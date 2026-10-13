"""
Dump every row of a PDF into Excel as-is: no headers, nothing skipped.

Works for data that LOOKS like columns but is not a real table (text
separated by gaps, some cells empty). Columns are found from where the text
sits on the page, so an empty cell stays empty instead of shifting the
values after it to the left.

Put this script and your PDF in the same folder, then press Run in VS Code.
Creates raw_rows.xlsx next to the PDF.

Requires:  pip install pdfplumber pandas openpyxl
"""

import sys
from pathlib import Path

import pandas as pd
import pdfplumber

# PDF file name in this folder. "" = use the first .pdf found.
PDF_FILE = ""
OUTPUT_FILE = "raw_rows.xlsx"

# Words closer than this (in points) are joined into one cell, e.g. "Alice Smith".
# Raise it if names/phrases get split across cells; lower it if separate
# columns get merged.
WORD_GAP = 6

# Words whose vertical positions differ by less than this are on the same row.
LINE_TOLERANCE = 3


def page_lines(page):
    """Return rows of cells; each cell is (x0, x1, text)."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    words.sort(key=lambda w: (round(w["top"]), w["x0"]))

    # Group words into lines by vertical position
    lines = []
    for w in words:
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])

    # Within a line, join nearby words into cells
    result = []
    for line in lines:
        line.sort(key=lambda w: w["x0"])
        cells = []
        for w in line:
            if cells and w["x0"] - cells[-1][1] <= WORD_GAP:
                x0, _, text = cells[-1]
                cells[-1] = (x0, w["x1"], text + " " + w["text"])
            else:
                cells.append((w["x0"], w["x1"], w["text"]))
        result.append(cells)
    return result


def find_columns(all_lines):
    """Find column x-ranges from the empty vertical gaps between them."""
    spans = sorted((x0, x1) for cells in all_lines if len(cells) > 1
                   for x0, x1, _ in cells)
    if not spans:  # every line has one cell -> one column
        return [(0, float("inf"))]
    columns = [list(spans[0])]
    for x0, x1 in spans[1:]:
        if x0 <= columns[-1][1]:          # overlaps current column
            columns[-1][1] = max(columns[-1][1], x1)
        else:                              # a gap -> new column
            columns.append([x0, x1])
    return columns


def column_for(x0, x1, columns):
    """Index of the column this cell overlaps most (or is nearest to)."""
    def score(col):
        overlap = min(x1, col[1]) - max(x0, col[0])
        return overlap if overlap > 0 else -min(abs(x0 - col[1]), abs(col[0] - x1))
    return max(range(len(columns)), key=lambda i: score(columns[i]))


def main():
    folder = Path(__file__).resolve().parent
    if PDF_FILE:
        pdf_path = folder / PDF_FILE
    else:
        pdfs = sorted(folder.glob("*.pdf"))
        pdf_path = pdfs[0] if pdfs else None
    if pdf_path is None or not pdf_path.exists():
        sys.exit(f"No PDF found in {folder}")

    with pdfplumber.open(pdf_path) as pdf:
        all_lines = [line for page in pdf.pages for line in page_lines(page)]
    if not all_lines:
        sys.exit("No text found. If the PDF is a scanned image it needs OCR first.")

    columns = find_columns(all_lines)
    rows = []
    for cells in all_lines:
        row = [""] * len(columns)
        for x0, x1, text in cells:
            i = column_for(x0, x1, columns)
            row[i] = (row[i] + " " + text).strip()
        rows.append(row)

    pd.DataFrame(rows).to_excel(folder / OUTPUT_FILE, index=False, header=False)
    print(f"Wrote {len(rows)} rows x {len(columns)} columns "
          f"from {pdf_path.name} to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
