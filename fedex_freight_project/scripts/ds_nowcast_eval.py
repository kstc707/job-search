"""Task 1 evaluation (ds/PREREGISTRATION.md): rolling-origin backtest of the pre-registered models, DM tests,
conformal and quantile intervals, ablation, permutation importance, error analysis. Outputs in reports/ds/."""
import json
import pathlib
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ltlds import config as C  # noqa: E402
from ltlds.evaluate import add_conformal, diebold_mariano, metrics, rolling_origin, usable  # noqa: E402
from ltlds.models import NUMERIC, GBMModel, RidgeModel, model_zoo  # noqa: E402
import style as S  # noqa: E402

S.apply()
OUT = C.OUT
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 200)
p = pd.read_csv(OUT / "panel.csv", parse_dates=["end", "start", "tau", "known"])
res = {"preregistration": "ds/PREREGISTRATION.md", "test_from": C.TEST_FROM}
t0 = time.time()


def section(t):
    print(f"\n=== {t} === ({time.time() - t0:.0f}s)")


# ------------------------------------------------------------------ 1. backtests
section("1. Rolling-origin backtests")
zoo = model_zoo()
bts = {}
for name in ["naive", "market", "own_monthly", "ridge", "gbm"]:
    bts[name] = add_conformal(rolling_origin(p, zoo[name]))
    print(f"{name}: {len(bts[name])} predictions")
ens = bts["ridge"][["ticker", "period", "tau", "y", "n_train", "train_last_known"]].copy()
ens["yhat"] = (bts["ridge"].set_index(["ticker", "tau"])["yhat"] + bts["gbm"].set_index(["ticker", "tau"])["yhat"]).reindex(
    pd.MultiIndex.from_frame(ens[["ticker", "tau"]])).to_numpy() / 2  # members are deterministic: same as refitting
bts["ensemble"] = add_conformal(ens)
allbt = pd.concat([b.assign(model=k) for k, b in bts.items()])
allbt.to_csv(OUT / "backtest_predictions.csv", index=False)

test = {k: b[b["tau"] >= C.TEST_FROM] for k, b in bts.items()}
naive_mae = metrics(test["naive"])["mae"]
tab = pd.DataFrame({k: metrics(b, naive_mae) for k, b in test.items()}).T.sort_values("mae")
print(tab.round(3).to_string())
fdx = pd.DataFrame({k: metrics(b[b["ticker"] == "FDX"], metrics(test["naive"][test["naive"]["ticker"] == "FDX"])["mae"])
                    for k, b in test.items()}).T.sort_values("mae")
print("FDX only:"); print(fdx.round(3).to_string())
per = pd.DataFrame({k: b.assign(ae=(b["yhat"] - b["y"]).abs()).groupby("ticker")["ae"].mean() for k, b in test.items()})
print("MAE by carrier:"); print(per.round(2).to_string())
res["metrics_all"] = tab.round(4).to_dict(orient="index")
res["metrics_fdx"] = fdx.round(4).to_dict(orient="index")
res["mae_by_carrier"] = per.round(3).to_dict()

# block bootstrap over issue dates for MAE confidence intervals
rng = np.random.default_rng(C.SEED)
taus = np.sort(test["naive"]["tau"].unique())
ci = {}
for k, b in test.items():
    ae = b.assign(ae=(b["yhat"] - b["y"]).abs()).groupby("tau")["ae"].agg(["sum", "count"])
    draws = []
    for _ in range(2000):
        s = rng.choice(taus, size=len(taus), replace=True)
        sub = ae.loc[s]
        draws.append(sub["sum"].sum() / sub["count"].sum())
    ci[k] = np.percentile(draws, [5, 95]).round(3).tolist()
res["mae_ci90_block_bootstrap"] = ci
print("MAE 90% CI (block bootstrap over issue dates):", ci)

# ------------------------------------------------------------------ 2. significance
section("2. Diebold-Mariano (HLN) vs naive and between ML models")
dm = {}
for k in tab.index:
    if k == "naive":
        continue
    dm[f"{k}_vs_naive"] = diebold_mariano(test[k], test["naive"])
