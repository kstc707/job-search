"""Integration tests against SQL Server: results, reconciliation, exports, data volume."""
import pytest

from permit_reports import db, engine, reconcile
from permit_reports.params import ReportParams
from permit_reports.reports import REPORTS

pytestmark = pytest.mark.db


def test_database_holds_100k_synthetic_records(conn):
    _, rows = db.query(conn, "SELECT (SELECT COUNT(*) FROM dbo.Permit), (SELECT COUNT(*) FROM dbo.Fee), "
                             "(SELECT COUNT(*) FROM dbo.Inspection)")
    assert rows[0] == (40_000, 30_000, 30_000)


@pytest.mark.parametrize("rid", sorted(REPORTS))
@pytest.mark.parametrize("params", reconcile.PARAM_SETS, ids=lambda p: p.label())
def test_report_reconciles_with_controls_and_exports(conn, tmp_path, rid, params):
    c = reconcile.check(conn, rid, params, tmp_path)
    assert c.rows_match_baseline, "SQL Command and baseline disagree"
    assert c.totals_match_control
    assert c.pdf_matches_control
    assert c.xlsx_matches_control


def test_empty_range_gives_zero_totals_not_nulls(conn):
    p = ReportParams.parse("2022-01-01", "2022-12-31")
    for rid in REPORTS:
        res = engine.refresh(conn, rid, p)
        assert res.rows == []
        assert all(v == 0 for v in engine.control_totals(conn, rid, p).values()), rid


def test_null_valuations_are_counted_not_silently_dropped(conn):
    p = ReportParams.parse("2023-01-01", "2025-12-31")
    res = engine.refresh(conn, "R1", p)
    _, rows = db.query(conn, "SELECT COUNT(*) FROM dbo.Permit WHERE Valuation IS NULL")
    assert res.totals["MissingValuationCount"] == rows[0][0] > 0


def test_r2_outstanding_equals_r3_aging_balance(conn):
    """Two reports, two shapes of the same money: they must agree."""
    for p in reconcile.PARAM_SETS[:5]:
        r2 = engine.refresh(conn, "R2", p).totals["Outstanding"]
        r3 = engine.refresh(conn, "R3", p).totals["Balance"]
        assert r2 == r3, p.label()


def test_voided_fees_are_excluded(conn):
    p = ReportParams.parse("2023-01-01", "2025-12-31")
    _, rows = db.query(conn, "SELECT COUNT(*) FROM dbo.Fee WHERE IsVoided = 0")
    assert engine.refresh(conn, "R2", p).totals["FeeCount"] == rows[0][0]


def test_sql_command_moves_far_fewer_rows_than_baseline(conn):
    p = ReportParams.parse("2025-01-01", "2025-12-31")
    for rid in REPORTS:
        opt, base = engine.refresh(conn, rid, p, "optimized"), engine.refresh(conn, rid, p, "baseline")
        assert opt.rows_fetched * 50 < base.rows_fetched, rid
