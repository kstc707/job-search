"""Small synthetic LaDe-shaped pickup tasks for tests and the CI demo model (no download needed)."""
import numpy as np
import pandas as pd


def make_tasks(n_days: int = 40, couriers: int = 12, per_day: int = 6, seed: int = 0) -> pd.DataFrame:
    """Couriers with different reliability: courier c is late with probability rising in c."""
    rng = np.random.default_rng(seed)
    rows, oid = [], 1
    start = pd.Timestamp("2022-08-01")
    for d in range(n_days):
        day = start + pd.Timedelta(days=d)
        for c in range(couriers):
            for k in range(per_day):
                accept = day + pd.Timedelta(hours=8 + k, minutes=int(rng.integers(0, 50)))
                ws = accept + pd.Timedelta(minutes=int(rng.integers(30, 120)))
                we = ws + pd.Timedelta(hours=2)
                late = rng.random() < 0.02 + 0.04 * c
                pickup = we + pd.Timedelta(minutes=int(rng.integers(5, 90))) if late else \
                    ws + pd.Timedelta(minutes=int(rng.integers(0, 110)))
                rows.append({
                    "order_id": oid, "city": "Test", "region_id": c % 3, "aoi_id": c % 5, "aoi_type": c % 2,
                    "courier_id": c, "lng": 121.4 + 0.01 * c, "lat": 31.2, "accept_time": accept,
                    "time_window_start": ws, "time_window_end": we, "pickup_time": pickup,
                    "accept_gps_lng": 121.41 if k % 3 else np.nan, "accept_gps_lat": 31.21 if k % 3 else np.nan,
                    "ds": int(pickup.strftime("%m%d")),
                })
                oid += 1
    return pd.DataFrame(rows)
