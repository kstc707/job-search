"""Tests that need no database."""
from datetime import date
from decimal import Decimal

import pytest

from permit_reports import baseline, db, generator
from permit_reports.params import ReportParams
from permit_reports.reports import REPORTS


def test_translate_command_turns_quoted_placeholders_into_parameters():
    sql, names = db.translate_command("WHERE d >= CAST('{?StartDate}' AS date) AND ('{?District}' = 'ALL')")
    assert sql == "WHERE d >= CAST(%(StartDate)s AS date) AND (%(District)s = 'ALL')"
    assert names == ["District", "StartDate"]


def test_translate_command_escapes_percent_and_rejects_unquoted_placeholder():
    sql, _ = db.translate_command("SELECT '100%' WHERE x = '{?Status}'")
    assert sql == "SELECT '100%%' WHERE x = %(Status)s"
    with pytest.raises(ValueError, match="unquoted"):
        db.translate_command("WHERE d >= {?StartDate}")


def test_every_report_command_uses_exactly_the_four_parameters():
    for r in REPORTS.values():
        _, names = db.load_command(r.command)
        assert set(names) <= {"StartDate", "EndDate", "District", "Status"}
        assert {"StartDate", "EndDate", "District", "Status"} == set(names), r.id
        _, cnames = db.load_command(r.control)
        assert set(cnames) == set(names), r.id


def test_split_batches_on_go_lines_only():
    script = "CREATE TABLE a (x int);\nGO\n-- only a comment\nGO\nSELECT 'GO';\ngo\n"
    assert db.split_batches(script) == ["CREATE TABLE a (x int);", "SELECT 'GO';"]


@pytest.mark.parametrize("kwargs", [
    {"district": "XYZ"}, {"status": "Approved"}, {"district": "CEN' OR 1=1 --"},
])
def test_params_reject_values_outside_the_pick_lists(kwargs):
    with pytest.raises(ValueError):
        ReportParams(date(2025, 1, 1), date(2025, 1, 31), **kwargs)


def test_params_reject_end_before_start():
    with pytest.raises(ValueError):
        ReportParams.parse("2025-02-01", "2025-01-31")


def test_percentile_cont_matches_sql_server_interpolation():
    assert baseline.percentile_cont([1, 2, 3, 4], 0.5) == 2.5
    assert baseline.percentile_cont([10], 0.9) == 10
    assert baseline.percentile_cont(list(range(1, 11)), 0.9) == pytest.approx(9.1)


@pytest.mark.parametrize("days,bucket", [(-5, "0 Current"), (0, "0 Current"), (1, "1 1-30"),
                                         (30, "1 1-30"), (31, "2 31-60"), (90, "3 61-90"), (91, "4 90+")])
def test_aging_bucket_boundaries(days, bucket):
    assert baseline.aging_bucket(days) == bucket


def test_round1_is_half_up_like_sql_round():
    assert baseline.round1(Decimal("2.25")) == Decimal("2.3")
    assert baseline.round1(Decimal("2.24")) == Decimal("2.2")


def test_generator_makes_exactly_100k_fact_records_and_is_deterministic():
    a, b = generator.generate(seed=7), generator.generate(seed=7)
    assert len(a["Permit"]) + len(a["Fee"]) + len(a["Inspection"]) == 100_000
    assert a["Fee"][:50] == b["Fee"][:50] and a["Inspection"][-50:] == b["Inspection"][-50:]
    assert generator.generate(seed=8)["Permit"][:50] != a["Permit"][:50]


def test_generator_respects_table_constraints():
    d = generator.generate()
    for _, _, _, _, status, applied, issued, finaled, _ in d["Permit"]:
        assert issued is None or issued >= applied
        assert (issued is None) == (status in ("Withdrawn", "Applied", "In Review"))
        assert finaled is None or status == "Finaled"
    for _, _, _, assessed, due, amount, paid, paid_date, _ in d["Fee"]:
        assert amount > 0 and 0 <= paid <= amount
        assert (paid == 0) == (paid_date is None)
        assert assessed <= generator.AS_OF and due > assessed
