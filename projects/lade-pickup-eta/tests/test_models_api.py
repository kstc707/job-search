import pandas as pd
import pytest
from fastapi.testclient import TestClient

from lade_eta import api
from lade_eta import features as F
from lade_eta.repository import FrameRepository


def test_models_predict_valid_ranges(bundle, frame):
    test = frame[frame["accept_time"] >= "2022-09-01"]
    assert (bundle.eta.predict(test) >= 0).all()
    risk = bundle.risk.predict(test)
    assert ((risk >= 0) & (risk <= 1)).all()


def test_risk_model_learns_courier_reliability(bundle, frame):
    """Synthetic couriers with higher ids are late more often; the model should rank them higher."""
    test = frame[frame["accept_time"] >= "2022-09-01"]
    risk = pd.Series(bundle.risk.predict(test), index=test.index)
    by_courier = risk.groupby(test["courier_id"]).mean()
    assert by_courier.loc[11] > by_courier.loc[0]


def test_unseen_region_does_not_crash(bundle, frame):
    row = frame.head(1).copy()
    row["region_id"] = pd.Categorical([999])
    assert bundle.eta.predict(row).shape == (1,)


@pytest.fixture()
def client(bundle, tasks):
    repo = FrameRepository(tasks)
    api.app.dependency_overrides[api.get_bundle] = lambda: bundle
    api.app.dependency_overrides[api.get_repository] = lambda: repo
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


TASK = {
    "courier_id": 11, "region_id": 2, "aoi_id": 1, "aoi_type": 1, "lng": 121.51, "lat": 31.2,
    "accept_time": "2022-09-05T09:00:00", "time_window_start": "2022-09-05T10:00:00",
    "time_window_end": "2022-09-05T12:00:00", "accept_gps_lng": 121.41, "accept_gps_lat": 31.21,
}


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and 0 <= body["alert_threshold"] <= 1


def test_predict_looks_up_workload_and_returns_consistent_times(client):
    r = client.post("/predict", json=TASK)
    assert r.status_code == 200, r.text
    body = r.json()
    est = pd.Timestamp(body["estimated_pickup"])
    expected = pd.Timestamp(TASK["accept_time"]) + pd.Timedelta(minutes=body["eta_minutes"])
    assert abs(est - expected) <= pd.Timedelta(seconds=1)
    assert (body["notification"] is not None) == body["flagged"]


def test_predict_rejects_task_accepted_after_window(client):
    bad = {**TASK, "accept_time": "2022-09-05T12:30:00"}
    assert client.post("/predict", json=bad).status_code == 422


def test_at_risk_returns_only_flagged_open_tasks(client, tasks):
    as_of = "2022-09-05T11:00:00"
    r = client.get("/at-risk", params={"as_of": as_of})
    assert r.status_code == 200, r.text
    items = r.json()
    open_ids = set(FrameRepository(tasks).open_tasks(pd.Timestamp(as_of))["order_id"])
    assert all(i["flagged"] and i["order_id"] in open_ids for i in items)
    ends = [i["time_window_end"] for i in items]
    assert ends == sorted(ends)


def test_feature_list_is_what_models_use(bundle):
    assert bundle.eta.booster.feature_name() == F.FEATURES
