# Baseline ("before") data sources

These are what the first version of each report pulled: the linked tables in Crystal's Database
Expert, every row, no WHERE and no GROUP BY. The record selection formula (dates, district, status)
and the group summaries ran inside the report engine, so every refresh moved the whole table set
over the wire and evaluated each record on the client.

The harness reproduces that: `permit_reports/baseline.py` filters and aggregates these rows in
Python, record by record, with the same rules as the SQL Commands in `../reports/`. The tests
check that both paths return identical rows.
