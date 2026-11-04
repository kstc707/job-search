"""The six report definitions.

Each report has one SQL Command (``sql/reports``), one baseline data source (``sql/baseline``),
one control query (``sql/controls``), and a column layout. ``totals`` lists the additive columns
that get a grand total; averages, rates, medians and distinct counts are not additive, so they are
left out of the total row on purpose.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    label: str
    kind: str  # text | int | money | dec1


@dataclass(frozen=True)
class Report:
    id: str
    title: str
    date_field: str
    command: str
    baseline_source: str
    control: str
    columns: tuple[Column, ...]
    totals: tuple[str, ...]

    def col_index(self, name: str) -> int:
        return [c.name for c in self.columns].index(name)


def C(name, label, kind="int"):
    return Column(name, label, kind)


REPORTS: dict[str, Report] = {r.id: r for r in [
    Report("R1", "Permit Activity Summary", "Applied date",
           "reports/R1_permit_activity.sql", "baseline/permit_detail.sql", "controls/R1_control.sql",
           (C("DistrictCode", "District", "text"), C("PermitTypeCode", "Permit type", "text"),
            C("Status", "Status", "text"), C("PermitCount", "Permits"),
            C("TotalValuation", "Valuation", "money"), C("MissingValuationCount", "No valuation")),
           ("PermitCount", "TotalValuation", "MissingValuationCount")),
    Report("R2", "Fee Revenue by District", "Fee assessed date",
           "reports/R2_fee_revenue.sql", "baseline/fee_detail.sql", "controls/R2_control.sql",
           (C("DistrictCode", "District", "text"), C("FeeTypeCode", "Fee type", "text"),
            C("FeeCount", "Fees"), C("Assessed", "Assessed", "money"),
            C("Collected", "Collected", "money"), C("Outstanding", "Outstanding", "money")),
           ("FeeCount", "Assessed", "Collected", "Outstanding")),
    Report("R3", "Outstanding Fee Aging", "Fee assessed date (aged as of end date)",
           "reports/R3_fee_aging.sql", "baseline/fee_detail.sql", "controls/R3_control.sql",
           (C("DistrictCode", "District", "text"), C("AgingBucket", "Days past due", "text"),
            C("FeeCount", "Fees"), C("Balance", "Balance", "money")),
           ("FeeCount", "Balance")),
    Report("R4", "Inspection Results", "Inspection scheduled date",
           "reports/R4_inspection_results.sql", "baseline/inspection_detail.sql", "controls/R4_control.sql",
           (C("DistrictCode", "District", "text"), C("InspectionTypeCode", "Inspection", "text"),
            C("Scheduled", "Scheduled"), C("Passed", "Pass"), C("Failed", "Fail"),
            C("Partial", "Partial"), C("Canceled", "Canceled"), C("Pending", "Pending"),
            C("PassRatePct", "Pass rate %", "dec1")),
           ("Scheduled", "Passed", "Failed", "Partial", "Canceled", "Pending")),
    Report("R5", "Permit Processing Time", "Applied date (issued permits)",
           "reports/R5_processing_time.sql", "baseline/permit_detail.sql", "controls/R5_control.sql",
           (C("PermitTypeCode", "Permit type", "text"), C("TargetDays", "Target days"),
            C("IssuedCount", "Issued"), C("TotalDays", "Total days"),
            C("AvgDays", "Avg days", "dec1"), C("MedianDays", "Median days", "dec1"),
            C("P90Days", "P90 days", "dec1"), C("WithinTargetCount", "Within target")),
           ("IssuedCount", "TotalDays", "WithinTargetCount")),
    Report("R6", "Inspector Workload", "Inspection scheduled date",
           "reports/R6_inspector_workload.sql", "baseline/inspection_detail.sql", "controls/R6_control.sql",
           (C("InspectorName", "Inspector", "text"), C("HomeDistrict", "Home district", "text"),
            C("Assigned", "Assigned"), C("Completed", "Completed"), C("Passed", "Pass"),
            C("Failed", "Fail"), C("Canceled", "Canceled"), C("DistinctPermits", "Permits")),
           ("Assigned", "Completed", "Passed", "Failed", "Canceled")),
]}
