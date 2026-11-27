import numpy as np
import pandas as pd
import pytest

from lade_eta import features as F
from lade_eta.repository import FrameRepository
from lade_eta.store import request_features


def T(s):
    return pd.Timestamp(f"2022-08-01 {s}")


def test_haversine_known_distance():
    # One degree of latitude is about 111.2 km.
    assert F.haversine_km(30.0, 120.0, 31.0, 120.0) == pytest.approx(111.19, abs=0.1)


def test_courier_workload_counts_open_tasks_excluding_self():
    df = pd.DataFrame({
        "courier_id": [1, 1, 1, 2],
        "accept_time": [T("08:00"), T("08:30"), T("10:00"), T("08:45")],
        "pickup_time": [T("09:00"), T("11:00"), T("10:30"), T("09:00")],
    })
    w = F.courier_workload(df)
    # 08:00: nothing else accepted yet. 08:30: the 08:00 task is still open.
    # 10:00: 08:00 task picked up at 09:00, 08:30 task still open -> 1. Courier 2 is independent.
    assert w["courier_open_tasks"].tolist() == [0, 1, 1, 0]
    assert w["courier_tasks_today"].tolist() == [0, 1, 2, 0]


def test_history_uses_only_earlier_days(tasks):
    """Rewriting every outcome on the last day must not change that day's features (no leakage)."""
    base = F.build(tasks)
    last_day = tasks["accept_time"].dt.normalize().max()
    changed = tasks.copy()
    on_last = changed["pickup_time"].dt.normalize() == last_day
    changed.loc[on_last, "pickup_time"] = changed.loc[on_last, "time_window_end"] + pd.Timedelta(minutes=300)
    after = F.build(changed)
    rows = base["accept_time"].dt.normalize() == last_day
    hist_cols = [c for c in F.NUMERIC if "_hist_" in c]
    pd.testing.assert_frame_equal(base.loc[rows, hist_cols], after.loc[rows, hist_cols])
    # ...while the targets on that day did change, so the test is not vacuous.
    assert after.loc[rows, F.TARGET_LATE].sum() > base.loc[rows, F.TARGET_LATE].sum()


def test_new_courier_gets_global_prior(frame):
    first_day = frame["accept_time"].dt.normalize().min()
    rows = frame[frame["accept_time"].dt.normalize() == first_day]
    assert (rows["courier_hist_n"] == 0).all()
    assert rows["courier_hist_mean_minutes"].isna().all()


def test_split_is_time_ordered(frame):
    train, valid, test = F.split_by_date(frame, "08-25", "09-01", 2022)
    assert train["accept_time"].max() < valid["accept_time"].min()
    assert valid["accept_time"].max() < test["accept_time"].min()
    assert len(train) + len(valid) + len(test) == len(frame)


def test_serving_features_match_training_features(tasks, frame):
    """The API path (snapshot + request) must produce the same numbers the model was trained on."""
    repo = FrameRepository(tasks)
    day = pd.Timestamp("2022-08-20")
    batch = frame[frame["accept_time"].dt.normalize() == day].reset_index(drop=True)
    req = repo.tasks[repo.tasks["accept_time"].dt.normalize() == day].reset_index(drop=True)
    served = request_features(req, repo.snapshot(day))
    for col in F.NUMERIC:
        np.testing.assert_allclose(served[col].to_numpy(float), batch[col].to_numpy(float), rtol=1e-9, err_msg=col)
