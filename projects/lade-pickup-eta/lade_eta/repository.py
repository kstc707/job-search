"""Where the API gets live state: open tasks, courier workload, and history up to a given day.

PostgresRepository answers with SQL against the `pickups` table (indexes in schema.sql).
FrameRepository answers the same questions from a pandas DataFrame, for tests and offline demos.
Both return the same columns, and a test checks they agree.

The dataset is historical, so "now" is a replay time passed by the caller (`as_of`).
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

from . import features as F
from .store import REQUEST_COLUMNS, HistorySnapshot


class Repository(Protocol):
    def snapshot(self, day: pd.Timestamp) -> HistorySnapshot: ...
    def open_tasks(self, as_of: pd.Timestamp, region_id: int | None = None) -> pd.DataFrame: ...
    def workload(self, courier_id: int, at: pd.Timestamp) -> tuple[int, int]: ...


OPEN_TASKS_SQL = """
SELECT p.order_id, p.courier_id, p.region_id, p.aoi_id, p.aoi_type, p.lng, p.lat,
       p.accept_time, p.time_window_start, p.time_window_end, p.accept_gps_lng, p.accept_gps_lat,
       o.n AS courier_open_tasks, d.n AS courier_tasks_today
FROM pickups p
-- Courier workload at the moment this task was accepted (same definition as features.courier_workload):
-- other tasks with accept_time <= p.accept_time < pickup_time ...
CROSS JOIN LATERAL (
    SELECT count(*) AS n FROM pickups q
    WHERE q.courier_id = p.courier_id AND q.order_id <> p.order_id
      AND tsrange(q.accept_time, q.pickup_time, '[)') @> p.accept_time
) o
-- ... and other tasks accepted earlier the same day.
CROSS JOIN LATERAL (
    SELECT count(*) AS n FROM pickups q
    WHERE q.courier_id = p.courier_id AND q.order_id <> p.order_id
      AND q.accept_time >= date_trunc('day', p.accept_time) AND q.accept_time <= p.accept_time
) d
WHERE tsrange(p.accept_time, p.pickup_time, '[)') @> %(as_of)s::timestamp
  AND p.time_window_end > %(as_of)s
  AND (%(region)s::int IS NULL OR p.region_id = %(region)s::int)
ORDER BY p.time_window_end, p.order_id
"""

HISTORY_SQL = """
SELECT {key} AS key, count(*) AS n,
       sum((pickup_time > time_window_end)::int) AS n_late,
       sum(least(extract(epoch FROM pickup_time - accept_time) / 60, %(cap)s)) AS sum_minutes
FROM pickups WHERE pickup_time < %(day)s GROUP BY {key}
"""


class PostgresRepository:
    def __init__(self, database_url: str, pool_size: int = 4):
        from psycopg_pool import ConnectionPool

        self.database_url = database_url
        # Reuse open connections: opening one costs about 8 ms, more than the workload query itself.
        self.pool = ConnectionPool(database_url, min_size=1, max_size=pool_size, open=True)
        self._snapshots: dict[pd.Timestamp, HistorySnapshot] = {}

    def _query(self, sql: str, params: dict) -> pd.DataFrame:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)

    def snapshot(self, day: pd.Timestamp) -> HistorySnapshot:
        day = pd.Timestamp(day).normalize()
        if day not in self._snapshots:  # history only changes once a day, so cache per day
            tables = {}
            for key in ("courier_id", "aoi_id", "region_id"):
                t = self._query(HISTORY_SQL.format(key=key), {"day": day, "cap": F.MINUTES_CAP})
                t = t.astype({"key": "int64", "n": "int64", "n_late": "int64", "sum_minutes": "float64"})
                tables[key] = t.set_index("key").rename_axis(key)
            n = tables["region_id"]["n"].sum()
            rate = float(tables["region_id"]["n_late"].sum() / n) if n else 0.0
            self._snapshots[day] = HistorySnapshot(day, tables["courier_id"], tables["aoi_id"], tables["region_id"], rate)
        return self._snapshots[day]

    def open_tasks(self, as_of: pd.Timestamp, region_id: int | None = None) -> pd.DataFrame:
        df = self._query(OPEN_TASKS_SQL, {"as_of": pd.Timestamp(as_of).to_pydatetime(), "region": region_id})
        for col in ["accept_gps_lng", "accept_gps_lat", "lng", "lat"]:
            df[col] = df[col].astype("float64")
        return df[["order_id", *REQUEST_COLUMNS]]

    def workload(self, courier_id: int, at: pd.Timestamp) -> tuple[int, int]:
        sql = """SELECT count(*) FILTER (WHERE pickup_time > %(at)s),
                        count(*) FILTER (WHERE accept_time >= date_trunc('day', %(at)s::timestamp))
                 FROM pickups WHERE courier_id = %(c)s AND accept_time <= %(at)s"""
        row = self._query(sql, {"c": int(courier_id), "at": pd.Timestamp(at).to_pydatetime()}).iloc[0]
        return int(row.iloc[0]), int(row.iloc[1])


class FrameRepository:
    def __init__(self, tasks: pd.DataFrame):
        self.tasks = F.add_targets(tasks.reset_index(drop=True))
        self.tasks = pd.concat([self.tasks, F.courier_workload(self.tasks)], axis=1)

    def snapshot(self, day: pd.Timestamp) -> HistorySnapshot:
        return HistorySnapshot.as_of(self.tasks, day)

    def open_tasks(self, as_of: pd.Timestamp, region_id: int | None = None) -> pd.DataFrame:
        t = self.tasks
        as_of = pd.Timestamp(as_of)
        mask = (t["accept_time"] <= as_of) & (t["pickup_time"] > as_of) & (t["time_window_end"] > as_of)
        if region_id is not None:
            mask &= t["region_id"] == region_id
        out = t[mask].sort_values(["time_window_end", "order_id"])
        return out[["order_id", *REQUEST_COLUMNS]].reset_index(drop=True)

    def workload(self, courier_id: int, at: pd.Timestamp) -> tuple[int, int]:
        at = pd.Timestamp(at)
        mine = self.tasks[(self.tasks["courier_id"] == courier_id) & (self.tasks["accept_time"] <= at)]
        open_n = int((mine["pickup_time"] > at).sum())
        today = int((mine["accept_time"] >= at.normalize()).sum())
        return open_n, today


def as_python(value):
    """numpy scalars -> plain Python for JSON responses."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    return value
