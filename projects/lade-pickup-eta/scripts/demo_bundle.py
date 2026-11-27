"""Train a tiny model bundle on synthetic tasks (no download). Used by CI to build and smoke-test the
Docker image; the real bundle comes from `python -m lade_eta train`.

    python scripts/demo_bundle.py OUTPUT_PATH   (refuses to overwrite an existing file)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from lade_eta import features as F  # noqa: E402
from lade_eta.models import LightGbmEta, LightGbmLateRisk, ModelBundle, RegionMedianEta  # noqa: E402
from lade_eta.store import HistorySnapshot  # noqa: E402
from lade_eta.synthetic import make_tasks  # noqa: E402

OUT = Path(sys.argv[1])
if OUT.exists():
    sys.exit(f"{OUT} exists; not overwriting a trained model with the synthetic demo")

frame = F.build(make_tasks())
train, valid, _ = F.split_by_date(frame, "08-25", "09-01", 2022)
small = {"num_leaves": 7, "min_data_in_leaf": 10}
eta = LightGbmEta(params=dict(small)).fit(train, valid)
risk = LightGbmLateRisk(params=dict(small)).fit(train, valid)
risk.set_threshold_for_budget(risk.predict(valid), 0.1)
snap = HistorySnapshot.as_of(frame, frame["pickup_time"].max() + pd.Timedelta(days=1))
ModelBundle(eta=eta, risk=risk, baseline=RegionMedianEta().fit(train), snapshot=snap,
            metadata={"city": "synthetic", "alert_budget": 0.1}).save(OUT)
print(f"wrote {OUT} (synthetic demo)")
