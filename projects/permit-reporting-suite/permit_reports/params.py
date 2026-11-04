"""Report parameters and their validation.

Crystal substitutes command parameters into the SQL as text, so a free-typed value can change the
query. The Crystal build guide uses pick lists; the harness enforces the same allowed values here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

DISTRICTS = ("CEN", "NTH", "STH", "EST", "WST", "HBR", "UNV", "IND")
STATUSES = ("Applied", "In Review", "Issued", "Finaled", "Expired", "Withdrawn")


@dataclass(frozen=True)
class ReportParams:
    start: date
    end: date
    district: str = "ALL"
    status: str = "ALL"

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError(f"EndDate {self.end} is before StartDate {self.start}")
        if self.district != "ALL" and self.district not in DISTRICTS:
            raise ValueError(f"unknown district {self.district!r}")
        if self.status != "ALL" and self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}")

    @classmethod
    def parse(cls, start: str, end: str, district: str = "ALL", status: str = "ALL") -> "ReportParams":
        return cls(date.fromisoformat(start), date.fromisoformat(end), district, status)

    def as_sql(self) -> dict:
        return {"StartDate": self.start.isoformat(), "EndDate": self.end.isoformat(),
                "District": self.district, "Status": self.status}

    def label(self) -> str:
        return f"{self.start} to {self.end} | district {self.district} | status {self.status}"
