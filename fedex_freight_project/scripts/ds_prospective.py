"""Prospective (truly out-of-sample) forecasts, locked before the actuals are published (ds/PREREGISTRATION.md).

Rows: each carrier's next unreported quarter (ODFL, SAIA, XPO, ARCB: calendar 2026Q3; FDX: Jun-Aug 2026) plus
FDXF's Jun-Sep 2026 transition period reported on 2026-10-29. Every model is fit on all rows published before
the issue date; 80% intervals are split-conformal from that model's own backtest residuals.
Writes ds/prospective_forecasts.csv and its SHA-256 to ds/prospective_forecasts.sha256.
"""
import hashlib
import pathlib
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ltlds import config as C  # noqa: E402
from ltlds.evaluate import usable  # noqa: E402
from ltlds.models import Hybrid, SelectRidge, model_zoo  # noqa: E402
from ltlds.panel import _macro_window_yoy, build_panel, load_monthly, macro_monthly, window_features  # noqa: E402

ISSUED = "2026-10-23"
p = build_panel(future=True)
fut = p[p["spd"].isna()].copy()
# FDXF's Jun-Sep 2026 transition period: same information set as FDX's next quarter, 4-month window, issued now
fdx = fut[fut["ticker"] == "FDX"].iloc[0].copy()
fdx["period"], fdx["start"], fdx["end"] = "Jun-Sep 2026 (FDXF transition period)", pd.Timestamp("2026-06-01"), pd.Timestamp("2026-09-30")
fdx["tau"] = fdx["end"]
fdx.update(pd.Series(window_features(p, load_monthly(), macro_monthly(), "FDX", fdx["start"], fdx["end"], fdx["tau"])))
fut = pd.concat([fut, fdx.to_frame().T], ignore_index=True)
for c in fut.columns:
    if c not in ("ticker", "period", "start", "end", "tau", "known", "covid"):
        try:
            fut[c] = pd.to_numeric(fut[c])
        except (ValueError, TypeError):
            pass

train = usable(p)
bt = pd.read_csv(C.OUT / "backtest_predictions.csv", parse_dates=["tau"])
bt = bt.merge(p[["ticker", "tau", "own_m_n"]], on=["ticker", "tau"], how="left")
bt["has_own"] = bt["own_m_n"].fillna(0) > 0
models = {k: v for k, v in model_zoo().items()}
models.update({"hybrid": Hybrid, "ridge_select": SelectRidge})
pre_registered_best = "own_monthly"
rows = []
for name, mk in models.items():
    m = mk().fit(train)
    pred = m.predict(fut)
    bm = bt[bt["model"] == name]
    for (_, r), yh in zip(fut.iterrows(), pred):
        # Mondrian conformal: calibrate on residuals from rows with the same own-monthly availability
        resid = (bm.loc[bm["has_own"] == (r["own_m_n"] > 0), "y"] - bm.loc[bm["has_own"] == (r["own_m_n"] > 0), "yhat"]).dropna()
        qlo, qhi = (np.quantile(resid, 0.10), np.quantile(resid, 0.90)) if len(resid) >= C.CONFORMAL_MIN_RESIDUALS else (np.nan, np.nan)
        base = r["spd_l4"]
        if r["period"].startswith("Jun-Sep"):
            base = np.nan  # Jun-Sep 2025 base is not a reported quarter; see reports/option_a for the bracketed base
        rows.append(dict(issued=ISSUED, model=name, post_hoc=name in ("hybrid", "ridge_select"),
                         pre_registered_best=name == pre_registered_best, ticker=r["ticker"], period=r["period"],
                         window_start=pd.Timestamp(r["start"]).date(), window_end=pd.Timestamp(r["end"]).date(),
                         yoy_log_pct=round(float(yh), 2), lo80=round(float(yh + qlo), 2), hi80=round(float(yh + qhi), 2),
                         spd_year_ago=base, spd_forecast=round(float(base * np.exp(yh / 100))) if pd.notna(base) else np.nan,
                         own_monthly_months_used=int(r["own_m_n"]), peer_monthly_carriers_used=int(r["mkt_m_n"])))
out = pd.DataFrame(rows)
path = C.ROOT / "ds/prospective_forecasts.csv"
out.to_csv(path, index=False)
digest = hashlib.sha256(path.read_bytes()).hexdigest()
(C.ROOT / "ds/prospective_forecasts.sha256").write_text(f"{digest}  prospective_forecasts.csv\n")
print(out.pivot_table(index=["ticker", "period"], columns="model", values="yoy_log_pct").round(1).to_string())
print("\npre-registered best (own_monthly) and ensemble with intervals:")
print(out[out["model"].isin(["own_monthly", "ensemble", "hybrid"])][["ticker", "period", "model", "yoy_log_pct", "lo80", "hi80",
                                                                     "spd_forecast"]].to_string(index=False))
print("sha256", digest)
