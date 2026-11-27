import numpy as np
import pandas as pd

from lade_eta import evaluate as E
from lade_eta import ingest, notify


def test_parse_times_attaches_reference_year():
    df = pd.DataFrame({c: ["05-18 08:16:00"] for c in ingest.TIME_COLS})
    out = ingest.parse_times(df, 2022)
    assert out["accept_time"].iloc[0] == pd.Timestamp("2022-05-18 08:16:00")


def test_clean_counts_each_rule_once(tasks):
    df = tasks.head(10).copy()
    df.loc[1, "order_id"] = df.loc[0, "order_id"]                                   # duplicate
    df.loc[2, "pickup_time"] = df.loc[2, "accept_time"] - pd.Timedelta(minutes=1)    # impossible order
    df.loc[3, "accept_time"] = df.loc[3, "time_window_end"]                          # accepted too late
    df.loc[3, "pickup_time"] = df.loc[3, "accept_time"] + pd.Timedelta(minutes=10)
    out, report = ingest.clean(df)
    assert report.dropped == {"duplicate_order_id": 1, "window_end_before_start": 0,
                              "pickup_before_accept": 1, "accepted_after_window_end": 1}
    assert len(out) == report.rows_out == 7


def test_flag_top_share_flags_exact_count_with_ties():
    flags = E.flag_top_share(np.zeros(100), 0.05)
    assert flags.sum() == 5


def test_alert_metrics():
    m = E.alert_metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert m["recall"] == 0.5 and m["precision"] == 0.5 and m["true_alerts"] == 1


def test_eta_metrics():
    m = E.eta_metrics([10, 20, 100], [10, 50, 100])
    assert m["mae_min"] == 10 and m["within_30_min"] == 1.0


def test_notification_gives_time_only_when_past_window():
    late = notify.compose(7, "2022-10-01 13:00", "2022-10-01 15:00", "2022-10-01 11:00", eta_minutes=250, risk=0.31)
    assert "13:00-15:00" in late.message and "around 15:15" in late.message
    unsure = notify.compose(8, "2022-10-01 13:00", "2022-10-01 15:00", "2022-10-01 11:00", eta_minutes=150, risk=0.2)
    assert "around" not in unsure.message and "after 15:00" in unsure.message