for a, b in [("gbm", "ridge"), ("ensemble", "ridge"), ("ensemble", "market"), ("gbm", "market")]:
    dm[f"{a}_vs_{b}"] = diebold_mariano(test[a], test[b])
for k, (st, pv, T) in dm.items():
    print(f"  {k:22s} DM={st:+.2f} p={pv:.3f} T={T}")
res["diebold_mariano"] = {k: {"stat": round(v[0], 3), "p": round(v[1], 4), "T": v[2]} for k, v in dm.items()}
best = tab.index[0]
crit = tab.loc[best, "mae"] <= 0.9 * naive_mae and dm.get(f"{best}_vs_naive", (0, 1, 0))[1] < 0.10
print(f"pre-registered usefulness criterion for best model '{best}': {'MET' if crit else 'NOT MET'}")
res["best_model"], res["usefulness_criterion_met"] = best, bool(crit)

# ------------------------------------------------------------------ 3. intervals
section("3. Prediction intervals: rolling split-conformal vs quantile GBM")
cov = {k: {"coverage": round(metrics(b).get("coverage", np.nan), 3), "width": round(metrics(b).get("width", np.nan), 2),
           "n": metrics(b).get("n_interval", 0)} for k, b in test.items()}
q_params = dict(max_depth=2, learning_rate=0.05, max_iter=200, min_samples_leaf=10)
qlo = rolling_origin(p, lambda: GBMModel(params=q_params, loss="quantile", quantile=0.1))
qhi = rolling_origin(p, lambda: GBMModel(params=q_params, loss="quantile", quantile=0.9))
qq = qlo.merge(qhi[["ticker", "tau", "yhat"]], on=["ticker", "tau"], suffixes=("_lo", "_hi"))
qq = qq[qq["tau"] >= C.TEST_FROM]
cov["quantile_gbm"] = {"coverage": round(((qq["y"] >= qq["yhat_lo"]) & (qq["y"] <= qq["yhat_hi"])).mean(), 3),
                       "width": round((qq["yhat_hi"] - qq["yhat_lo"]).mean(), 2), "n": len(qq)}
for k, v in cov.items():
    flag = "calibrated" if 0.70 <= v["coverage"] <= 0.90 else "NOT calibrated"
    print(f"  {k:14s} coverage={v['coverage']:.2f} width={v['width']:.1f}pp n={v['n']}  [{flag}]")
res["intervals_80"] = cov

# ------------------------------------------------------------------ 4. ablation
section("4. Ablation: drop one feature group (retuned at every origin)")
abl = {}
base_cols = NUMERIC + ["carrier_code"]
for model_name, maker in [("ridge", lambda cols: RidgeModel(cols=cols)), ("gbm", lambda cols: GBMModel(cols=cols))]:
    base = metrics(test[model_name])["mae"]
    abl[model_name] = {}
    for g, cols in C.FEATURE_GROUPS.items():
        keep = [c for c in base_cols if c not in cols]
        bt = rolling_origin(p, lambda keep=keep: maker(keep))
        mae = metrics(bt[bt["tau"] >= C.TEST_FROM])["mae"]
        abl[model_name][g] = round(mae - base, 3)
        print(f"  {model_name:5s} without {g:12s}: MAE {mae:.3f} (change {mae - base:+.3f})")
res["ablation_delta_mae"] = abl

# ------------------------------------------------------------------ 5. permutation importance (holdout)
section("5. Permutation importance on a temporal holdout (train: published before 2022, test: 2022+)")
d = usable(p)
tr, te = d[d["known"] < pd.Timestamp(C.TEST_FROM)], d[d["tau"] >= pd.Timestamp(C.TEST_FROM)]
imp = {}
for model_name, m in [("ridge", RidgeModel().fit(tr)), ("gbm", GBMModel().fit(tr))]:
    base = np.abs(m.predict(te) - te["y"]).mean()
    imp[model_name] = {"holdout_mae": round(base, 3)}
    for g, cols in C.FEATURE_GROUPS.items():
        incs = []
        for _ in range(30):
            Xp = te.copy()
            perm = rng.permutation(len(Xp))
            for c in cols:
                Xp[c] = Xp[c].to_numpy()[perm]
            incs.append(np.abs(m.predict(Xp) - te["y"]).mean() - base)
        imp[model_name][g] = round(float(np.mean(incs)), 3)
    print(f"  {model_name}: " + ", ".join(f"{g} {v:+.2f}" for g, v in imp[model_name].items()))
