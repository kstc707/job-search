"""CLI: python -m permit_reports {setup,generate,run,controls,reconcile,bench}"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bench, db, engine, exporters, generator, reconcile
from .params import ReportParams
from .reports import REPORTS

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = ROOT / "out"


def cmd_setup(_):
    db.ensure_database()
    with db.connect() as conn:
        db.run_script(conn, "01_schema.sql")
        db.run_script(conn, "02_indexes.sql")
    print(f"schema and indexes created in {db.settings()['database']}")


def cmd_generate(a):
    data = generator.generate(seed=a.seed)
    with db.connect() as conn:
        counts = generator.load(conn, data)
    facts = counts["Permit"] + counts["Fee"] + counts["Inspection"]
    print(f"loaded {facts:,} records (seed {a.seed}): " + ", ".join(f"{k} {v:,}" for k, v in counts.items()))
    if a.csv:
        generator.write_csv(data, ROOT / "data")
        print("CSV copies written to data/")


def cmd_run(a):
    p = ReportParams.parse(a.start, a.end, a.district, a.status)
    with db.connect() as conn:
        res = engine.refresh(conn, a.report, p, a.mode)
    cols = res.report.columns
    print(f"{res.report.id} {res.report.title} | {p.label()} | {a.mode} | {res.seconds:.3f}s, "
          f"{res.rows_fetched:,} rows fetched")
    print("  ".join(c.label for c in cols))
    for r in res.rows:
        print("  ".join(exporters.fmt(v, c.kind) for v, c in zip(r, cols)))
    print("GRAND TOTAL " + ", ".join(f"{k}={v:,}" for k, v in res.totals.items()))
    stem = f"{a.report}_{p.start}_{p.end}_{p.district}_{p.status}".replace(" ", "")
    if a.pdf:
        print("wrote", exporters.to_pdf(res, OUT / f"{stem}.pdf"))
    if a.xlsx:
        print("wrote", exporters.to_xlsx(res, OUT / f"{stem}.xlsx"))


def cmd_controls(a):
    p = ReportParams.parse(a.start, a.end, a.district, a.status)
    with db.connect() as conn:
        for rid, r in REPORTS.items():
            ctl = engine.control_totals(conn, rid, p)
            print(f"{rid} {r.title}: " + ", ".join(f"{k}={v:,}" for k, v in ctl.items()))


def cmd_reconcile(_):
    with db.connect() as conn:
        checks = reconcile.run_all(conn, OUT / "reconcile")
    reconcile.write_results(checks, RESULTS)
    bad = [c for c in checks if not c.ok]
    print(f"{len(checks) - len(bad)}/{len(checks)} checks passed; see results/reconciliation.md")
    for c in bad:
        print("FAILED", c)
    return 1 if bad else 0


def cmd_bench(a):
    with db.connect() as conn:
        result = bench.run(conn, runs=a.runs)
    bench.write_results(result, RESULTS)
    for name, s in result["scenarios"].items():
        print(f"{name}: suite median {s['suite_baseline_median_s']:.3f}s baseline -> "
              f"{s['suite_optimized_median_s']:.3f}s optimized")
    print("see results/benchmark.md")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="permit_reports")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="create database, tables and indexes")
    g = sub.add_parser("generate", help="generate and load the synthetic data")
    g.add_argument("--seed", type=int, default=2026)
    g.add_argument("--csv", action="store_true", help="also write CSV copies to data/")
    r = sub.add_parser("run", help="refresh one report")
    r.add_argument("report", choices=sorted(REPORTS))
    r.add_argument("--start", required=True)
    r.add_argument("--end", required=True)
    r.add_argument("--district", default="ALL")
    r.add_argument("--status", default="ALL")
    r.add_argument("--mode", choices=["optimized", "baseline"], default="optimized")
    r.add_argument("--pdf", action="store_true")
    r.add_argument("--xlsx", action="store_true")
    k = sub.add_parser("controls", help="print the control totals (to check a Crystal export by hand)")
    for flag in ("--start", "--end"):
        k.add_argument(flag, required=True)
    k.add_argument("--district", default="ALL")
    k.add_argument("--status", default="ALL")
    sub.add_parser("reconcile", help="check all six reports against control totals")
    b = sub.add_parser("bench", help="time baseline vs SQL Command refresh")
    b.add_argument("--runs", type=int, default=20)
    a = ap.parse_args(argv)
    return {"setup": cmd_setup, "generate": cmd_generate, "run": cmd_run, "controls": cmd_controls,
            "reconcile": cmd_reconcile, "bench": cmd_bench}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
