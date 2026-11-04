# Building the six reports in Crystal Reports

Crystal Reports runs only on Windows, so the harness in this repository cannot open or refresh a
`.rpt` file. What it does provide is everything a `.rpt` is built from: the SQL Server database,
the exact SQL Command text for each report (`../sql/reports/R*.sql`, already in Crystal's
`{?Parameter}` syntax), and the control totals every export has to match. This guide turns those
into real `.rpt` files and gives you a way to time them in Crystal itself.

> The timings in `../results/benchmark.md` come from the Python harness, not from Crystal.
> If you quote a Crystal refresh time, measure it with step 6 below and record it in
> `../results/crystal-timings.md`.

## 1. Prerequisites

- Crystal Reports 2020 (or 2016), on Windows.
- Microsoft ODBC Driver 18 for SQL Server.
- The database from the main README (`docker compose up -d`, then `python -m permit_reports setup`
  and `generate`). From Windows, the server is the Docker host's address, port 1433.
- An ODBC System DSN named `PermitReporting` pointing at that server and database. With Driver 18
  on a dev container, tick "Trust server certificate".

## 2. Create the report from the SQL Command (the "after" version)

For each `R1` to `R6`:

1. File > New > Blank Report.
2. Database Expert > Create New Connection > ODBC (RDO) > `PermitReporting` > log on.
3. Under the connection, double-click **Add Command**.
4. In the right-hand pane click **Create...** four times to add the parameters, all type **String**:
   `StartDate` (default `2025-01-01`), `EndDate` (default `2025-12-31`), `District` (default `ALL`),
   `Status` (default `ALL`). Names must match the file exactly.
5. Paste the whole of `sql/reports/R<n>_*.sql` into the command box. OK. Rename the command to the
   report id (`R1`, ...).

## 3. Lock the parameters to pick lists

Crystal substitutes command parameters into the SQL as text. A free-typed `District` value can
change the query, so restrict it.

- Field Explorer > Parameter Fields > `District` > Edit. List of Values: Static. Add `ALL`, `CEN`,
  `NTH`, `STH`, `EST`, `WST`, `HBR`, `UNV`, `IND`. Set **Allow custom values = False**.
- `Status`: same, with `ALL`, `Applied`, `In Review`, `Issued`, `Finaled`, `Expired`, `Withdrawn`.
- `StartDate` / `EndDate`: set Prompt Text to "YYYY-MM-DD" and an Edit Mask of `0000-00-00`.
  (A bad date makes SQL Server's `CAST` fail, so it cannot slip through silently.) If you switch
  them to Date-type parameters, check how your Crystal version writes them into the command with
  Database > Show SQL Query before relying on it.

## 4. Layout

Group and summarize to match the column layout in `permit_reports/reports.py`:

| Report | Groups (in order) | Detail fields | Report-footer Sum on |
|---|---|---|---|
| R1 | DistrictCode | PermitTypeCode, Status, PermitCount, TotalValuation, MissingValuationCount | PermitCount, TotalValuation, MissingValuationCount |
| R2 | DistrictCode | FeeTypeCode, FeeCount, Assessed, Collected, Outstanding | FeeCount, Assessed, Collected, Outstanding |
| R3 | DistrictCode | AgingBucket, FeeCount, Balance | FeeCount, Balance |
| R4 | DistrictCode | InspectionTypeCode, Scheduled ... Pending, PassRatePct | Scheduled, Passed, Failed, Partial, Canceled, Pending |
| R5 | (none) | every column | IssuedCount, TotalDays, WithinTargetCount |
| R6 | (none) | every column | Assigned, Completed, Passed, Failed, Canceled |

Do **not** sum `PassRatePct`, `AvgDays`, `MedianDays`, `P90Days` or `DistinctPermits`: they are
not additive (an average of averages is wrong, and one permit can be visited by two inspectors).
Put the parameter values in the page header (drag the parameter fields there) so every export
says what it was filtered on.

Save as `crystal/R<n>_<name>.rpt`.

## 5. Export and reconcile

1. Refresh with a parameter set, e.g. `2025-01-01`, `2025-12-31`, `ALL`, `ALL`.
2. File > Export > **Adobe Acrobat (PDF)**, then File > Export > **Microsoft Excel Workbook
   Data-only (.xlsx)**.
3. Print the control totals for the same parameters and compare the report-footer sums in both files:

   ```bash
   python -m permit_reports controls --start 2025-01-01 --end 2025-12-31
   ```

   Every number must match to the cent. If one does not, Database > Show SQL Query shows what
   Crystal actually sent.

## 6. Time the refresh in Crystal (before vs after)

**Before version** (for comparison): a second copy of each report built from linked tables
(Database Expert > add `Permit`, `District`, `PermitType` and link them on the ID columns) with
the filtering in Report > Selection Formulas > Record, e.g. for R1:

```
{Permit.AppliedDate} >= CDate({?StartDate}) and {Permit.AppliedDate} <= CDate({?EndDate})
and ({?District} = "ALL" or {District.DistrictCode} = {?District})
and ({?Status} = "ALL" or {Permit.Status} = {?Status})
```

and the group summaries built in the report. Check Database > Show SQL Query: if the `WHERE`
clause is missing or partial, Crystal is pulling every row and filtering on the client, which is
exactly the baseline the harness reproduces.

**Measure**: refresh each version 20 times with the same parameters on the same machine and read
Report > Performance Information > Performance Timing after each refresh (or use a stopwatch
from clicking Refresh to the first page drawn). Take the median, and record the runs in
`../results/crystal-timings.md`.
