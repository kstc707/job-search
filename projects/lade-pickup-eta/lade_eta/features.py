"""Turn cleaned pickup tasks into model features.

Every feature is something a dispatcher would know at the moment the courier accepts the task
(the prediction time). Two rules keep the future out:

1. Courier workload uses only the current state at accept time: tasks already accepted and not yet
   picked up.
2. History features (late rate, typical duration per courier / area / region) use only outcomes
   from *earlier days*: a task's outcome is counted from the day it was picked up, and a row on
   day d sees only outcomes from days before d.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TARGET_MINUTES = "minutes_to_pickup"
TARGET_LATE = "late"

CATEGORICAL = ["region_id", "aoi_type"]
NUMERIC = [
    "accept_hour",
    "minutes_to_window_start",
    "minutes_to_window_end",
    "window_minutes",
    "window_end_hour",
    "km_courier_to_stop",
    "courier_open_tasks",
    "courier_tasks_today",
    "courier_hist_n",
    "courier_hist_late_rate",
    "courier_hist_mean_minutes",
    "aoi_hist_n",
    "aoi_hist_late_rate",
    "aoi_hist_mean_minutes",
    "region_hist_late_rate",
    "region_hist_mean_minutes",
]
FEATURES = CATEGORICAL + NUMERIC

# Smoothing strength for historical late rates: a courier with few past tasks is pulled toward the
# global rate instead of showing 0% or 100% after two tasks.
PRIOR_WEIGHT = 20.0
# Durations above a day are rare (pickups re-scheduled); cap them so one outlier does not move a mean.
MINUTES_CAP = 24 * 60


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out[TARGET_MINUTES] = (out["pickup_time"] - out["accept_time"]).dt.total_seconds() / 60
    out[TARGET_LATE] = (out["pickup_time"] > out["time_window_end"]).astype(int)
    return out


def haversine_km(lat1, lng1, lat2, lng2) -> np.ndarray:
    lat1, lng1, lat2, lng2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def time_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    acc = df["accept_time"]
    out["accept_hour"] = acc.dt.hour + acc.dt.minute / 60
    out["minutes_to_window_start"] = (df["time_window_start"] - acc).dt.total_seconds() / 60
    out["minutes_to_window_end"] = (df["time_window_end"] - acc).dt.total_seconds() / 60
    out["window_minutes"] = (df["time_window_end"] - df["time_window_start"]).dt.total_seconds() / 60
    out["window_end_hour"] = df["time_window_end"].dt.hour + df["time_window_end"].dt.minute / 60
    out["km_courier_to_stop"] = haversine_km(df["accept_gps_lat"], df["accept_gps_lng"], df["lat"], df["lng"])
    return out


def courier_workload(df: pd.DataFrame) -> pd.DataFrame:
    """Open tasks (accepted, not yet picked up) and tasks accepted so far today, at each accept time.

    Counts exclude the task itself. Computed per courier with binary search over sorted times, so it
    is O(n log n) instead of comparing every pair of tasks.
    """
    open_tasks = np.zeros(len(df), dtype=np.int32)
    today = np.zeros(len(df), dtype=np.int32)
    acc_all = df["accept_time"].to_numpy()
    pick_all = df["pickup_time"].to_numpy()
    day_all = df["accept_time"].dt.normalize().to_numpy()
    for _, idx in df.groupby("courier_id", sort=False).indices.items():
        acc = acc_all[idx]
        pick = pick_all[idx]
        acc_sorted = np.sort(acc)
        pick_sorted = np.sort(pick)
        n_accepted = np.searchsorted(acc_sorted, acc, side="right")
        n_picked = np.searchsorted(pick_sorted, acc, side="right")
        self_open = (pick > acc).astype(np.int32)  # the task itself is open unless picked up instantly
        open_tasks[idx] = n_accepted - n_picked - self_open
        n_before_day = np.searchsorted(acc_sorted, day_all[idx], side="left")
        today[idx] = n_accepted - n_before_day - 1
    return pd.DataFrame({"courier_open_tasks": open_tasks, "courier_tasks_today": today}, index=df.index)


def history_features(df: pd.DataFrame, key: str, prefix: str, with_count: bool = True) -> pd.DataFrame:
    """Late rate and mean duration for `key` using only outcomes from days before the accept day."""
    outcome_day = df["pickup_time"].dt.normalize()
    capped = df[TARGET_MINUTES].clip(upper=MINUTES_CAP)
    daily = (
        pd.DataFrame({key: df[key], "day": outcome_day, "late": df[TARGET_LATE], "minutes": capped})
        .groupby([key, "day"], sort=True)
        .agg(n=("late", "size"), n_late=("late", "sum"), sum_minutes=("minutes", "sum"))
        .reset_index()
    )
    daily[["cum_n", "cum_late", "cum_minutes"]] = daily.groupby(key)[["n", "n_late", "sum_minutes"]].cumsum()

    glob = daily.groupby("day")[["n", "n_late"]].sum().cumsum().reset_index()
    glob["global_rate"] = glob["n_late"] / glob["n"]

    left = pd.DataFrame({key: df[key], "day": df["accept_time"].dt.normalize(), "_row": np.arange(len(df))})
    left = left.sort_values("day")
    hist = pd.merge_asof(
        left, daily[[key, "day", "cum_n", "cum_late", "cum_minutes"]].sort_values("day"),
        on="day", by=key, allow_exact_matches=False,  # strictly earlier days only
    )
    hist = pd.merge_asof(hist, glob[["day", "global_rate"]], on="day", allow_exact_matches=False)
    hist = hist.sort_values("_row")

    n = hist["cum_n"].fillna(0).to_numpy()
    late = hist["cum_late"].fillna(0).to_numpy()
    prior = hist["global_rate"].fillna(0.0).to_numpy()
    out = pd.DataFrame(index=df.index)
    if with_count:
        out[f"{prefix}_hist_n"] = n
    out[f"{prefix}_hist_late_rate"] = (late + PRIOR_WEIGHT * prior) / (n + PRIOR_WEIGHT)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[f"{prefix}_hist_mean_minutes"] = np.where(n > 0, hist["cum_minutes"].to_numpy() / n, np.nan)
    return out


def build(df: pd.DataFrame) -> pd.DataFrame:
    """Cleaned tasks in, one feature row per task out (original columns kept for reporting)."""
    df = add_targets(df.reset_index(drop=True))
    parts = [
        df,
        time_features(df),
        courier_workload(df),
        history_features(df, "courier_id", "courier"),
        history_features(df, "aoi_id", "aoi"),
        history_features(df, "region_id", "region", with_count=False),
    ]
    out = pd.concat(parts, axis=1)
    for col in CATEGORICAL:
        out[col] = out[col].astype("category")
    return out


def split_by_date(df: pd.DataFrame, valid_start: str, test_start: str, year: int):
    """Time-ordered split on accept date: train < valid_start <= valid < test_start <= test."""
    v = pd.Timestamp(f"{year}-{valid_start}")
    t = pd.Timestamp(f"{year}-{test_start}")
    acc = df["accept_time"]
    return df[acc < v], df[(acc >= v) & (acc < t)], df[acc >= t]
