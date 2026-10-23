"""Task 2 (ds/PREREGISTRATION.md): how much of FedEx Freight's lost share is explained by relative price?

1. Share panel: five carriers' shipments/day shares and weight-adjusted relative price, by calendar quarter.
2. Elasticity of share to relative price, estimated on the four PEERS only (FedEx held out), with
   leave-one-carrier-out prediction checks and a within-carrier permutation placebo.
3. Applied out of sample to FedEx: explained (price) vs unexplained share change.
4. Changepoints in FedEx's share change (simulation-calibrated penalty; operating characteristics measured).
Outputs: reports/ds/share_*.csv, share_results.json, figures.
"""
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ltlds import config as C  # noqa: E402
from ltlds.share import (calibrated_changepoints, explained, fit_elasticity, permutation_placebo,  # noqa: E402
                         share_panel)
import style as S  # noqa: E402

S.apply()
OUT, FIG = C.OUT, C.OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 200)
res = {}


def section(t):
    print(f"\n=== {t} ===")


# ------------------------------------------------------------------ 1. panel
section("1. Share panel")
q = share_panel()
q.to_csv(OUT / "share_panel.csv", index=False)
print(f"calendar quarters with all 5 carriers: {q['cq'].nunique()} ({q['cq'].min()}..{q['cq'].max()})")
print(q.pivot_table(index="cq", columns="ticker", values="share").iloc[[0, 8, 16, 24, -1]].round(3).to_string())
fdx_share = q[q["ticker"] == "FDX"].set_index("cq")["share"]
res["fdx_share"] = {"first": [str(fdx_share.index[0]), round(fdx_share.iloc[0], 4)],
                    "peak": [str(fdx_share.idxmax()), round(fdx_share.max(), 4)],
                    "last": [str(fdx_share.index[-1]), round(fdx_share.iloc[-1], 4)]}
print("FDX share:", res["fdx_share"])

est = q[~q["covid"]]
peers = est[est["ticker"] != "FDX"]

# ------------------------------------------------------------------ 2. elasticity on peers
section("2. Share-price elasticity, estimated on the four peers (FedEx held out)")
specs = {}
for name, kw, data in [("primary: peers, carrier FE, +lag", dict(lag=True), peers),
                       ("no lag", dict(lag=False), peers),
                       ("+ time FE", dict(lag=True, time_fe=True), peers),
                       ("incl. FDX", dict(lag=True), est)]:
    m, dd = fit_elasticity(data, **kw)
    lr = m.params["d4_rel"] + m.params.get("d4_rel_l1", 0.0)
    ci = m.conf_int().loc["d4_rel"].tolist()
    specs[name] = dict(b0=round(m.params["d4_rel"], 3), b0_ci=[round(c, 3) for c in ci],
                       b1=round(m.params.get("d4_rel_l1", np.nan), 3), long_run=round(lr, 3), n=int(m.nobs),
                       r2=round(m.rsquared, 3))
    print(f"  {name:32s} b0={m.params['d4_rel']:+.3f} CI[{ci[0]:+.2f},{ci[1]:+.2f}] "
          f"b1={m.params.get('d4_rel_l1', np.nan):+.3f} sum={lr:+.3f} n={int(m.nobs)} R2={m.rsquared:.2f}")
res["elasticity_specs"] = specs
primary, _ = fit_elasticity(peers, lag=True)

# ex-fuel robustness (ODFL, SAIA, XPO have ex-fuel yield; FedEx and ARCB do not)
qx = share_panel(price_col="cwt_xf") if "cwt_xf" in q.columns else None
try:
    qx = share_panel(price_col="cwt_xf")
    mx, _ = fit_elasticity(qx[~qx["covid"]], lag=True)
    res["elasticity_ex_fuel_3_carriers"] = dict(b0=round(mx.params["d4_rel"], 3), n=int(mx.nobs))
    print(f"  ex-fuel prices (ODFL/SAIA/XPO only): b0={mx.params['d4_rel']:+.3f} n={int(mx.nobs)}")
except Exception as exc:  # FedEx has no ex-fuel series, so the 5-carrier share panel can't be built ex-fuel
    print(f"  ex-fuel robustness skipped: {type(exc).__name__}: {exc}")

# placebo
real, p_perm, draws = permutation_placebo(peers, n=2000)
print(f"  permutation placebo (2,000 within-carrier shuffles): b0={real:+.3f}, p={p_perm:.4f}")
res["placebo"] = {"b0": round(real, 3), "p_value": round(p_perm, 4), "null_sd": round(float(draws.std()), 3)}

# leave-one-carrier-out predictive check
loco = []
for t in ["ODFL", "SAIA", "XPO", "ARCB"]:
    m_, _ = fit_elasticity(peers[peers["ticker"] != t], lag=True)
    held = peers[peers["ticker"] == t].dropna(subset=["d4_share", "d4_rel", "d4_rel_l1"])
    pred = explained(m_, held) + (held["d4_share"].mean() * 0)  # price-only prediction, no carrier intercept
    loco.append(dict(ticker=t, n=len(held), mae_price_model=float(np.abs(held["d4_share"] - pred).mean()),
                     mae_zero=float(np.abs(held["d4_share"]).mean()),
                     corr=float(np.corrcoef(held["d4_share"], pred)[0, 1])))
