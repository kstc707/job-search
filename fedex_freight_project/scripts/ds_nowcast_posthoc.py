"""Post-hoc nowcast models (ds/DEVIATIONS.md #1), evaluated with the identical rolling-origin protocol."""
import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ltlds import config as C  # noqa: E402
from ltlds.evaluate import add_conformal, diebold_mariano, metrics, rolling_origin  # noqa: E402
from ltlds.models import Hybrid, SelectRidge  # noqa: E402

p = pd.read_csv(C.OUT / "panel.csv", parse_dates=["end", "start", "tau", "known"])
prev = pd.read_csv(C.OUT / "backtest_predictions.csv", parse_dates=["tau", "train_last_known"])
naive = prev[(prev["model"] == "naive") & (prev["tau"] >= C.TEST_FROM)]
ens = prev[(prev["model"] == "ensemble") & (prev["tau"] >= C.TEST_FROM)]
own = prev[(prev["model"] == "own_monthly") & (prev["tau"] >= C.TEST_FROM)]
nm = metrics(naive)["mae"]
out = {}
new = []
for name, mk in [("hybrid", Hybrid), ("ridge_select", SelectRidge)]:
    bt = add_conformal(rolling_origin(p, mk))
    new.append(bt.assign(model=name))
    t = bt[bt["tau"] >= C.TEST_FROM]
    m = metrics(t, nm)
    m["dm_vs_naive"] = diebold_mariano(t, naive)
    m["dm_vs_ensemble"] = diebold_mariano(t, ens)
    m["dm_vs_own_monthly"] = diebold_mariano(t, own)
    m["fdx_mae"] = metrics(t[t["ticker"] == "FDX"])["mae"]
    out[name] = m
    print(name, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()})
pd.concat([prev, *new]).to_csv(C.OUT / "backtest_predictions.csv", index=False)
(C.OUT / "posthoc_results.json").write_text(json.dumps(out, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
