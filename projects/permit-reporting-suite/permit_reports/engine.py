"""Refresh a report in either mode and time it.

* ``optimized``: run the parameterized SQL Command; the server filters and aggregates and
  returns only the summary rows.
* ``baseline``: fetch the full detail source and filter/aggregate on the client.

"Refresh" means what Crystal's Refresh button does: query the database and build the summary
rows. Rendering and export are timed separately (see ``exporters``).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal

from . import baseline, db
from .params import ReportParams
from .reports import REPORTS, Report


@dataclass
class ReportResult:
    report: Report
    params: ReportParams
    mode: str
    rows: list[tuple]
    rows_fetched: int
    seconds: float
    totals: dict = field(default_factory=dict)


def grand_totals(report: Report, rows: list[tuple]) -> dict:
    out = {}
    for name in report.totals:
        i = report.col_index(name)
        kind = report.columns[i].kind
        out[name] = sum((r[i] for r in rows), Decimal("0.00") if kind == "money" else 0)
    return out


def refresh(conn, report_id: str, params: ReportParams, mode: str = "optimized") -> ReportResult:
    report = REPORTS[report_id]
    t0 = time.perf_counter()
    if mode == "optimized":
        sql, _ = db.load_command(report.command)
        _, raw = db.query(conn, sql, params.as_sql())
        rows = [tuple(r) for r in raw]
        fetched = len(rows)
    elif mode == "baseline":
        sql, _ = db.load_command(report.baseline_source)
        cols, raw = db.query(conn, sql)
        rows = baseline.AGGREGATORS[report_id](raw, cols, params)
        fetched = len(raw)
    else:
        raise ValueError(f"unknown mode {mode!r}")
    seconds = time.perf_counter() - t0
    return ReportResult(report, params, mode, rows, fetched, seconds, grand_totals(report, rows))


def control_totals(conn, report_id: str, params: ReportParams) -> dict:
    sql, _ = db.load_command(REPORTS[report_id].control)
    cols, rows = db.query(conn, sql, params.as_sql())
    return dict(zip(cols, rows[0]))
