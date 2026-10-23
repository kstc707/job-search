"""Option A: is FedEx Freight's volume decline the market or FedEx? A backtested nowcast.

Target: YoY log change in FedEx Freight average daily shipments (ADS) over a window of months.
Training windows are FedEx fiscal quarters (Mar-May, Jun-Aug, Sep-Nov, Dec-Feb), FY2018Q4-FY2026Q4.
Features are computed over the SAME months as the target, so the model can nowcast any window - in
particular FDXF's first standalone report: the 4-month transition period Jun-Sep 2026 (reported 2026-10-29).

Models (all re-estimated at every origin of a rolling backtest, never seeing the test quarter):
  naive_last   y_t = y_{t-1}
  mean4        mean of the last 4 quarters
  ar1          OLS on y_{t-1}
  macro3       OLS on manufacturing IP, ATA tonnage, Cass shipments (same-window YoY)
  macro3_ar    macro3 + y_{t-1}
  ridge_all    ridge (LOO-tuned) on all macro features + y_{t-1}
  peer*        same, plus the LTL peer index (only if data/processed/peer_ltl_*.csv exists)
COVID base-effect quarters (FY2020Q4-FY2022Q1) are excluded from training and scoring.
Prediction intervals: empirical quantiles of each model's own out-of-sample backtest errors.
Run from the project root: .venv/bin/python -I scripts/option_a_nowcast.py
"""
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data/raw", ROOT / "data/processed"
OUT = ROOT / "reports/option_a"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 220)
res = {}
COVID = ("2020-03-01", "2021-08-31")  # windows ending in this range have COVID base effects
TEST_FROM = "2021-09-01"              # score every quarter from FY2022Q2 onward (19 quarters)
NOWCAST = ("2026-06-01", "2026-09-30")  # FDXF transition period, reported 2026-10-29


def section(t):
    print(f"\n=== {t} ===")


# ------------------------------------------------------------------ monthly indicators
def fred(sid):
    return pd.read_csv(RAW / f"fred/{sid}.csv", parse_dates=[0], index_col=0, na_values=".")[sid].dropna()


MACRO = {"ipman": "IPMAN", "tonnage": "TRUCKD11", "cass": "FRGSHPUSM649NCIS", "tsi": "TSIFRGHT",
         "dgorder": "DGORDER", "retail": "RSXFS", "intermodal": "RAILFRTINTERMODALD11",
         "ppi_ltl": "PCU484122484122", "ppi_tl": "PCU484121484121", "truck_jobs": "CES4348400001"}
monthly = pd.DataFrame({k: fred(v) for k, v in MACRO.items()})
monthly["isratio"] = fred("ISRATIO")
monthly["diesel"] = fred("GASDESW").resample("MS").mean()
monthly = monthly["2015":]


def window_yoy(col, start, end, diff=False):
    """YoY change of the window average vs the same calendar months a year earlier, using only months
    that are available in BOTH years (handles the ragged edge of late-published series)."""
    cur = monthly.loc[start:end, col]
    prev = monthly.loc[pd.Timestamp(start) - pd.DateOffset(years=1):pd.Timestamp(end) - pd.DateOffset(years=1), col]
    prev.index = prev.index + pd.DateOffset(years=1)
    both = pd.concat([cur, prev], axis=1, keys=["c", "p"]).dropna()
    if both.empty:
        return np.nan, 0
    if diff:
        return both["c"].mean() - both["p"].mean(), len(both)
    return np.log(both["c"].mean() / both["p"].mean()), len(both)


# ------------------------------------------------------------------ peer LTL index (optional)
def load_peer_monthly():
    """Return a monthly DataFrame of peer shipments/day YoY (log) if the peer fork produced it."""
    f = PROC / "peer_ltl_monthly_kpis.csv"
    if not f.exists():
        return None
    return pd.read_csv(f)


def load_peer_quarterly():
    f = PROC / "peer_ltl_quarterly_kpis.csv"
    if not f.exists():
        return None
    return pd.read_csv(f)


peer_q = load_peer_quarterly()
peer_m = load_peer_monthly()
PEER_COL = None
PEER_TICKERS = ["ODFL", "SAIA", "XPO", "ARCB"]


