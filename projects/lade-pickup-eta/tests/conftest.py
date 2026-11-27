"""Small synthetic LaDe-shaped data so tests run in seconds without downloading anything."""
import pandas as pd
import pytest

from lade_eta import features as F
from lade_eta.models import LightGbmEta, LightGbmLateRisk, ModelBundle, RegionMedianEta
from lade_eta.store import HistorySnapshot
from lade_eta.synthetic import make_tasks


@pytest.fixture(scope="session")
def tasks() -> pd.DataFrame:
    return make_tasks()


@pytest.fixture(scope="session")
def frame(tasks) -> pd.DataFrame:
    return F.build(tasks)


@pytest.fixture(scope="session")
def bundle(frame) -> ModelBundle:
    train, valid, _ = F.split_by_date(frame, "08-25", "09-01", 2022)
    params = {"num_leaves": 7, "min_data_in_leaf": 10}
    eta = LightGbmEta(params=dict(params)).fit(train, valid)
    risk = LightGbmLateRisk(params=dict(params)).fit(train, valid)
    risk.set_threshold_for_budget(risk.predict(valid), 0.1)
    snap = HistorySnapshot.as_of(frame, frame["pickup_time"].max() + pd.Timedelta(days=1))
    return ModelBundle(eta=eta, risk=risk, baseline=RegionMedianEta().fit(train), snapshot=snap,
                       metadata={"city": "Test", "alert_budget": 0.1})
