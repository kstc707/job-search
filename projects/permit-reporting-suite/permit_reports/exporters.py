"""PDF and Excel exports, and readers that pull the grand-total row back out of each file.

Reading the totals back from the exported files (not from memory) is what proves the export did
not drop, round or reformat anything: ``reconcile`` compares them with the SQL control totals.
"""
from __future__ import annotations

import re
import subprocess
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .engine import ReportResult

TOTAL_LABEL = "GRAND TOTAL"
NUMBER_FORMATS = {"int": "#,##0", "money": "#,##0.00", "dec1": "0.0"}


def fmt(value, kind: str) -> str:
    if value is None:
        return ""
    if kind == "int":
        return f"{value:,}"
    if kind == "money":
        return f"{value:,.2f}"
    if kind == "dec1":
        return f"{value:.1f}"
    return str(value)


def _total_row(res: ReportResult) -> list:
    row = []
    for i, c in enumerate(res.report.columns):
        if i == 0:
            row.append(TOTAL_LABEL)
        else:
            row.append(res.totals.get(c.name))
    return row


def to_pdf(res: ReportResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    cols = res.report.columns
    header = [c.label for c in cols]
    body = [[fmt(v, c.kind) for v, c in zip(r, cols)] for r in res.rows]
    total = [fmt(v, c.kind) if i else v for i, (v, c) in enumerate(zip(_total_row(res), cols))]
    table = Table([header, *body, total], repeatRows=1)
    numeric = [i for i, c in enumerate(cols) if c.kind != "text"]
    style = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F2F4F7")]),
    ]
    style += [("ALIGN", (i, 0), (i, -1), "RIGHT") for i in numeric]
    table.setStyle(TableStyle(style))
    doc = SimpleDocTemplate(str(path), pagesize=landscape(letter), title=res.report.title,
                            leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    doc.build([
        Paragraph(f"{res.report.id} {res.report.title}", styles["Title"]),
        Paragraph(f"{res.params.label()} &nbsp;&nbsp; date field: {res.report.date_field}", styles["Normal"]),
        Spacer(1, 10), table,
    ])
    return path


def to_xlsx(res: ReportResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = res.report.id
    ws.append([f"{res.report.id} {res.report.title}"])
    ws.append([res.params.label()])
    ws.append([c.label for c in res.report.columns])
    for cell in ws[3]:
        cell.font = Font(bold=True)
    cols = res.report.columns
    for r in [*res.rows, _total_row(res)]:
        ws.append([float(v) if isinstance(v, Decimal) and c.kind == "dec1" else v for v, c in zip(r, cols)])
    for row in ws.iter_rows(min_row=4):
        for cell, c in zip(row, cols):
            if c.kind in NUMBER_FORMATS:
                cell.number_format = NUMBER_FORMATS[c.kind]
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for i, c in enumerate(cols):
        ws.column_dimensions[chr(65 + i)].width = max(12, len(c.label) + 4)
    wb.save(path)
    return path


def _parse_number(text: str, kind: str):
    text = text.replace(",", "")
    return Decimal(text) if kind == "money" else int(text)


def read_pdf_totals(res: ReportResult, path: Path) -> dict:
    """Extract the GRAND TOTAL line with pdftotext and map its numbers onto the total columns."""
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                          capture_output=True, text=True).stdout
    line = next(l for l in text.splitlines() if l.strip().startswith(TOTAL_LABEL))
    numbers = re.findall(r"-?[\d,]+(?:\.\d+)?", line[line.index(TOTAL_LABEL) + len(TOTAL_LABEL):])
    names = [c for c in res.report.columns[1:] if c.name in res.report.totals]
    if len(numbers) != len(names):
        raise ValueError(f"{path.name}: expected {len(names)} totals, found {numbers}")
    return {c.name: _parse_number(n, c.kind) for c, n in zip(names, numbers)}


def read_xlsx_totals(res: ReportResult, path: Path) -> dict:
    ws = load_workbook(path, read_only=True).active
    for row in ws.iter_rows(values_only=True):
        if row and row[0] == TOTAL_LABEL:
            out = {}
            for c, v in zip(res.report.columns, row):
                if c.name in res.report.totals:
                    out[c.name] = Decimal(str(v)).quantize(Decimal("0.01")) if c.kind == "money" else int(v)
            return out
    raise ValueError(f"{path.name}: no {TOTAL_LABEL} row")