def build_peer_yoy(peer_q, peer_m):
    """Monthly LTL-industry shipments/day YoY (log), shipments-weighted across public peers.

    Per ticker and month: the monthly operating update's YoY where one exists, else the YoY of the calendar
    quarter containing that month. Weights: each ticker's shipments/day a year earlier (so the index is a
    chain-linked YoY of the peers' combined daily shipments)."""
    q = peer_q[(peer_q["metric"] == "shipments_per_day") & peer_q["ticker"].isin(PEER_TICKERS)].copy()
    q["period_end"] = pd.to_datetime(q["period_end"])
    lv = q.pivot_table(index="period_end", columns="ticker", values="value").sort_index()
    lv = lv.resample("QE").last()
    qyoy = np.log(lv / lv.shift(4))
    w_prev = lv.shift(4)
    months = pd.date_range("2016-01-01", "2026-12-01", freq="MS")
    tick_yoy = pd.DataFrame(index=months, columns=lv.columns, dtype=float)
    tick_w = pd.DataFrame(index=months, columns=lv.columns, dtype=float)
    for mth in months:
        qe = mth + pd.offsets.QuarterEnd(0)
        if qe in qyoy.index:
            tick_yoy.loc[mth] = qyoy.loc[qe]
        # weight = last known year-ago level (fall back to latest level if this quarter isn't reported yet)
        ref = w_prev.loc[:qe].ffill().iloc[-1] if len(w_prev.loc[:qe]) else np.nan
        tick_w.loc[mth] = ref
    src = pd.DataFrame("quarterly", index=months, columns=lv.columns)
    if peer_m is not None and len(peer_m):
        mm = peer_m[(peer_m["metric"] == "shipments_per_day_yoy_pct") & (peer_m["unit"] == "yoy_pct")
                    & peer_m["ticker"].isin(PEER_TICKERS)].copy()
        mm["month"] = pd.to_datetime(mm["month"].astype(str).str[:7] + "-01")
        for _, r_ in mm.iterrows():
            if r_["month"] in tick_yoy.index and r_["ticker"] in tick_yoy.columns:
                tick_yoy.loc[r_["month"], r_["ticker"]] = np.log1p(r_["value"] / 100)
                src.loc[r_["month"], r_["ticker"]] = "monthly"
    num = (tick_yoy * tick_w).sum(axis=1, min_count=1)
    den = tick_w.where(tick_yoy.notna()).sum(axis=1, min_count=1)
    out = pd.DataFrame({"peer_yoy": num / den, "n_tickers": tick_yoy.notna().sum(axis=1)})
    return out, tick_yoy, src, lv


if peer_q is not None:
    peer_yoy, tick_yoy, peer_src, peer_lv = build_peer_yoy(peer_q, peer_m)
    full_cov = peer_yoy[peer_yoy["n_tickers"] == len(PEER_TICKERS)]
    print(f"peer index: months with all {len(PEER_TICKERS)} tickers: {full_cov.index.min():%Y-%m}..{full_cov.index.max():%Y-%m}; "
          f"latest months: " + ", ".join(f"{d:%Y-%m}={100 * v:+.1f}% (n={n})" for d, v, n in
                                       zip(peer_yoy.dropna().index[-5:], peer_yoy.dropna()["peer_yoy"][-5:], peer_yoy.dropna()["n_tickers"][-5:])))
    peer_yoy.to_csv(OUT / "peer_index_monthly_yoy.csv")
    peer_src.to_csv(OUT / "peer_index_monthly_source.csv")
    PEER_COL = "peer_yoy"


def peer_window(start, end):
    """Mean monthly peer YoY (log) over the window; NaN if no peer month is available."""
    if PEER_COL is None:
        return np.nan
    v = peer_yoy.loc[start:end, "peer_yoy"].dropna()
    return v.mean() if len(v) else np.nan


# ------------------------------------------------------------------ FedEx target + features per window
k = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"])
k["start"] = (k["period_end"] - pd.offsets.MonthBegin(3)).dt.normalize()
k = k.sort_values("period_end").reset_index(drop=True)
k["y"] = np.log(k["avg_daily_shipments_k"]).diff(4)
k["y_lag1"] = k["y"].shift(1)

FEATS = ["ipman", "tonnage", "cass", "tsi", "dgorder", "retail", "intermodal", "truck_jobs", "ppi_ltl", "ppi_tl"]


def features(start, end):
    f = {}
    for c in FEATS:
        f[c] = window_yoy(c, start, end)[0]
    f["isratio"] = window_yoy("isratio", start, end, diff=True)[0]
    f["diesel"] = window_yoy("diesel", start, end)[0]
    f["ltl_tl_spread"] = f["ppi_ltl"] - f["ppi_tl"]  # LTL pricing relative to truckload: mode-shift pressure
    if PEER_COL:
        f[PEER_COL] = peer_window(start, end)
    return f


