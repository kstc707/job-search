"""Serving-time features.

Training computes history features for every row in one batch (features.history_features). The API
scores one task at a time, so it needs the same numbers from a stored summary: per courier, area
(AOI) and region, how many tasks finished before today, how many were late, and their total minutes.

`HistorySnapshot.as_of(df, day)` builds that summary from outcomes on days before `day`;
`request_features` turns API requests into the exact feature columns the models were trained on.
A test checks that both paths give identical values.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import features as F


@dataclass
class HistorySnapshot:
    as_of_day: pd.Timestamp
    courier: pd.DataFrame  # index courier_id; columns n, n_late, sum_minutes
    aoi: pd.DataFrame
    region: pd.DataFrame
    global_rate: float

    @staticmethod
    def as_of(df: pd.DataFrame, day: pd.Timestamp) -> "HistorySnapshot":
        """Summary of outcomes picked up strictly before `day`. `df` must already have targets."""
        day = pd.Timestamp(day).normalize()
        past = df[df["pickup_time"] < day]
        capped = past[F.TARGET_MINUTES].clip(upper=F.MINUTES_CAP)

        def agg(key: str) -> pd.DataFrame:
            return (
                pd.DataFrame({key: past[key].astype("int64"), "late": past[F.TARGET_LATE], "m": capped})
                .groupby(key)
                .agg(n=("late", "size"), n_late=("late", "sum"), sum_minutes=("m", "sum"))
            )

        rate = float(past[F.TARGET_LATE].mean()) if len(past) else 0.0
        return HistorySnapshot(day, agg("courier_id"), agg("aoi_id"), agg("region_id"), rate)

    def lookup(self, keys: pd.Series, table: pd.DataFrame, prefix: str, with_count: bool = True) -> pd.DataFrame:
        hit = table.reindex(keys.astype("int64").to_numpy())
        n = hit["n"].fillna(0).to_numpy()
        late = hit["n_late"].fillna(0).to_numpy()
        out = pd.DataFrame(index=keys.index)
        if with_count:
            out[f"{prefix}_hist_n"] = n
        out[f"{prefix}_hist_late_rate"] = (late + F.PRIOR_WEIGHT * self.global_rate) / (n + F.PRIOR_WEIGHT)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[f"{prefix}_hist_mean_minutes"] = np.where(n > 0, hit["sum_minutes"].to_numpy() / n, np.nan)
        return out


REQUEST_COLUMNS = [
    "courier_id", "region_id", "aoi_id", "aoi_type", "lng", "lat", "accept_time", "time_window_start",
    "time_window_end", "accept_gps_lng", "accept_gps_lat", "courier_open_tasks", "courier_tasks_today",
]


def request_features(req: pd.DataFrame, snap: HistorySnapshot) -> pd.DataFrame:
    """Feature rows for tasks described by REQUEST_COLUMNS (workload counts supplied by the caller)."""
    req = req.reset_index(drop=True)
    for col in ["accept_time", "time_window_start", "time_window_end"]:
        req[col] = pd.to_datetime(req[col])
    out = pd.concat(
        [
            req,
            F.time_features(req),
            snap.lookup(req["courier_id"], snap.courier, "courier"),
            snap.lookup(req["aoi_id"], snap.aoi, "aoi"),
            snap.lookup(req["region_id"], snap.region, "region", with_count=False),
        ],
        axis=1,
    )
    return out
