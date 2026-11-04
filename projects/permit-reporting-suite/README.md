# Permit & Inspection Reporting Suite

**SQL Server · T-SQL · Crystal Reports SQL Commands · Python harness**

A city permitting office needs six recurring reports: permit activity, fee revenue, fee aging,
inspection results, processing time and inspector workload. Each one is filtered by date range,
district and permit status, and each one is exported to PDF and Excel. The numbers go to finance and
council, so they have to be right, and staff refresh them all day, so they have to be fast.

This project builds that suite on 100,000 synthetic records in a real SQL Server 2022 instance.
It proves every report against independent control totals and measures what moving the work into
SQL saves.

## Results (measured, reproducible)

| What | Result | Source |
|---|---|---|
| Synthetic records | 100,000 (40,000 permits, 30,000 fees, 30,000 inspections), seeded | `permit_reports/generator.py` |
| Reports | 6, each with StartDate / EndDate / District / Status parameters | `sql/reports/` |
| Reconciliation | **60 / 60 checks pass**: 6 reports × 10 parameter sets, each checking SQL vs baseline rows, totals vs control, PDF totals vs control, Excel totals vs control | [`results/reconciliation.md`](results/reconciliation.md) |
| Refresh, all six reports, full year, all districts | **2.53 s → 0.26 s** median over 20 runs (9.8× faster) | [`results/benchmark.md`](results/benchmark.md) |
| Refresh, all six reports, one quarter, one district | **2.51 s → 0.07 s** median over 20 runs | same |
| Rows sent to the client per refresh | 30,000–40,000 → 3–349 | same |
| Tests | 85 pass (19 offline unit tests + 66 against SQL Server) | `tests/` |

Timings are from SQL Server in a local Docker container (no network hop), so they mostly measure
row transfer and client-side processing. Over a real network to a shared server the baseline gets
slower and the gap gets wider, but those numbers were not measured here.

## How it works

```
 generator.py ──(seeded, 100k rows)──▶ SQL Server: Permit, Fee, Inspection + 5 lookups
                                              │
          ┌───────────────────────────────────┼───────────────────────────────────┐
          ▼                                   ▼                                   ▼
 sql/baseline/*.sql                  sql/reports/R1..R6.sql              sql/controls/R1..R6.sql
 every detail row, no WHERE          SQL Command: WHERE + GROUP BY       independent single-row
          │                          on the server, {?param} syntax      totals (written a
 baseline.py: select + summarize              │                          different way)
 on the client, record by record              │                                   │
          └──────────── must be equal ────────┤                                   │
                                              ▼                                   │
                                  exporters.py: PDF + Excel                       │
                                  read totals back from the files ── must equal ──┘
```

- **Before (baseline).** A report built on linked tables pulls every row and filters it in
  the report engine: Crystal's record selection formula, when Crystal cannot push it to the
  server. `baseline.py` reproduces that: fetch all detail rows, then select and summarize in
  Python one record at a time.
- **After (SQL Commands).** Each report is one parameterized query that filters on an indexed
  date column with a half-open range (`>= start AND < end + 1 day`), aggregates with `GROUP BY`,
  and returns only the summary rows. The files use Crystal's `'{?StartDate}'` syntax so they paste
  straight into Crystal's Add Command dialog. The harness turns the placeholders into real
  driver parameters (`db.translate_command`), so values are never spliced into the SQL.
- **Indexes** (`sql/02_indexes.sql`): one covering index per report date column, so each command
  seeks a date range and never touches the base table.
- **Control totals** (`sql/controls/`) are deliberately written a different way: `IN`
  subqueries on IDs instead of joins on codes, `BETWEEN` instead of the half-open range, `IIF`
  instead of `CASE`. A shared mistake would have to be made twice, in two different ways, to hide.

### The six reports

| Id | Report | Date filter | Grand totals |
|---|---|---|---|
| R1 | Permit Activity Summary (district × type × status) | applied | permits, valuation, missing valuations |
| R2 | Fee Revenue (district × fee type) | fee assessed | fees, assessed, collected (as of end date), outstanding |
| R3 | Outstanding Fee Aging (current / 1-30 / 31-60 / 61-90 / 90+) | fee assessed, aged at end date | fees, balance |
| R4 | Inspection Results with pass rate | scheduled | scheduled, pass, fail, partial, canceled, pending |
| R5 | Processing Time: avg, median, P90, within target | applied (issued permits) | issued, total days, within target |
| R6 | Inspector Workload | scheduled | assigned, completed, pass, fail, canceled |

### Problems the reconciliation is built to catch

- **NULLs.** A few permits have no valuation. `SUM` skips them quietly, so R1 counts them in a
  separate column, and a test checks that count against the table.
- **Voided fees** are excluded everywhere, and a test checks the R2 count equals the non-voided rows.
- **As-of logic.** A payment made after the end date does not count as collected. R2's outstanding
  total and R3's aging balance are computed in different shapes and must match to the cent (tested).
- **Non-additive measures.** Pass rate, averages, medians and distinct-permit counts are never
  summed into a grand total.
- **Empty ranges** return zero totals, not NULL or a missing row.
- **Leap day and single-day ranges** are in the parameter grid, to catch off-by-one date filters.
- **Parameter injection.** Crystal pastes command parameters into the SQL as text. The harness
  only accepts pick-list values, and the Crystal guide restricts parameters to pick lists too.

## Run it

Needs Docker and Python 3.11+.

```bash
cd projects/permit-reporting-suite
cp .env.example .env                  # set your own MSSQL_SA_PASSWORD
set -a; . ./.env; set +a
docker compose up -d                  # SQL Server 2022 Developer
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

```bash
python -m permit_reports setup        # database, tables, indexes
python -m permit_reports generate     # 100,000 records, seed 2026 (add --csv for CSV copies)
python -m permit_reports run R2 --start 2025-01-01 --end 2025-12-31 --district HBR --pdf --xlsx
python -m permit_reports reconcile    # 60 checks -> results/reconciliation.md
python -m permit_reports bench --runs 20   # -> results/benchmark.md
pytest                                # 85 tests; DB tests skip if SQL Server is not reachable
```

## Crystal Reports

[`crystal/README.md`](crystal/README.md) is the build guide: create each `.rpt` from its SQL
Command, lock the parameters to pick lists, lay out groups and footer sums, export to PDF and
Excel, check the exports against `python -m permit_reports controls`, and time before and after
inside Crystal.

## Limitations

- **Crystal itself is not in the loop.** It runs only on Windows, and this repository cannot run
  it. The SQL Commands are what a `.rpt` runs, and the PDF and Excel exports here are produced by
  reportlab and openpyxl, not by Crystal's export engine. The refresh times are the harness's, not
  Crystal's. Crystal timings belong in `results/crystal-timings.md`, which stays empty until
  someone measures them on Windows.
- **The baseline is a reconstruction.** Crystal pushes part of a record selection formula to the
  server when it can, so a real "before" report may be faster than this all-rows baseline.
- **The numbers come from a local container**, with no network latency and no concurrent users.
- **The data is synthetic.** Distributions are plausible, not drawn from any real jurisdiction.
- **No row-level security or scheduling.** A production deployment would add a read-only report
  login, a scheduler (SQL Agent or BusinessObjects) and report distribution.
