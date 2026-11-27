"""Runs only when TEST_DATABASE_URL points at a disposable PostgreSQL database (CI provides one)."""
import os

import numpy as np
import pandas as pd
import pytest

from lade_eta import ingest
from lade_eta.repository import FrameRepository, PostgresRepository

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def repos(tasks):
    ingest.write_postgres(tasks, URL, replace=True)
    return PostgresRepository(URL), FrameRepository(tasks)


def test_round_trip(tasks, repos):
    back = ingest.read_postgres(URL, "ORDER BY order_id")
    assert len(back) == len(tasks)
    assert (back["pickup_time"].to_numpy() == tasks.sort_values("order_id")["pickup_time"].to_numpy()).all()


def test_sql_open_tasks_match_pandas(repos):
    pg, fr = repos
    as_of = pd.Timestamp("2022-09-05 11:00")
    a = pg.open_tasks(as_of).reset_index(drop=True)
    b = fr.open_tasks(as_of).reset_index(drop=True)
    assert len(a) > 0
    assert a["order_id"].tolist() == b["order_id"].tolist()
    assert a["courier_open_tasks"].tolist() == b["courier_open_tasks"].tolist()
    assert a["courier_tasks_today"].tolist() == b["courier_tasks_today"].tolist()


def test_sql_history_snapshot_matches_pandas(repos):
    pg, fr = repos
    day = pd.Timestamp("2022-08-20")
    a, b = pg.snapshot(day), fr.snapshot(day)
    assert a.global_rate == pytest.approx(b.global_rate)
    for name in ("courier", "aoi", "region"):
        ta, tb = getattr(a, name).sort_index(), getattr(b, name).sort_index()
        np.testing.assert_allclose(ta.to_numpy(float), tb.to_numpy(float), rtol=1e-9)


def test_sql_workload_matches_pandas(repos):
    pg, fr = repos
    at = pd.Timestamp("2022-08-10 12:05")
    assert pg.workload(3, at) == fr.workload(3, at)
