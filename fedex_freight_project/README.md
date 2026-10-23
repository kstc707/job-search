# FedEx Freight: LTL demand project (public data only)

A short, real analysis to send with a FedEx Freight Data Science Internship application. It uses only public
data: FRED macro and freight indicators, BTS/ORNL Freight Analysis Framework v5.7.1, and SEC EDGAR filings
(FedEx Freight Holding Co. and pre-spin-off FedEx Corp segment reporting). No synthetic data.

**Status:** data collected and EDA done. The project direction is still to be picked; see
[reports/eda_summary.md](reports/eda_summary.md).

## Layout

```
data/README.md        inventory: every file, source URL, date range, granularity, key columns, failures, caveats
data/raw/             downloaded inputs (FRED CSVs, FAF5, SEC HTML); large files git-ignored
data/processed/       extracted FedEx Freight KPI CSVs (+ FAF5 parquet, git-ignored)
scripts/              download, parse, EDA
reports/              eda_summary.md, eda_output.txt, figures/
```

## Reproduce

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash scripts/download_data.sh                                    # ~350 MB, mostly FAF5
.venv/bin/python -I scripts/parse_fedex_freight_segment.py data/raw/sec_edgar/fedex_corp_earnings data/processed/_fedex_corp_segment_rows.csv
.venv/bin/python -I scripts/parse_fdxf_recast.py data/raw/sec_edgar/8-K_2026-08-06_ex99_recast_cy2025_cy2024.htm data/processed/fdxf_calendar_quarterly_kpis_recast.csv
.venv/bin/python -I scripts/faf5_to_parquet.py data/raw/faf5/FAF5.7.1/FAF5.7.1.csv data/processed/faf5_7_1.parquet
.venv/bin/python -I scripts/eda.py > reports/eda_output.txt
```
