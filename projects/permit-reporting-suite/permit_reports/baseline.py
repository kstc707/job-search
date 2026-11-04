"""The "before" version of each report: fetch every detail row, then select and summarize on the
client, one record at a time, the way a Crystal report with linked tables and a record selection
formula that is not pushed to the server does.

The rules here must match the SQL Commands exactly; ``tests/test_reports.py`` checks that the two
paths return identical rows for many parameter combinations.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from .params import ReportParams

ONE = Decimal("0.1")
ZERO = Decimal("0.00")


def round1(x: Decimal) -> Decimal:
    return x.quantize(ONE, rounding=ROUND_HALF_UP)


def percentile_cont(sorted_vals: list[int], p: float) -> float:
    """SQL Server PERCENTILE_CONT: linear interpolation at row (n - 1) * p."""
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def round_float1(x: float) -> Decimal:
    return round1(Decimal(repr(x)))


def _keep(p: ReportParams, d, district, status) -> bool:
    return (p.start <= d <= p.end
            and (p.district == "ALL" or district == p.district)
            and (p.status == "ALL" or status == p.status))


def r1(rows, cols, p: ReportParams):
    ix = {c: i for i, c in enumerate(cols)}
    g = defaultdict(lambda: [0, ZERO, 0])
    for r in rows:
        if not _keep(p, r[ix["AppliedDate"]], r[ix["DistrictCode"]], r[ix["Status"]]):
            continue
        acc = g[(r[ix["DistrictCode"]], r[ix["PermitTypeCode"]], r[ix["Status"]])]
        acc[0] += 1
        v = r[ix["Valuation"]]
        if v is None:
            acc[2] += 1
        else:
            acc[1] += v
    return [(*k, a[0], a[1], a[2]) for k, a in sorted(g.items())]


def _paid_as_of(r, ix, end):
    pd = r[ix["PaidDate"]]
    return r[ix["PaidAmount"]] if pd is not None and pd <= end else ZERO


def r2(rows, cols, p: ReportParams):
    ix = {c: i for i, c in enumerate(cols)}
    g = defaultdict(lambda: [0, ZERO, ZERO])
    for r in rows:
        if r[ix["IsVoided"]] or not _keep(p, r[ix["AssessedDate"]], r[ix["DistrictCode"]], r[ix["Status"]]):
            continue
        acc = g[(r[ix["DistrictCode"]], r[ix["FeeTypeCode"]])]
        acc[0] += 1
        acc[1] += r[ix["Amount"]]
        acc[2] += _paid_as_of(r, ix, p.end)
    return [(*k, a[0], a[1], a[2], a[1] - a[2]) for k, a in sorted(g.items())]


def aging_bucket(days_past_due: int) -> str:
    if days_past_due <= 0:
        return "0 Current"
    if days_past_due <= 30:
        return "1 1-30"
    if days_past_due <= 60:
        return "2 31-60"
    if days_past_due <= 90:
        return "3 61-90"
    return "4 90+"


def r3(rows, cols, p: ReportParams):
    ix = {c: i for i, c in enumerate(cols)}
    g = defaultdict(lambda: [0, ZERO])
    for r in rows:
        if r[ix["IsVoided"]] or not _keep(p, r[ix["AssessedDate"]], r[ix["DistrictCode"]], r[ix["Status"]]):
            continue
        bal = r[ix["Amount"]] - _paid_as_of(r, ix, p.end)
        if bal <= 0:
            continue
        acc = g[(r[ix["DistrictCode"]], aging_bucket((p.end - r[ix["DueDate"]]).days))]
        acc[0] += 1
        acc[1] += bal
    return [(*k, a[0], a[1]) for k, a in sorted(g.items())]


RESULTS = ("Pass", "Fail", "Partial", "Canceled", "Pending")


def r4(rows, cols, p: ReportParams):
    ix = {c: i for i, c in enumerate(cols)}
    g = defaultdict(lambda: dict.fromkeys(RESULTS, 0))
    for r in rows:
        if not _keep(p, r[ix["ScheduledDate"]], r[ix["DistrictCode"]], r[ix["Status"]]):
            continue
        g[(r[ix["DistrictCode"]], r[ix["InspectionTypeCode"]])][r[ix["Result"]]] += 1
    out = []
    for k, c in sorted(g.items()):
        completed = c["Pass"] + c["Fail"] + c["Partial"]
        rate = round1(Decimal(100 * c["Pass"]) / completed) if completed else None
        out.append((*k, sum(c.values()), c["Pass"], c["Fail"], c["Partial"], c["Canceled"], c["Pending"], rate))
    return out


def r5(rows, cols, p: ReportParams):
    ix = {c: i for i, c in enumerate(cols)}
    days_by_type: dict[str, list[int]] = defaultdict(list)
    target: dict[str, int] = {}
    for r in rows:
        if r[ix["IssuedDate"]] is None or not _keep(p, r[ix["AppliedDate"]], r[ix["DistrictCode"]], r[ix["Status"]]):
            continue
        t = r[ix["PermitTypeCode"]]
        days_by_type[t].append((r[ix["IssuedDate"]] - r[ix["AppliedDate"]]).days)
        target[t] = r[ix["TargetDays"]]
    out = []
    for t in sorted(days_by_type):
        d = sorted(days_by_type[t])
        total = sum(d)
        out.append((t, target[t], len(d), total, round1(Decimal(total) / len(d)),
                    round_float1(percentile_cont(d, 0.5)), round_float1(percentile_cont(d, 0.9)),
                    sum(1 for x in d if x <= target[t])))
    return out


def r6(rows, cols, p: ReportParams):
    ix = {c: i for i, c in enumerate(cols)}
    g = defaultdict(lambda: {"n": 0, "Pass": 0, "Fail": 0, "Partial": 0, "Canceled": 0, "permits": set()})
    for r in rows:
        if not _keep(p, r[ix["ScheduledDate"]], r[ix["DistrictCode"]], r[ix["Status"]]):
            continue
        acc = g[(r[ix["InspectorName"]], r[ix["HomeDistrict"]])]
        acc["n"] += 1
        res = r[ix["Result"]]
        if res in acc:
            acc[res] += 1
        acc["permits"].add(r[ix["PermitId"]])
    return [(*k, a["n"], a["Pass"] + a["Fail"] + a["Partial"], a["Pass"], a["Fail"], a["Canceled"],
             len(a["permits"])) for k, a in sorted(g.items())]


AGGREGATORS = {"R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5, "R6": r6}
