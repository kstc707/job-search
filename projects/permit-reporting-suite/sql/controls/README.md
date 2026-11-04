# Control totals

One query per report, written independently of the report SQL so a shared mistake cannot hide:
no joins to lookup tables for codes (district and status are resolved with `IN` subqueries
against IDs), `BETWEEN` on dates instead of the half-open range, and plain base-table aggregates.
Each returns a single row whose columns are named after the report columns they must equal.
`python -m permit_reports reconcile` compares them against the report grand totals and against
the totals read back out of the PDF and Excel exports.
