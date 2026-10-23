"""Pooled vs group-conditional (Mondrian) conformal intervals, from the saved out-of-sample residuals
(ds/DEVIATIONS.md #4). Groups: whether the carrier's own monthly update was available at the issue date."""
import json
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ltlds import config as C  # noqa: E402
from ltlds.evaluate import add_conformal  # noqa: E402

bt = pd.read_csv(C.OUT / "backtest_predictions.csv", parse_dates=["tau"])
p = pd.read_csv(C.OUT / "panel.csv", parse_dates=["tau"])
bt = bt.merge(p[["ticker", "tau", "own_m_n"]], on=["ticker", "tau"], how="left")
bt["has_own"] = bt["own_m_n"].fillna(0) > 0
rows, out = [], {}
for m, g in bt.groupby("model"):
    g = g.drop(columns=[c for c in ("lo", "hi", "n_calib", "resid") if c in g])
    for kind, kw in [("pooled", {}), ("mondrian", {"group_col": "has_own"})]:
        x = add_conformal(g, **kw)
        x = x[(x["tau"] >= C.TEST_FROM)].dropna(subset=["lo"])
        inside = (x["y"] >= x["lo"]) & (x["y"] <= x["hi"])
        for grp, xx in [("all", x), ("own monthly available", x[x["has_own"]]), ("not available", x[~x["has_own"]]),
                        ("FDX", x[x["ticker"] == "FDX"])]:
            ii = (xx["y"] >= xx["lo"]) & (xx["y"] <= xx["hi"])
            rows.append(dict(model=m, method=kind, group=grp, n=len(xx), coverage=round(ii.mean(), 3),
                             width=round((xx["hi"] - xx["lo"]).mean(), 2)))
t = pd.DataFrame(rows)
show = t[t["model"].isin(["own_monthly", "hybrid", "ensemble", "naive"])]
print(show.pivot_table(index=["model", "group"], columns="method", values=["coverage", "width"]).round(2).to_string())
t.to_csv(C.OUT / "conformal_groups.csv", index=False)