F = pd.DataFrame([features(s, e) for s, e in zip(k["start"], k["period_end"] + pd.offsets.MonthEnd(0))])
data = pd.concat([k[["fiscal_period", "start", "period_end", "y", "y_lag1", "avg_daily_shipments_k"]], F], axis=1)
data["covid"] = data["period_end"].between(*COVID) | data["start"].between(*COVID)
data = data[data["y"].notna()].reset_index(drop=True)
print(f"usable quarters: {len(data)}; excluded COVID-affected: {int(data['covid'].sum())}")

ALL_X = [c for c in F.columns] + ["y_lag1"]
MODELS = {
    "naive_last": None, "mean4": None,
    "ar1": ["y_lag1"],
    "macro3": ["ipman", "tonnage", "cass"],
    "macro3_ar": ["ipman", "tonnage", "cass", "y_lag1"],
    "ridge_all": "ridge",
}
if PEER_COL:
    MODELS["peer"] = [PEER_COL]
    MODELS["peer_ar"] = [PEER_COL, "y_lag1"]
    MODELS["peer_macro_ar"] = [PEER_COL, "ipman", "cass", "y_lag1"]


def fit_predict(name, train, xrow):
    spec = MODELS[name]
    if name == "naive_last":
        return xrow["y_lag1"]
    if name == "mean4":
        return train["y"].tail(4).mean()
    if spec == "ridge":
        cols = [c for c in ALL_X if train[c].notna().all() and pd.notna(xrow[c])]
        mdl = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 30)))
    else:
        cols = spec
        mdl = LinearRegression()
    train = train.dropna(subset=cols + ["y"])  # each model uses every row that has its own inputs
    min_rows = 6 if spec == "ridge" else len(cols) + 4  # ridge is regularized; OLS needs spare degrees of freedom
    if len(train) < min_rows or any(pd.isna(xrow[c]) for c in cols):
        return np.nan
    mdl.fit(train[cols], train["y"])
    return float(mdl.predict(pd.DataFrame([xrow[cols]]))[0])


# ------------------------------------------------------------------ rolling-origin backtest
section("1. Rolling-origin backtest (one quarter ahead of each origin, re-fit every time)")
clean = data[~data["covid"]].reset_index(drop=True)
preds = []
for i, row in clean.iterrows():
    if row["start"] < pd.Timestamp(TEST_FROM):
        continue
    train = clean.iloc[:i]
    train = train[train["period_end"] < row["start"]]  # strictly before the test window
    for name in MODELS:
        try:
            p = fit_predict(name, train.dropna(subset=["y_lag1"]), row)
        except (ValueError, KeyError):
            p = np.nan
        preds.append(dict(fiscal_period=row["fiscal_period"], period_end=row["period_end"], model=name,
                          y=row["y"], yhat=p, n_train=len(train), test_start=row["start"],
                          train_last_end=train["period_end"].max()))
bt = pd.DataFrame(preds)
# forecast combination with members fixed by design (one persistence, one market, one macro model), not chosen
# by backtest rank - so its own backtest is not flattered by selection
COMBO = ["ar1", "peer_ar", "macro3_ar"] if PEER_COL else ["ar1", "macro3_ar"]
cb = bt[bt["model"].isin(COMBO)].groupby("fiscal_period").agg(
    period_end=("period_end", "first"), y=("y", "first"), yhat=("yhat", "mean"), n_train=("n_train", "max"),
    test_start=("test_start", "first"), train_last_end=("train_last_end", "max"), k=("yhat", "count"))
cb = cb[cb["k"] == len(COMBO)].drop(columns="k").reset_index().assign(model="combo")
bt = pd.concat([bt, cb], ignore_index=True).sort_values(["period_end", "model"])
bt["err"] = bt["yhat"] - bt["y"]
score = bt.dropna(subset=["yhat"]).groupby("model").agg(
    n=("err", "size"), mae_pp=("err", lambda e: 100 * e.abs().mean()), rmse_pp=("err", lambda e: 100 * np.sqrt((e ** 2).mean())),
    bias_pp=("err", lambda e: 100 * e.mean()))
