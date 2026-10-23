"""Rolling-origin evaluation, Diebold-Mariano test, split-conformal intervals (ds/PREREGISTRATION.md)."""
import numpy as np
import pandas as pd
from scipy import stats

from . import config as C


def usable(p: pd.DataFrame) -> pd.DataFrame:
    return p[p["y"].notna() & ~p["covid"]].copy()


def _one_origin(d, tau, make_model, min_train):
    train = d[d["known"] < tau]
    test = d[d["tau"] == tau]
    if len(train) < min_train or test.empty:
        return []
    m = make_model().fit(train)
    pred = m.predict(test)
    return [dict(ticker=r["ticker"], period=r["period"], tau=tau, y=r["y"], yhat=float(yh), n_train=len(train),
                 train_last_known=train["known"].max()) for (_, r), yh in zip(test.iterrows(), pred)]


def rolling_origin(p: pd.DataFrame, make_model, start=C.BURN_IN_FROM, min_train=25, n_jobs=4):
    """For every issue date tau >= start: fit on rows published before tau, predict rows issued at tau.
    Origins are independent, so they run in parallel; results are identical to a sequential loop."""
    from joblib import Parallel, delayed
    d = usable(p)
    taus = np.sort(d.loc[d["tau"] >= start, "tau"].unique())
    out = Parallel(n_jobs=n_jobs)(delayed(_one_origin)(d, tau, make_model, min_train) for tau in taus)
    return pd.DataFrame([row for rows in out for row in rows])


def add_conformal(bt: pd.DataFrame, level=C.INTERVAL, min_res=C.CONFORMAL_MIN_RESIDUALS, group_col=None) -> pd.DataFrame:
    """Rolling split-conformal: interval from quantiles of the model's own earlier out-of-sample residuals
    whose targets were published before tau. With group_col, calibration uses only residuals from the same group
    (Mondrian conformal), which gives coverage within each group, not just on average."""
    bt = bt.sort_values("tau").copy()
    bt["resid"] = bt["y"] - bt["yhat"]
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    lo, hi, n = [], [], []
    for _, r in bt.iterrows():
        mask = bt["tau"] + pd.Timedelta(days=C.REPORT_LAG_DAYS) < r["tau"]
        if group_col is not None:
            mask &= bt[group_col] == r[group_col]
        past = bt.loc[mask, "resid"]
        n.append(len(past))
        if len(past) >= min_res:
            lo.append(r["yhat"] + np.quantile(past, lo_q))
            hi.append(r["yhat"] + np.quantile(past, hi_q))
        else:
            lo.append(np.nan)
            hi.append(np.nan)
    bt["lo"], bt["hi"], bt["n_calib"] = lo, hi, n
    return bt


def metrics(bt: pd.DataFrame, naive_mae=None) -> dict:
    e = bt["yhat"] - bt["y"]
    out = dict(n=len(bt), mae=np.abs(e).mean(), rmse=np.sqrt((e ** 2).mean()), bias=e.mean(),
               direction=(np.sign(bt["yhat"]) == np.sign(bt["y"])).mean())
    if naive_mae:
        out["mase"] = out["mae"] / naive_mae
    iv = bt.dropna(subset=["lo", "hi"]) if "lo" in bt else pd.DataFrame()
    if len(iv):
        out["coverage"] = ((iv["y"] >= iv["lo"]) & (iv["y"] <= iv["hi"])).mean()
        out["width"] = (iv["hi"] - iv["lo"]).mean()
        out["n_interval"] = len(iv)
    return out


def diebold_mariano(bt_a: pd.DataFrame, bt_b: pd.DataFrame, h: int = 1):
    """DM test on absolute-error differential (a minus b), averaged per issue date; HLN small-sample correction.
    Negative statistic = model a more accurate. Returns (stat, two-sided p, T)."""
    m = bt_a.merge(bt_b, on=["ticker", "tau"], suffixes=("_a", "_b"))
    m["d"] = np.abs(m["yhat_a"] - m["y_a"]) - np.abs(m["yhat_b"] - m["y_b"])
    d = m.groupby("tau")["d"].mean().to_numpy()
    T = len(d)
    if T < 5:
        return np.nan, np.nan, T
    dbar = d.mean()
    gamma = [np.sum((d[k:] - dbar) * (d[:T - k] - dbar)) / T for k in range(h)]
    var = (gamma[0] + 2 * sum(gamma[1:])) / T
    dm = dbar / np.sqrt(var)
    hln = np.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    stat = dm * hln
    p = 2 * stats.t.sf(abs(stat), df=T - 1)
    return float(stat), float(p), T
