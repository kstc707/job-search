"""Score the locked prospective forecasts once actuals are published.

Usage (after the peers' Q3 2026 8-Ks are on EDGAR and FDXF has reported on 2026-10-29):
  .venv/bin/python -I scripts/fetch_peer_filings.py data/raw/sec_edgar/peers
  .venv/bin/python -I scripts/parse_peer_kpis.py data/raw/sec_edgar/peers data/processed
  .venv/bin/python -I scripts/ds_score_prospective.py --fdx-junsep-yoy-pct <FDXF reported Jun-Sep ADS YoY %>

The script first verifies the forecast file still matches the SHA-256 committed on 2026-10-23, then scores every
model's point forecast and 80% interval against the actuals.
"""
import argparse
import hashlib
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ltlds import config as C  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--fdx-junsep-yoy-pct", type=float, default=None,
                help="FDXF's reported Jun-Sep 2026 average daily shipments YoY change, in % (e.g. -4.2)")
args = ap.parse_args()

f = C.ROOT / "ds/prospective_forecasts.csv"
digest = (C.ROOT / "ds/prospective_forecasts.sha256").read_text().split()[0]
if hashlib.sha256(f.read_bytes()).hexdigest() != digest:
    sys.exit("forecast file does not match its committed hash - refusing to score")
fc = pd.read_csv(f)

w = pd.read_csv(C.PROC / "peer_ltl_quarterly_kpis_wide.csv")
actual = {}
for t in C.PEERS:
    s = w[w["ticker"] == t].set_index("period")["shipments_per_day"]
    if "2026Q3" in s.index and "2025Q3" in s.index:
        actual[(t, "2026Q3")] = 100 * np.log(s["2026Q3"] / s["2025Q3"])
if args.fdx_junsep_yoy_pct is not None:
    actual[("FDX", "Jun-Sep 2026 (FDXF transition period)")] = 100 * np.log1p(args.fdx_junsep_yoy_pct / 100)
if not actual:
    sys.exit("no actuals available yet")
fc["actual"] = [actual.get((t, p_), np.nan) for t, p_ in zip(fc["ticker"], fc["period"])]
sc = fc.dropna(subset=["actual"]).copy()
sc["abs_err"] = (sc["yoy_log_pct"] - sc["actual"]).abs()
sc["inside_80"] = (sc["actual"] >= sc["lo80"]) & (sc["actual"] <= sc["hi80"])
print(sc.pivot_table(index=["ticker", "period"], columns="model", values="abs_err").round(2).to_string())
summary = sc.groupby("model").agg(n=("abs_err", "size"), mae=("abs_err", "mean"), coverage_80=("inside_80", "mean"))
print(summary.sort_values("mae").round(3).to_string())
sc.to_csv(C.ROOT / "ds/prospective_scores.csv", index=False)