hit = bt.dropna(subset=["yhat"]).assign(hit=lambda d: np.sign(d["yhat"]) == np.sign(d["y"])).groupby("model")["hit"].mean()
score["direction_hit"] = hit
score = score.sort_values("mae_pp")
print(score.round(2).to_string())
bt.to_csv(OUT / "backtest_predictions.csv", index=False)
score.to_csv(OUT / "backtest_scores.csv")
res["backtest"] = score.round(2).reset_index().to_dict(orient="records")
best = score.index[0]
print(f"best by MAE: {best}")

# common-sample comparison (models with peers have fewer test points)
common = bt.dropna(subset=["yhat"]).pivot_table(index="fiscal_period", columns="model", values="err").dropna()
if len(common) and len(common) < len(bt["fiscal_period"].unique()):
    print(f"common-sample MAE (n={len(common)}):"); print((100 * common.abs().mean()).sort_values().round(2).to_string())
    res["backtest_common_sample"] = {"n": len(common), "mae_pp": (100 * common.abs().mean()).round(2).to_dict()}

fig, ax = plt.subplots(figsize=(10, 4.5))
act = clean.set_index("period_end")["y"] * 100
ax.plot(act.index, act, "k-o", ms=3, label="Actual FedEx Freight ADS YoY")
for name, style in [("naive_last", ":"), ("macro3_ar", "--"), (best, "-")]:
    s = bt[bt["model"] == name].set_index("period_end")["yhat"] * 100
    ax.plot(s.index, s, style, label=f"{name} (out-of-sample)")
ax.axhline(0, color="0.6", lw=0.8); ax.legend(fontsize=8)
ax.set_title("Rolling-origin backtest: one-quarter-ahead nowcasts vs actual (%, log)")
fig.tight_layout(); fig.savefig(FIG / "a1_backtest.png", dpi=130); plt.close(fig)

# ------------------------------------------------------------------ market vs FedEx-specific gap
section("2. Market-implied vs actual: the FedEx-specific gap")
# fit a pure-market model (no FedEx lag) on pre-downturn clean quarters, then look at residuals afterwards
mkt_cols = [PEER_COL] if PEER_COL else ["ipman", "tonnage", "cass"]
fitset = clean.dropna(subset=mkt_cols)
pre = fitset[fitset["period_end"] < pd.Timestamp("2022-06-01")]
if len(pre) >= 6:
    mk = LinearRegression().fit(pre[mkt_cols], pre["y"])
    fitset = fitset.assign(market_implied=mk.predict(fitset[mkt_cols]))
    fitset["gap"] = fitset["y"] - fitset["market_implied"]
    print(f"market model on {len(pre)} pre-2022-06 quarters, cols={mkt_cols}, coefs={np.round(mk.coef_, 2)}")
    print((100 * fitset.set_index("fiscal_period")[["y", "market_implied", "gap"]]).loc["FY2022Q4":].round(1).to_string())
    post = fitset[fitset["period_end"] >= pd.Timestamp("2022-06-01")]
    print(f"mean gap since FY2023: {100 * post['gap'].mean():+.1f} pp/yr (n={len(post)}); "
          f"cumulative shortfall vs market since FY2022Q4 ~ {100 * post['gap'].sum() / 4:+.1f}% of volume (annualized YoY gaps / 4)")
    res["gap"] = {"cols": mkt_cols, "mean_gap_pp_since_fy23": round(100 * post["gap"].mean(), 1),
                  "by_quarter": (100 * post.set_index("fiscal_period")["gap"]).round(1).to_dict()}
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(fitset["period_end"], 100 * fitset["gap"], width=60, color=np.where(fitset["gap"] < 0, "C3", "C2"),
           label="FedEx-specific gap (actual - market-implied)")
    ax.plot(fitset["period_end"], 100 * fitset["y"], "k-o", ms=3, label="FedEx ADS YoY")
    ax.plot(fitset["period_end"], 100 * fitset["market_implied"], "C0--", label="Market-implied YoY")
    ax.axvline(pd.Timestamp("2022-06-01"), color="0.5", ls=":"); ax.axhline(0, color="0.6", lw=0.8)
    ax.legend(fontsize=8); ax.set_title(f"Market vs FedEx-specific volume change (market model: {', '.join(mkt_cols)})")
    fig.tight_layout(); fig.savefig(FIG / "a2_market_vs_gap.png", dpi=130); plt.close(fig)

