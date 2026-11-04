# Refresh benchmark

20 runs per mode, same environment, medians. Generated 2026-11-04T00:08:25+00:00 by `python -m permit_reports bench`.

Environment: SQL Server 16.0.4305.5, Python 3.13.18, 4 CPUs, Linux-6.18.44-fc-v230-x86_64-with-glibc2.39. SQL Server in a local Docker container (no real network hop).

Baseline = fetch every detail row, select and summarize on the client (table-linked report). Optimized = parameterized SQL Command, server filters and aggregates.

## full-year, all districts (2025-01-01 to 2025-12-31 | district ALL | status ALL)

All six reports, median refresh: **2.530 s baseline -> 0.259 s optimized** (90% less time, 9.8x faster).

| Report | Baseline median (s) | Optimized median (s) | Rows fetched: baseline | Rows fetched: optimized |
|---|---:|---:|---:|---:|
| R1 | 0.4528 | 0.0206 | 40,000 | 349 |
| R2 | 0.4885 | 0.0250 | 30,000 | 56 |
| R3 | 0.4760 | 0.0143 | 30,000 | 40 |
| R4 | 0.3332 | 0.0285 | 30,000 | 56 |
| R5 | 0.4504 | 0.1198 | 40,000 | 10 |
| R6 | 0.3233 | 0.0425 | 30,000 | 24 |

## one quarter, one district (2025-04-01 to 2025-06-30 | district CEN | status ALL)

All six reports, median refresh: **2.508 s baseline -> 0.067 s optimized** (97% less time, 37.4x faster).

| Report | Baseline median (s) | Optimized median (s) | Rows fetched: baseline | Rows fetched: optimized |
|---|---:|---:|---:|---:|
| R1 | 0.4456 | 0.0066 | 40,000 | 28 |
| R2 | 0.4795 | 0.0105 | 30,000 | 7 |
| R3 | 0.4736 | 0.0094 | 30,000 | 3 |
| R4 | 0.3260 | 0.0114 | 30,000 | 7 |
| R5 | 0.4501 | 0.0139 | 40,000 | 10 |
| R6 | 0.3216 | 0.0139 | 30,000 | 24 |
