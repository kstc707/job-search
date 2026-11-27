"""Load test for /predict with real test-month tasks (workload looked up in PostgreSQL per request).

    locust -f locustfile.py --headless -u 20 -r 5 -t 60s --host http://localhost:8000
"""
import random

from locust import HttpUser, between, task

from lade_eta.ingest import read_postgres
from lade_eta.settings import get_settings

_rows = read_postgres(get_settings().database_url, "WHERE accept_time >= %s ORDER BY order_id LIMIT 2000",
                      ("2022-10-01",))
PAYLOADS = [
    {
        "order_id": int(r.order_id), "courier_id": int(r.courier_id), "region_id": int(r.region_id),
        "aoi_id": int(r.aoi_id), "aoi_type": int(r.aoi_type), "lng": float(r.lng), "lat": float(r.lat),
        "accept_time": r.accept_time.isoformat(), "time_window_start": r.time_window_start.isoformat(),
        "time_window_end": r.time_window_end.isoformat(),
        "accept_gps_lng": None if r.accept_gps_lng != r.accept_gps_lng else float(r.accept_gps_lng),
        "accept_gps_lat": None if r.accept_gps_lat != r.accept_gps_lat else float(r.accept_gps_lat),
    }
    for r in _rows.itertuples()
]


class Dispatcher(HttpUser):
    wait_time = between(0.05, 0.2)

    @task
    def predict(self):
        self.client.post("/predict", json=random.choice(PAYLOADS))
