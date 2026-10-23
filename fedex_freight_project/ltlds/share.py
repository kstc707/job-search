"""Task 2 (ds/PREREGISTRATION.md): carrier shares, weight-adjusted relative price, share-price elasticity,
and changepoint detection on FedEx Freight's share."""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import config as cfg
from .panel import load_quarters

BETA_WEIGHT = -0.57  # cross-carrier elasticity of revenue/cwt to weight/shipment (reports/option_b, peer_check)


def calendar_quarter(end: pd.Series) -> pd.PeriodIndex:
    """Map a quarter's end date to the calendar quarter it overlaps by at least two months.
    FedEx fiscal quarters end Feb/May/Aug/Nov -> Q1/Q2/Q3/Q4; calendar quarters map to themselves."""
    return (pd.to_datetime(end) - pd.DateOffset(months=1)).dt.to_period("Q")


def share_panel(beta: float = BETA_WEIGHT, price_col: str = "cwt") -> pd.DataFrame:
    q = load_quarters()
    q["cq"] = calendar_quarter(q["end"])
    q = q.dropna(subset=["spd", price_col, "wps"]).drop_duplicates(["ticker", "cq"])
    full = q.groupby("cq")["ticker"].nunique()
    n_need = q["ticker"].nunique()
    q = q[q["cq"].isin(full[full == n_need].index)].copy()
    q["share"] = q["spd"] / q.groupby("cq")["spd"].transform("sum")
    q["adj_price"] = np.log(q[price_col]) - beta * np.log(q["wps"])  # like-for-like price index (log)
    rel = []
    for _, r in q.iterrows():
        oth = q[(q["cq"] == r["cq"]) & (q["ticker"] != r["ticker"])]
        w = oth["spd"] / oth["spd"].sum()
        rel.append(r["adj_price"] - np.log((w * np.exp(oth["adj_price"])).sum()))
    q["rel_price"] = rel
    q = q.sort_values(["ticker", "cq"])
    g = q.groupby("ticker")
    q["d4_share"] = 100 * (np.log(q["share"]) - g["share"].transform(lambda s: np.log(s).shift(4)))
    q["d4_rel"] = 100 * (q["rel_price"] - g["rel_price"].shift(4))
    q["d4_rel_l1"] = q.groupby("ticker")["d4_rel"].shift(1)
    # require exactly 4 calendar quarters between rows used in the differences
    q["gap_ok"] = (q["cq"] - g["cq"].shift(4)).apply(lambda x: getattr(x, "n", np.nan)) == 4
    q.loc[~q["gap_ok"], ["d4_share", "d4_rel"]] = np.nan
    q["covid"] = q["cq"].dt.start_time.between("2020-01-01", "2021-06-30")
    return q.reset_index(drop=True)


def fit_elasticity(d: pd.DataFrame, lag=True, time_fe=False):
    f = "d4_share ~ d4_rel" + (" + d4_rel_l1" if lag else "") + " + C(ticker)" + (" + C(cq)" if time_fe else "")
    dd = d.dropna(subset=["d4_share", "d4_rel"] + (["d4_rel_l1"] if lag else []))
    dd = dd.assign(cq=dd["cq"].astype(str))
    m = smf.ols(f, dd).fit(cov_type="cluster", cov_kwds={"groups": dd["cq"]})
    return m, dd


def explained(m, d: pd.DataFrame) -> pd.Series:
    """Share change implied by relative price alone (no carrier or time effects)."""
    out = m.params["d4_rel"] * d["d4_rel"]
    if "d4_rel_l1" in m.params:
        out = out + m.params["d4_rel_l1"] * d["d4_rel_l1"]
    return out


def permutation_placebo(d: pd.DataFrame, n=2000, seed=cfg.SEED, lag=True):
    """Null distribution of the elasticity: shuffle relative-price changes within each carrier."""
    rng = np.random.default_rng(seed)
    dd = d.dropna(subset=["d4_share", "d4_rel"] + (["d4_rel_l1"] if lag else [])).copy()
    real = fit_elasticity(dd, lag=lag)[0].params["d4_rel"]
    draws = []
    for _ in range(n):
        x = dd.copy()
        for t, idx in x.groupby("ticker").groups.items():
            perm = rng.permutation(len(idx))
            x.loc[idx, "d4_rel"] = x.loc[idx, "d4_rel"].to_numpy()[perm]
            if lag:
                x.loc[idx, "d4_rel_l1"] = x.loc[idx, "d4_rel_l1"].to_numpy()[perm]
        draws.append(fit_elasticity(x, lag=lag)[0].params["d4_rel"])
    draws = np.array(draws)
    return real, float((np.abs(draws) >= abs(real)).mean()), draws


# ---------------------------------------------------------------- changepoints (optimal partitioning, L2 cost)
def optimal_partition(x: np.ndarray, penalty: float, min_size: int = 3) -> list:
    """Exact penalized segmentation of x into piecewise-constant means (optimal partitioning, Jackson et al. 2005;
    PELT gives the same answer faster, unnecessary at n ~ 35). Returns sorted start indices of new segments."""
    x = np.asarray(x, float)
    n = len(x)
    cs, cs2 = np.concatenate([[0], np.cumsum(x)]), np.concatenate([[0], np.cumsum(x ** 2)])

    def cost(a, b):  # sum of squared deviations of x[a:b] from its mean
        s, s2, m = cs[b] - cs[a], cs2[b] - cs2[a], b - a
        return s2 - s * s / m

    F = np.full(n + 1, np.inf)
    F[0] = -penalty
    last = np.zeros(n + 1, int)
    for t in range(min_size, n + 1):
        for s in range(0, t - min_size + 1):
            if s != 0 and s < min_size:
                continue
            v = F[s] + cost(s, t) + penalty
            if v < F[t]:
                F[t], last[t] = v, s
    cps, t = [], n
    while t > 0:
        s = last[t]
        if s > 0:
            cps.append(s)
        t = s
    return sorted(cps)


