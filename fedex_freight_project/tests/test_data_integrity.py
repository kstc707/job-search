"""Raw downloads are real data and the extracted KPIs tie out to the filings' own totals."""
import pandas as pd
import pytest


def test_fred_files_are_csv_not_html(root):
    files = list((root / "data/raw/fred").glob("*.csv"))
    assert len(files) >= 18
    for f in files:
        head = f.read_text()[:200]
        assert head.startswith("observation_date,"), f.name
        assert "<html" not in head.lower()


def test_sec_files_are_filings(root):
    for f in (root / "data/raw/sec_edgar").glob("*.htm"):
        txt = f.read_text(errors="replace")[:5000].lower()
        assert "<html" in txt or "<xbrl" in txt or "<?xml" in txt, f.name
        assert "page not found" not in txt and "access denied" not in txt


def test_fiscal_quarters_complete_and_contiguous(kpis):
    assert kpis["fiscal_period"].iloc[0] == "FY2017Q4" and kpis["fiscal_period"].iloc[-1] == "FY2026Q4"
    assert len(kpis) == 37
    gaps = kpis["period_end"].diff().dropna().dt.days
    assert gaps.between(89, 93).all()


def test_fy2026_ties_to_10k(kpis):
    fy = kpis[kpis["fiscal_year"] == 2026]
    assert fy["revenue_musd"].sum() == pytest.approx(8795, abs=1)          # 10-K FY2026 revenue
    assert fy["operating_income_musd"].sum() == pytest.approx(616, abs=1)  # segment op. income (10-K, Q4 release)
    ads = (fy["avg_daily_shipments_k"] * fy["operating_days"]).sum() / fy["operating_days"].sum()
    assert ads == pytest.approx(86.1, abs=0.05)                            # 10-K "Total average daily shipments"


def test_fy2026q4_matches_fdxf_release(kpis):
    q = kpis.set_index("fiscal_period").loc["FY2026Q4"]
    assert q["revenue_musd"] == 2408 and q["operating_income_musd"] == 158
    assert q["avg_daily_shipments_k"] == 86.7 and q["weight_per_shipment_lbs"] == 948
    assert q["revenue_per_shipment_usd"] == pytest.approx(415.22) and q["revenue_per_cwt_usd"] == pytest.approx(43.79)


def test_internal_identity_rps_equals_cwt_times_weight(kpis):
    implied = kpis["revenue_per_cwt_usd"] * kpis["weight_per_shipment_lbs"] / 100
    rel = (implied / kpis["revenue_per_shipment_usd"] - 1).abs()
    assert rel.max() < 0.01  # rounding of reported stats only


def test_recast_ties_to_annual_totals(recast):
    by = recast.groupby("calendar_year")[["revenue_musd", "operating_income_musd"]].sum()
    assert by.loc[2025].tolist() == [8778, 1022]
    assert by.loc[2024].tolist() == [9092, 1532]
    ads = recast["total_shipments"] / recast["operating_days"] / 1000
    assert (ads - recast["avg_daily_shipments_k"]).abs().max() < 0.01


def test_fuel_table_complete(root):
    t = pd.read_csv(root / "data/raw/external/fedex_freight_fuel_surcharge_table_2025-06-09.csv")
    assert t["eia_index_cents"].tolist() == list(range(330, 801))
    assert t["surcharge_pct"].is_monotonic_increasing
    assert t.set_index("eia_index_cents").loc[[330, 379, 800], "surcharge_pct"].tolist() == [31.0, 33.7, 75.8]


def test_calendar_tonnage_approximation_matches_fdxf_actuals(kpis, recast):
    """Option C sums fiscal quarters ending Feb-Nov into calendar years; check against FDXF's true CY tonnage."""
    k = kpis.assign(tons=kpis["avg_daily_shipments_k"] * 1e3 * kpis["weight_per_shipment_lbs"] * kpis["operating_days"] / 2000,
                    year=kpis["period_end"].dt.year)
    approx = k.groupby("year")["tons"].sum()
    actual = recast.groupby("calendar_year")["total_tonnage"].sum()
    for y in (2024, 2025):
        assert abs(approx[y] / actual[y] - 1) < 0.01
