"""Refresh-time benchmark: baseline (client-side selection) vs SQL Command (server-side).

Same machine, same database, same connection, alternating which mode goes first on each run so
neither always benefits from a warmer cache. One warm-up refresh per report and mode is run first
and discarded. Medians are reported because a single slow run (GC, I/O) skews a mean.
"""
from __future__ import annotations

import json
import os
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path

from . import db, engine
from .params import ReportParams
from .reports import REPORTS

SCENARIOS = {
    "full-year, all districts": ReportParams.parse("2025-01-01", "2025-12-31"),
    "one quarter, one district": ReportParams.parse("2025-04-01", "2025-06-30", "CEN"),
}


def run(conn, runs: int = 20) -> dict:
    timings = {s: {m: {r: [] for r in REPORTS} for m in ("baseline", "optimized")} for s in SCENARIOS}
    fetched = {s: {m: {} for m in ("baseline", "optimized")} for s in SCENARIOS}
    for name, p in SCENARIOS.items():
        for rid in REPORTS:
            for mode in ("baseline", "optimized"):
                engine.refresh(conn, rid, p, mode)  # warm-up, discarded
    for i in range(runs):
        order = ("baseline", "optimized") if i % 2 == 0 else ("optimized", "baseline")
        for name, p in SCENARIOS.items():
            for mode in order:
                for rid in REPORTS:
                    res = engine.refresh(conn, rid, p, mode)
                    timings[name][mode][rid].append(res.seconds)
                    fetched[name][mode][rid] = res.rows_fetched

    _, ver = db.query(conn, "SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(30))")
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs": runs,
        "environment": {
            "sql_server": ver[0][0], "python": platform.python_version(),
            "os": platform.platform(), "cpus": os.cpu_count(),
            "network": "SQL Server in a local Docker container (no real network hop)",
        },
        "scenarios": {},
    }
    for name, p in SCENARIOS.items():
        per_report = {}
        for rid in REPORTS:
            b, o = timings[name]["baseline"][rid], timings[name]["optimized"][rid]
            per_report[rid] = {
                "baseline_median_s": round(statistics.median(b), 4),
                "optimized_median_s": round(statistics.median(o), 4),
                "baseline_rows_fetched": fetched[name]["baseline"][rid],
                "optimized_rows_fetched": fetched[name]["optimized"][rid],
            }
        suite_b = [sum(timings[name]["baseline"][r][i] for r in REPORTS) for i in range(runs)]
        suite_o = [sum(timings[name]["optimized"][r][i] for r in REPORTS) for i in range(runs)]
        out["scenarios"][name] = {
            "params": p.label(),
            "reports": per_report,
            "suite_baseline_median_s": round(statistics.median(suite_b), 3),
            "suite_optimized_median_s": round(statistics.median(suite_o), 3),
            "suite_baseline_runs_s": [round(x, 3) for x in suite_b],
            "suite_optimized_runs_s": [round(x, 3) for x in suite_o],
        }
    return out


def write_results(result: dict, results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
    env = result["environment"]
    lines = [
        "# Refresh benchmark",
        "",
        f"{result['runs']} runs per mode, same environment, medians. Generated {result['generated_at']} "
        "by `python -m permit_reports bench`.",
        "",
        f"Environment: SQL Server {env['sql_server']}, Python {env['python']}, {env['cpus']} CPUs, {env['os']}. "
        f"{env['network']}.",
        "",
        "Baseline = fetch every detail row, select and summarize on the client (table-linked report). "
        "Optimized = parameterized SQL Command, server filters and aggregates.",
        "",
    ]
    for name, s in result["scenarios"].items():
        b, o = s["suite_baseline_median_s"], s["suite_optimized_median_s"]
        lines += [
            f"## {name} ({s['params']})",
            "",
            f"All six reports, median refresh: **{b:.3f} s baseline -> {o:.3f} s optimized** "
            f"({(1 - o / b) * 100:.0f}% less time, {b / o:.1f}x faster).",
            "",
            "| Report | Baseline median (s) | Optimized median (s) | Rows fetched: baseline | Rows fetched: optimized |",
            "|---|---:|---:|---:|---:|",
        ]
        for rid, r in s["reports"].items():
            lines.append(f"| {rid} | {r['baseline_median_s']:.4f} | {r['optimized_median_s']:.4f} | "
                         f"{r['baseline_rows_fetched']:,} | {r['optimized_rows_fetched']:,} |")
        lines.append("")
    (results_dir / "benchmark.md").write_text("\n".join(lines))