res["permutation_importance_holdout"] = imp

# ------------------------------------------------------------------ 6. error analysis
section("6. Largest errors of the best model")
b = test[best].assign(err=lambda x: x["yhat"] - x["y"]).sort_values("err", key=np.abs, ascending=False)
print(b.head(10)[["ticker", "period", "y", "yhat", "err"]].round(1).to_string(index=False))
res["largest_errors"] = b.head(10)[["ticker", "period", "y", "yhat", "err"]].round(2).to_dict(orient="records")

# ------------------------------------------------------------------ figures
order = tab.index.tolist()
fig, ax = plt.subplots(figsize=(7.2, 3.6))
ax.barh(order, tab["mae"], color=[S.BLUE if o != "naive" else S.NEUTRAL for o in order], height=0.6)
for i, o in enumerate(order):
    ax.plot(ci[o], [i, i], color=S.INK_2, lw=1.2)
    ax.text(ci[o][1] + 0.05, i, f"{tab.loc[o, 'mae']:.2f}", va="center", fontsize=8.5)
ax.invert_yaxis(); ax.grid(axis="x"); ax.grid(axis="y", visible=False)
ax.set_xlabel("MAE, YoY percentage points (90% block-bootstrap CI)")
ax.set_title("Out-of-sample error by model, 2022-2026 (5 carriers)", pad=20)
S.subtitle(ax, f"{int(tab.loc['naive', 'n'])} carrier-quarters, rolling origin, nested tuning; lower is better")
S.save(fig, FIG / "ds1_model_mae.png")

fig, axes = plt.subplots(1, 5, figsize=(12, 2.8), sharey=True)
for ax, t in zip(axes, C.CARRIERS):
    bb = test[best][test[best]["ticker"] == t].sort_values("tau")
    ax.fill_between(bb["tau"], bb["lo"], bb["hi"], color=S.BLUE, alpha=0.15, lw=0)
    ax.plot(bb["tau"], bb["y"], color=S.INK, marker="o", ms=2.5, lw=1.5)
    ax.plot(bb["tau"], bb["yhat"], color=S.BLUE, ls="--", lw=1.5)
    ax.set_title(t, fontsize=10); ax.tick_params(axis="x", labelrotation=45, labelsize=7)
axes[0].set_ylabel("shipments/day YoY %")
fig.suptitle(f"Best model ({best}) out of sample: actual (black), forecast (dashed), 80% conformal band", fontsize=10, x=0.01, ha="left")
fig.tight_layout(); fig.savefig(FIG / "ds2_oos_by_carrier.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.2, 3.4))
groups = list(C.FEATURE_GROUPS)
x = np.arange(len(groups))
ax.bar(x - 0.2, [abl["ridge"][g] for g in groups], 0.4, color=S.BLUE, label="ridge")
ax.bar(x + 0.2, [abl["gbm"][g] for g in groups], 0.4, color=S.AQUA, label="gbm")
ax.axhline(0, color=S.INK_2, lw=0.8); ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=8.5)
ax.set_ylabel("change in MAE when dropped (pp)"); ax.legend()
ax.set_title("Ablation: which information carries the forecast", pad=20)
S.subtitle(ax, "Positive = model gets worse without the group; each variant retuned at every origin")
S.save(fig, FIG / "ds3_ablation.png")

(OUT / "nowcast_results.json").write_text(json.dumps(res, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print(f"\nwritten {OUT} in {time.time() - t0:.0f}s")