loco = pd.DataFrame(loco)
print("  leave-one-carrier-out (price-only prediction of share change vs predicting zero):")
print(loco.round(3).to_string(index=False))
res["loco"] = loco.round(4).to_dict(orient="records")

# ------------------------------------------------------------------ 3. FedEx: explained vs unexplained
section("3. FedEx Freight out of sample: share change explained by relative price vs not")
f = q[(q["ticker"] == "FDX")].dropna(subset=["d4_share", "d4_rel", "d4_rel_l1"]).copy()
f["explained"] = explained(primary, f)
f["unexplained"] = f["d4_share"] - f["explained"]
f["cq"] = f["cq"].astype(str)
show = f[["cq", "d4_share", "d4_rel", "explained", "unexplained", "covid"]]
print(show.round(2).to_string(index=False))
f.to_csv(OUT / "share_fdx_decomposition.csv", index=False)

# ------------------------------------------------------------------ 4. changepoints
section("4. Changepoints in FedEx's YoY share change (exploratory; detector characteristics measured below)")
fx = f[~f["covid"]].reset_index(drop=True)
series = fx["d4_share"].to_numpy()
cps, info = calibrated_changepoints(series, fpr=0.05, sims=1000)
print("detector:", info, "changepoints at", [fx.loc[c, "cq"] for c in cps])
# stability: leave-one-quarter-out
counts = {}
for i in range(len(series)):
    c_, _ = calibrated_changepoints(np.delete(series, i), sims=300, seed=C.SEED + i)
    for c in c_:
        lab = fx.loc[c if c < i else c + 1, "cq"]
        counts[lab] = counts.get(lab, 0) + 1
