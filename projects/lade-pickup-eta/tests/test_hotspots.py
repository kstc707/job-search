import pandas as pd

from lade_eta.hotspots import courier_concentration, hotspots, recommend


def _rows(courier, n, late, open_tasks=5, hour=11, region=1):
    end = pd.Timestamp(f"2022-10-03 {hour}:00")
    return pd.DataFrame({
        "region_id": region, "courier_id": courier, "late": [1] * late + [0] * (n - late),
        "flagged": [True] * late + [False] * (n - late), "courier_open_tasks": open_tasks, "time_window_end": end,
    })


def test_concentrated_region_names_the_couriers():
    df = pd.concat([_rows(1, 20, 10), _rows(2, 20, 6), _rows(3, 200, 2), _rows(4, 200, 1)])
    text = recommend(df)
    assert text.startswith("Couriers 1, 2, 3 hold") and "of this region's 19 late pickups" in text


def test_workload_rule_when_late_is_spread_across_couriers():
    parts = [_rows(c, 40, 1) for c in range(10, 30)] + [_rows(c, 10, 3, open_tasks=40) for c in range(30, 40)]
    text = recommend(pd.concat(parts))
    assert "Cap open tasks per courier at 30" in text


def test_hotspots_sorted_by_late_count_and_concentration_shares():
    df = pd.concat([_rows(1, 50, 5, region=1), _rows(2, 50, 20, region=2)])
    table = hotspots(df)
    assert list(table.index) == [2, 1] and table["recommendation"].str.len().gt(0).all()
    conc = courier_concentration(df)
    assert conc["couriers"] == 2 and conc["top_1pct_share"] == 20 / 25