def bic_penalty(x: np.ndarray) -> float:
    """BIC-style penalty: 2 * sigma^2 * ln(n), sigma from the MAD of first differences (robust to mean shifts)."""
    x = np.asarray(x, float)
    sigma = np.median(np.abs(np.diff(x) - np.median(np.diff(x)))) * 1.4826 / np.sqrt(2)
    return 2 * sigma ** 2 * np.log(len(x))


def _ar1(resid: np.ndarray) -> float:
    r = resid - resid.mean()
    return float(np.clip(np.sum(r[1:] * r[:-1]) / np.sum(r[:-1] ** 2), -0.95, 0.95))


def segment_residuals(x: np.ndarray, cps: list) -> np.ndarray:
    bounds = [0] + list(cps) + [len(x)]
    return np.concatenate([x[a:b] - x[a:b].mean() for a, b in zip(bounds[:-1], bounds[1:])])


def robust_noise(x: np.ndarray):
    """AR(1) coefficient and innovation-scale of x estimated from first differences, which a few mean shifts
    barely affect: drop differences more than 3 MADs from the median (the jumps), then use
    corr(d_t, d_{t-1}) = -(1 - phi)/2 and var(d) = 2 sd^2 (1 - phi) for a stationary AR(1) with sd = sd(x)."""
    d = np.diff(np.asarray(x, float))
    med, mad = np.median(d), np.median(np.abs(d - np.median(d))) * 1.4826
    keep = np.abs(d - med) <= 3 * max(mad, 1e-9)
    pairs = [(d[i], d[i - 1]) for i in range(1, len(d)) if keep[i] and keep[i - 1]]
    a, b = np.array(pairs).T
    rho = np.corrcoef(a, b)[0, 1] if len(pairs) > 3 else -0.5
    phi = 1 + 2 * rho
    phi = float(np.clip(phi + (1 + 3 * phi) / len(x), -0.9, 0.95))  # Kendall small-sample bias correction
    sd = float(np.sqrt(d[keep].var(ddof=1) / (2 * (1 - phi))))
    return phi, sd


def calibrated_changepoints(x: np.ndarray, fpr: float = 0.05, sims: int = 1000, seed: int = cfg.SEED,
                            min_size: int = 3):
    """Changepoints with a penalty calibrated by simulation: on a series of the same length with the same AR(1)
    noise (estimated robustly from first differences) and NO change, a changepoint is found with probability
    <= fpr. Returns (changepoints, details)."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    n = len(x)
    phi, sd = robust_noise(x)
    need = []
    for _ in range(sims):
        e = rng.normal(0, sd * np.sqrt(1 - phi ** 2), n)
        z = np.empty(n)
        z[0] = rng.normal(0, sd)
        for i in range(1, n):
            z[i] = phi * z[i - 1] + e[i]
        need.append(_min_penalty_for_no_change(z, min_size))
    pen = float(np.quantile(need, 1 - fpr))
    cps = optimal_partition(x, pen, min_size)
    return [int(c) for c in cps], dict(phi=round(phi, 3), sd=round(sd, 3), penalty=round(pen, 2), fpr=fpr, sims=sims)


def _min_penalty_for_no_change(z: np.ndarray, min_size: int) -> float:
    """Smallest penalty at which the optimal segmentation of z has no changepoint."""
    tot = np.sum((z - z.mean()) ** 2)
    # no-change is optimal iff for every k >= 1: cost_k + k*pen >= tot, i.e. pen >= (tot - cost_k)/k (k <= 3 here;
    # with min_size 3 and n ~ 35 more splits never beat the best <=3-split gain per split in practice)
    best = 0.0
    for k in (1, 2, 3):
        ck = _best_k_split_cost(z, k, min_size)
        if np.isfinite(ck):
            best = max(best, (tot - ck) / k)
    return best


def _best_k_split_cost(z: np.ndarray, k: int, min_size: int) -> float:
    """Minimum within-segment SSE using exactly k changepoints (dynamic programming)."""
    n = len(z)
    cs, cs2 = np.concatenate([[0], np.cumsum(z)]), np.concatenate([[0], np.cumsum(z ** 2)])

    def cost(a, b):
        s, s2, m = cs[b] - cs[a], cs2[b] - cs2[a], b - a
        return s2 - s * s / m

    D = np.full((k + 2, n + 1), np.inf)
    D[0, 0] = 0.0
    for seg in range(1, k + 2):
        for t in range(seg * min_size, n + 1):
            D[seg, t] = min((D[seg - 1, s] + cost(s, t) for s in range((seg - 1) * min_size, t - min_size + 1)
                             if np.isfinite(D[seg - 1, s])), default=np.inf)
    return D[k + 1, n]