print("leave-one-out stability (how often each break date recurs, n=%d):" % len(series), counts)
# operating characteristics on simulated series of the same length and noise
rng = np.random.default_rng(C.SEED)
fa, pw = 0, 0
phi, sd = info["phi"], info["sd"]
n = len(series)
for s in range(100):
    z = np.zeros(n)
    z[0] = rng.normal(0, sd)
    for i in range(1, n):
        z[i] = phi * z[i - 1] + rng.normal(0, sd * np.sqrt(1 - phi ** 2))
    fa += len(calibrated_changepoints(z, sims=200, seed=s)[0]) > 0
    zz = z.copy()
    zz[n // 2:] -= 2 * sd
    pw += len(calibrated_changepoints(zz, sims=200, seed=s)[0]) > 0
print(f"simulated at this n/phi/sd: false-alarm rate {fa / 100:.2f}, power for a 2-sd shift {pw / 100:.2f}")
bounds = [0] + cps + [len(fx)]
regimes = []
for a, b in zip(bounds[:-1], bounds[1:]):
    seg = fx.iloc[a:b]
    regimes.append(dict(start=seg["cq"].iloc[0], end=seg["cq"].iloc[-1], n=len(seg),
                        actual=round(seg["d4_share"].mean(), 2), explained=round(seg["explained"].mean(), 2),
                        unexplained=round(seg["unexplained"].mean(), 2), rel_price=round(seg["d4_rel"].mean(), 2)))
regimes = pd.DataFrame(regimes)
print("regimes (mean YoY log-% change in share):"); print(regimes.to_string(index=False))
res["changepoints"] = dict(info=info, dates=[fx.loc[c, "cq"] for c in cps], stability=counts,
                           sim_false_alarm=fa / 100, sim_power_2sd=pw / 100)
res["regimes"] = regimes.to_dict(orient="records")

# also a fixed, theory-driven split for comparison (not data-chosen): pre-spin-announcement vs after
cut = "2024Q4"  # spin-off announced 2024-12-19
pre = fx[(fx["cq"] >= "2022Q3") & (fx["cq"] < cut)]
post = fx[fx["cq"] >= cut]
fixed = {k: dict(n=len(v), actual=round(v["d4_share"].mean(), 2), explained=round(v["explained"].mean(), 2),
                 unexplained=round(v["unexplained"].mean(), 2)) for k, v in [("2022Q3-2024Q3", pre), ("2024Q4-", post)]}
print("fixed split at spin announcement:", fixed)
res["fixed_split"] = fixed

# ------------------------------------------------------------------ non-overlapping annual decomposition
section("5. Non-overlapping annual decomposition (YoY changes at one anchor quarter per year sum exactly)")
f_ok = f[~f["covid"]].copy()
f_ok["qtr"] = f_ok["cq"].str[-1]
anchors = {}
for qn in "1234":
    a = f_ok[f_ok["qtr"] == qn]
    anchors[f"Q{qn}"] = dict(years=f"{a['cq'].iloc[0]}..{a['cq'].iloc[-1]}", n=len(a),
                             actual=round(a["d4_share"].sum(), 2), explained=round(a["explained"].sum(), 2),
                             unexplained=round(a["unexplained"].sum(), 2))
print("cumulative log-% change in FedEx share, by anchor quarter (robustness to the anchor choice):")
print(pd.DataFrame(anchors).T.to_string())
ann = f_ok[f_ok["qtr"] == "2"][["cq", "d4_share", "explained", "unexplained", "d4_rel"]].reset_index(drop=True)
print("annual (Q2 to Q2):"); print(ann.round(2).to_string(index=False))
res["annual_q2"] = ann.round(3).to_dict(orient="records")
res["anchor_robustness"] = anchors

# ------------------------------------------------------------------ figures
fig, ax = plt.subplots(figsize=(7.4, 3.9))
xa = np.arange(len(ann))
ax.bar(xa - 0.27, ann["d4_share"], 0.26, color=S.INK_2, label="actual change in share")
ax.bar(xa, ann["explained"], 0.26, color=S.BLUE, label="explained by relative price")
ax.bar(xa + 0.27, ann["unexplained"], 0.26, color=S.ORANGE, label="not explained by price")
for i, r in ann.iterrows():
    ax.text(i + 0.27, r["unexplained"] + (0.3 if r["unexplained"] >= 0 else -0.3), f"{r['unexplained']:+.1f}",
            ha="center", va="bottom" if r["unexplained"] >= 0 else "top", fontsize=8, color=S.ORANGE)
ax.axhline(0, color=S.INK_2, lw=0.8)
labels = [f"{a[:4]}" for a in ann["cq"]]
ax.set_xticks(xa); ax.set_xticklabels([f"Q2 {int(l) - 1} to\nQ2 {l}" for l in labels], fontsize=8)
ax.set_ylabel("FedEx share of 5-carrier shipments,\nlog-% change over the year")
tot = anchors["Q2"]
ax.set_title("FedEx Freight's share loss: price first, then something else", pad=20)
S.subtitle(ax, f"Mid-2021 to mid-2026: share {tot['actual']:+.1f} log-%, price explains {tot['explained']:+.1f}, "
           f"not price {tot['unexplained']:+.1f}. Elasticity from the 4 peers only")
ax.legend(fontsize=7.5, loc="lower left")
S.save(fig, FIG / "ds6_share_annual.png")

f = f[~f["covid"]].reset_index(drop=True)
fig, ax = plt.subplots(figsize=(7.4, 3.9))
x = np.arange(len(f))
ax.bar(x - 0.2, f["explained"], 0.4, color=S.BLUE, alpha=0.85, label="explained by relative price (peer-estimated)")
ax.bar(x + 0.2, f["unexplained"], 0.4, color=S.ORANGE, alpha=0.7, label="not explained by price")
ax.plot(x, f["d4_share"], color=S.INK, marker="o", ms=3, lw=1.5, label="actual YoY change in share")
if "2024Q4" in list(f["cq"]):
    xi = list(f["cq"]).index("2024Q4")
    ax.axvline(xi - 0.5, color=S.INK_2, ls=":", lw=1)
    ax.text(xi - 0.4, ax.get_ylim()[1] * 0.85 if ax.get_ylim()[1] > 0 else 1, "spin-off\nannounced", fontsize=7.5, color=S.INK_2)
ax.axhline(0, color=S.INK_2, lw=0.8)
step = max(1, len(x) // 9)
ax.set_xticks(x[::step]); ax.set_xticklabels(f["cq"].iloc[::step], fontsize=8)
ax.set_ylabel("FedEx share of 5-carrier shipments, YoY log %")
ax.set_title("How much of FedEx Freight's share change does price explain?", pad=20)
S.subtitle(ax, f"YoY by quarter (overlapping windows). Elasticity from ODFL/SAIA/XPO/ARCB only (b0 {specs['primary: peers, carrier FE, +lag']['b0']:+.2f}), applied to FedEx")
ax.legend(fontsize=7.5, loc="lower left")
S.save(fig, FIG / "ds4_share_explained.png")

fig, ax = plt.subplots(figsize=(6.4, 3.2))
ax.hist(draws, bins=50, color=S.NEUTRAL)
ax.axvline(real, color=S.ORANGE, lw=2)
ax.text(real, ax.get_ylim()[1] * 0.9, f"  estimated {real:+.2f}\n  p = {p_perm:.3f}", color=S.ORANGE, fontsize=8.5)
ax.set_xlabel("elasticity under 2,000 within-carrier shuffles of relative price")
ax.set_title("Placebo test: is the share-price relationship real?", pad=20)
S.subtitle(ax, "Gray = null distribution with the price-share link broken")
S.save(fig, FIG / "ds5_placebo.png")

(OUT / "share_results.json").write_text(json.dumps(res, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print("\nwritten", OUT)