if PEER_COL:
    rel = clean.dropna(subset=[PEER_COL]).set_index("fiscal_period")[["period_end", "y", PEER_COL]].copy()
    rel["fedex_minus_peers_pp"] = 100 * (rel["y"] - rel[PEER_COL])
    print("\nDirect relative performance (FedEx ADS YoY minus peer index YoY, pp):")
    print(rel[["fedex_minus_peers_pp"]].T.round(1).to_string())
    since = rel[rel["period_end"] >= pd.Timestamp("2022-06-01")]["fedex_minus_peers_pp"]
    print(f"mean since FY2023: {since.mean():+.1f} pp; last 4 quarters: {since.tail(4).round(1).tolist()}")
    rel.to_csv(OUT / "fedex_vs_peers_quarterly.csv")
    res["relative_vs_peers"] = {"mean_since_fy23_pp": round(since.mean(), 1),
                                "by_quarter_pp": rel["fedex_minus_peers_pp"].round(1).to_dict()}

# ------------------------------------------------------------------ nowcast Jun-Sep 2026
section("3. Nowcast: FDXF transition period Jun-Sep 2026 (reported 2026-10-29)")
s, e = NOWCAST
xrow = pd.Series(features(s, e))
avail = {c: window_yoy(c, s, e)[1] for c in FEATS}
if PEER_COL:
    pw = peer_yoy.loc[s:e]
    avail["peer_months"] = {f"{d:%Y-%m}": int(n) for d, n in pw["n_tickers"].items() if n > 0}
print("months of Jun-Sep 2026 available per indicator:", avail)
xrow["y_lag1"] = data["y"].iloc[-1]  # FY2026Q4 (Mar-May 2026)
print("feature values (log YoY):"); print((100 * xrow).round(2).to_string())
train_all = clean.dropna(subset=["y_lag1"])
errs = bt.dropna(subset=["yhat"]).groupby("model")["err"]
rows = []
for name in MODELS:
    try:
        p = fit_predict(name, train_all, xrow)
    except (ValueError, KeyError):
        continue
    if pd.isna(p):
        continue
    e_ = errs.get_group(name) if name in errs.groups else pd.Series(dtype=float)
    lo, hi = (p - np.quantile(e_, 0.9), p - np.quantile(e_, 0.1)) if len(e_) >= 8 else (np.nan, np.nan)
    rows.append(dict(model=name, yhat_pct=100 * p, lo80_pct=100 * lo, hi80_pct=100 * hi,
                     backtest_mae_pp=score.loc[name, "mae_pp"] if name in score.index else np.nan))
members = [r_ for r_ in rows if r_["model"] in COMBO]
if len(members) == len(COMBO):
    p = np.mean([m_["yhat_pct"] for m_ in members]) / 100
    e_ = errs.get_group("combo")
    rows.append(dict(model="combo", yhat_pct=100 * p, lo80_pct=100 * (p - np.quantile(e_, 0.9)),
                     hi80_pct=100 * (p - np.quantile(e_, 0.1)), backtest_mae_pp=score.loc["combo", "mae_pp"]))
nc = pd.DataFrame(rows).sort_values("backtest_mae_pp")
# base: Jun-Sep 2025 ADS from FY2026Q1 (Jun-Aug 2025) and CY2025Q3 (Jul-Sep 2025): bounded by the two
rc = pd.read_csv(PROC / "fdxf_calendar_quarterly_kpis_recast.csv").set_index("period")
base_lo, base_hi = sorted([k.set_index("fiscal_period").loc["FY2026Q1", "avg_daily_shipments_k"], rc.loc["2025Q3", "avg_daily_shipments_k"]])
base = (base_lo + base_hi) / 2
nc["ads_k"] = base * np.exp(nc["yhat_pct"] / 100)
print(f"Jun-Sep 2025 ADS base ~{base:.1f}k (between {base_lo:.2f}k and {base_hi:.2f}k)")
print(nc.round(2).to_string(index=False))
nc.to_csv(OUT / "nowcast_jun_sep_2026.csv", index=False)
res["combo_members"] = COMBO
res["nowcast"] = {"window": NOWCAST, "base_ads_k": round(base, 2), "models": nc.round(2).to_dict(orient="records"),
                  "external": {"BofA_Q3_shipments_yoy_pct": -3.0,
                               "mgmt_sept8": "mid-single-digit decline 1H26, exit 2026 flat to slightly positive"}}

(OUT / "results.json").write_text(json.dumps(res, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print("\nwritten:", OUT)
