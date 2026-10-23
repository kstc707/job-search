"""Build the carrier x quarter panel with point-in-time features (ds/PREREGISTRATION.md, Task 1).

Every feature for a row issued at tau (the quarter's last day) uses only information published by tau:
own quarterly results through q-1, monthly operating updates with an EDGAR filing date <= tau, and
macro months that have finished at least MACRO_LAG_MONTHS before tau.
"""
import numpy as np
import pandas as pd

from . import config as C


def _fred(sid):
    s = pd.read_csv(C.RAW / f"fred/{sid}.csv", parse_dates=[0], index_col=0, na_values=".").iloc[:, 0].dropna()
    return s


def load_quarters() -> pd.DataFrame:
    """One row per carrier-quarter with levels: spd (shipments/day), wps, cwt (rev/cwt incl. fuel), days."""
    k = pd.read_csv(C.PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"])
    fdx = pd.DataFrame({"ticker": "FDX", "period": k["fiscal_period"], "end": k["period_end"],
                        "spd": k["avg_daily_shipments_k"] * 1000, "wps": k["weight_per_shipment_lbs"],
                        "cwt": k["revenue_per_cwt_usd"], "days": k["operating_days"]})
    w = pd.read_csv(C.PROC / "peer_ltl_quarterly_kpis_wide.csv")
    w = w[w["ticker"].isin(C.PEERS)]
    peers = pd.DataFrame({"ticker": w["ticker"], "period": w["period"],
                          "end": pd.PeriodIndex(w["period"], freq="Q").end_time.normalize(),
                          "spd": w["shipments_per_day"], "wps": w["weight_per_shipment_lbs"],
                          "cwt": w["revenue_per_cwt_usd"], "cwt_xf": w["revenue_per_cwt_ex_fuel_usd"],
                          "days": w["workdays"]})
    df = pd.concat([fdx, peers], ignore_index=True)
    df["end"] = pd.to_datetime(df["end"]).dt.normalize()
    df["start"] = (df["end"] - pd.offsets.MonthBegin(3)).dt.normalize()
    return df.sort_values(["ticker", "end"]).reset_index(drop=True)


def _yoy(g: pd.DataFrame, col: str) -> pd.Series:
    """100*ln(x_q / x_{q-4}) where q-4 must end 12 months (+-10 days) earlier, else NaN."""
    prev = g.set_index("end")[col]
    target_end = g["end"] - pd.DateOffset(years=1)
    vals = []
    for te, cur in zip(target_end, g[col]):
        cand = prev[(prev.index >= te - pd.Timedelta(days=10)) & (prev.index <= te + pd.Timedelta(days=10))]
        vals.append(100 * np.log(cur / cand.iloc[0]) if len(cand) and cand.iloc[0] > 0 and cur > 0 else np.nan)
    return pd.Series(vals, index=g.index)


def load_monthly() -> pd.DataFrame:
    m = pd.read_csv(C.PROC / "peer_ltl_monthly_kpis.csv")
    m = m[(m["metric"] == "shipments_per_day_yoy_pct") & m["ticker"].isin(C.PEERS)].copy()
    m["month"] = pd.to_datetime(m["month"].astype(str).str[:7] + "-01")
    m["filed"] = pd.to_datetime(m["filed"])
    m["y_m"] = 100 * np.log1p(m["value"] / 100)
    return m[["ticker", "month", "filed", "y_m"]]


def macro_monthly() -> pd.DataFrame:
    d = pd.DataFrame({k: _fred(v) for k, v in C.MACRO.items()})
    d["diesel"] = _fred("GASDESW").resample("MS").mean()
    return d


def _macro_window_yoy(mac: pd.DataFrame, start, tau) -> dict:
    out = {}
    cutoff = (pd.Timestamp(tau) + pd.Timedelta(days=1)) - pd.DateOffset(months=C.MACRO_LAG_MONTHS)
    for col in mac.columns:
        last_ok = pd.Timestamp(tau) if col == "diesel" else cutoff - pd.Timedelta(days=1)
        months = pd.date_range(start, tau, freq="MS")
        months = [mo for mo in months if (mo + pd.offsets.MonthEnd(0)) <= last_ok]
        cur = mac.loc[mac.index.isin(months), col].dropna()
        prev_idx = [mo - pd.DateOffset(years=1) for mo in cur.index]
        prev = mac.loc[mac.index.isin(prev_idx), col].dropna()
        if len(cur) == 0 or len(prev) != len(cur):
            out[col] = np.nan
        elif col in C.DIFF_SERIES:
            out[col] = cur.mean() - prev.mean()
        else:
            out[col] = 100 * np.log(cur.mean() / prev.mean())
    return out


def add_next_quarters(q: pd.DataFrame) -> pd.DataFrame:
    """Append one placeholder row (levels unknown) per carrier for its next, not-yet-reported quarter, so the
    prospective forecast gets features from exactly the same code path as the backtest."""
    rows = []
    for t, g in q.groupby("ticker"):
        last = g.sort_values("end").iloc[-1]
        end = (last["end"] + pd.offsets.MonthEnd(3)).normalize()
        per = (f"FY{int(last['period'][2:6]) + (1 if last['period'].endswith('Q4') else 0)}Q"
               f"{1 if last['period'].endswith('Q4') else int(last['period'][-1]) + 1}") if t == "FDX" else str(pd.Period(end, "Q"))
        rows.append(dict(ticker=t, period=per, end=end, start=(end - pd.offsets.MonthBegin(3)).normalize()))
    return pd.concat([q, pd.DataFrame(rows)], ignore_index=True).sort_values(["ticker", "end"]).reset_index(drop=True)


def window_features(p: pd.DataFrame, mon: pd.DataFrame, mac: pd.DataFrame, ticker, start, end, tau) -> dict:
    """Same-window features for one carrier and window, using only what was published by tau."""
    f = {}
    inq = mon[(mon["month"] >= start) & (mon["month"] <= end) & (mon["filed"] <= tau)]
    own = inq[inq["ticker"] == ticker]
    f["own_m"] = own["y_m"].mean() if len(own) else np.nan
    f["own_m_n"] = len(own)
    oth = inq[inq["ticker"] != ticker]
    if len(oth):  # weight other carriers by their latest daily shipments published by tau
        wts = []
        for tk in oth["ticker"]:
            lv = p[(p["ticker"] == tk) & (p["known"] <= tau)]["spd"].dropna()
            wts.append(lv.iloc[-1] if len(lv) else np.nan)
        wts = pd.Series(wts, index=oth.index, dtype=float)
        wts = wts.fillna(wts.mean() if wts.notna().any() else 1.0)
        f["mkt_m"] = float((oth["y_m"] * wts).sum() / wts.sum())
    else:
        f["mkt_m"] = np.nan
    f["mkt_m_n"] = oth["ticker"].nunique()
    known = p[(p["ticker"] != ticker) & (p["known"] <= tau) & p["y"].notna()]
    last = known.sort_values("end").groupby("ticker").tail(1)
    last = last[last["end"] >= tau - pd.Timedelta(days=200)]
    f["mkt_l1"] = float(np.average(last["y"], weights=last["spd"])) if len(last) else np.nan
    f.update(_macro_window_yoy(mac, start, tau))
    return f


def build_panel(future: bool = False) -> pd.DataFrame:
    q = load_quarters()
    if future:
        q = add_next_quarters(q)
    parts = []
    for t, g in q.groupby("ticker"):
        g = g.copy()
        g["y"] = _yoy(g, "spd")
        g["spd_l4"] = g["spd"].shift(4)
        g["cwt_yoy"] = _yoy(g, "cwt")
        g["wps_yoy"] = _yoy(g, "wps")
        g["y_l1"] = g["y"].shift(1)
        g["y_l2"] = g["y"].shift(2)
        g["y_l4"] = g["y"].shift(4)
        g["dy_l1"] = g["y_l1"] - g["y_l2"]
        g["cwt_yoy_l1"] = g["cwt_yoy"].shift(1)
        g["wps_yoy_l1"] = g["wps_yoy"].shift(1)
        parts.append(g)
    p = pd.concat(parts).sort_values(["end", "ticker"]).reset_index(drop=True)
    p["tau"] = p["end"]
    p["known"] = p["end"] + pd.Timedelta(days=C.REPORT_LAG_DAYS)
    p["covid"] = p["end"].between(*C.COVID) | p["start"].between(*C.COVID)
    p["carrier_code"] = p["ticker"].map({c: i for i, c in enumerate(C.CARRIERS)})

    mon = load_monthly()
    mac = macro_monthly()
    feats = [window_features(p, mon, mac, r["ticker"], r["start"], r["end"], r["tau"]) for _, r in p.iterrows()]
    p = pd.concat([p, pd.DataFrame(feats, index=p.index)], axis=1)
    return p


def validate_panel(p: pd.DataFrame) -> list:
    """Schema and sanity checks; returns a list of failure messages (empty = pass)."""
    errs = []
    if set(p["ticker"]) != set(C.CARRIERS):
        errs.append(f"carriers {sorted(set(p['ticker']))}")
    if p.duplicated(["ticker", "end"]).any():
        errs.append("duplicate carrier-quarter rows")
    if (p["spd"] <= 0).any():
        errs.append("non-positive shipments/day")
    ok = p[~p["covid"] & p["y"].notna()]
    if (ok["y"].abs() > 40).any():
        errs.append("implausible |YoY| > 40 outside COVID")
    for c in ["own_m", "mkt_m"]:
        if (p[c].abs() > 40).any():
            errs.append(f"implausible {c}")
    if p.loc[p["ticker"] == "FDX", "own_m_n"].gt(0).any():
        errs.append("FDX has no monthly updates but own_m_n > 0")
    return errs
