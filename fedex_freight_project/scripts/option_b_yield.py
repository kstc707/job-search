"""Option B: what is really moving FedEx Freight's yield? Fuel vs weight vs base price.

1. Fuel model. FedEx Freight's published fuel-surcharge tariff (effective 2025-06-09) maps the weekly EIA
   diesel index (10-day lag) to a surcharge %. Realized fuel revenue is far below tariff because of contract
   discounts/caps, so realized_fuel% = rho * tariff%(diesel). rho is estimated on the 8 calendar quarters
   where FDXF disclosed revenue ex-fuel, compared against a naive linear-in-diesel fit (leave-one-out CV),
   then tested out-of-sample on FY2026 Q4 against management's own description of that quarter.
2. Revenue bridge: exact log decomposition of YoY revenue into days, shipments/day, weight/shipment,
   fuel yield and base (ex-fuel) yield per cwt.
3. Weight elasticity of revenue/cwt: heavier shipments mechanically lower revenue per cwt. Estimate the
   elasticity and report a weight-adjusted ("like-for-like") base yield.
Run from the project root: .venv/bin/python -I scripts/option_b_yield.py
"""
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data/raw", ROOT / "data/processed"
OUT = ROOT / "reports/option_b"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 220)
res = {}


def section(t):
    print(f"\n=== {t} ===")


# ------------------------------------------------------------------ inputs
diesel_w = pd.read_csv(RAW / "fred/GASDESW.csv", parse_dates=[0], index_col=0, na_values=".")["GASDESW"].dropna()
table = pd.read_csv(RAW / "external/fedex_freight_fuel_surcharge_table_2025-06-09.csv").set_index("eia_index_cents")["surcharge_pct"]


def tariff_pct(price_usd):
    """FedEx Freight LTL fuel surcharge % for an EIA diesel price, per the 2025-06-09 table."""
    cents = np.floor(np.asarray(price_usd) * 100).astype(int)
    lo, hi = table.index.min(), table.index.max()
    out = table.reindex(np.clip(cents, lo, hi)).to_numpy(dtype=float).copy()
    out[cents < lo] = np.nan  # below the table floor the schedule is undefined (old tables applied)
    return out


# surcharge for week w uses the diesel price from ~10 days earlier -> shift the weekly series by one week
weekly = pd.DataFrame({"diesel": diesel_w})
weekly["diesel_applied"] = weekly["diesel"].shift(1)
weekly["tariff_pct"] = tariff_pct(weekly["diesel_applied"].fillna(0))
weekly.loc[weekly["diesel_applied"].isna(), "tariff_pct"] = np.nan


def period_avg(start, end):
    w = weekly.loc[start:end]
    return w["diesel_applied"].mean(), w["tariff_pct"].mean()


rc = pd.read_csv(PROC / "fdxf_calendar_quarterly_kpis_recast.csv")
rc["start"] = pd.to_datetime(dict(year=rc["calendar_year"], month=3 * rc["calendar_quarter"] - 2, day=1))
rc["end"] = rc["start"] + pd.offsets.QuarterEnd(0)
rc[["diesel", "tariff_pct"]] = [period_avg(s, e) for s, e in zip(rc["start"], rc["end"])]
rc["fuel_ps"] = rc["revenue_per_shipment_usd"] - rc["revenue_per_shipment_ex_fuel_usd"]
rc["fuel_pct"] = 100 * rc["fuel_ps"] / rc["revenue_per_shipment_ex_fuel_usd"]
rc["rho"] = rc["fuel_pct"] / rc["tariff_pct"]

section("1. Fuel model on FDXF's 8 disclosed quarters")
print(rc[["period", "diesel", "tariff_pct", "fuel_pct", "rho", "revenue_per_cwt_ex_fuel_usd"]].round(3).to_string())
rho = rc["rho"].mean()
print(f"rho (realized / tariff) mean={rho:.3f} sd={rc['rho'].std():.3f} cv={rc['rho'].std() / rho:.1%}")

# leave-one-out CV: structural (rho * tariff) vs linear-in-diesel
err_s, err_l = [], []
for i in range(len(rc)):
    tr = rc.drop(index=i)
    err_s.append(rc.loc[i, "fuel_pct"] - tr["rho"].mean() * rc.loc[i, "tariff_pct"])
    b = np.polyfit(tr["diesel"], tr["fuel_pct"], 1)
    err_l.append(rc.loc[i, "fuel_pct"] - np.polyval(b, rc.loc[i, "diesel"]))
mae_s, mae_l = np.mean(np.abs(err_s)), np.mean(np.abs(err_l))
lin = np.polyfit(rc["diesel"], rc["fuel_pct"], 1)
print(f"LOO MAE (fuel % pts): structural {mae_s:.2f}, linear {mae_l:.2f}; linear slope {lin[0]:.2f} pts per $1 "
      f"vs tariff slope 10.0 pts per $1 x rho {rho:.2f} = {10 * rho:.2f}")
res["fuel_model"] = {"rho_mean": round(rho, 3), "rho_sd": round(rc["rho"].std(), 3), "loo_mae_structural_pts": round(mae_s, 2),
                     "loo_mae_linear_pts": round(mae_l, 2), "linear_slope_pts_per_usd": round(lin[0], 2),
                     "diesel_range_in_sample": [round(rc["diesel"].min(), 2), round(rc["diesel"].max(), 2)]}


def fuel_pct_hat(diesel, tariff, method="structural"):
    return rho * tariff if method == "structural" else np.polyval(lin, diesel)


# ------------------------------------------------------------------ out-of-sample: FY2026 Q4
section("2. Out-of-sample test: FY2026 Q4 (Mar-May 2026, diesel spike) vs FY2025 Q4")
k = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"])
k["start"] = (k["period_end"] - pd.offsets.MonthBegin(3)).dt.normalize()
k[["diesel", "tariff_pct"]] = [period_avg(s, e) for s, e in zip(k["start"], k["period_end"])]
k = k.set_index("fiscal_period")
rows = []
for fp in ["FY2025Q4", "FY2026Q4"]:
    r = k.loc[fp]
    for m in ["structural", "linear"]:
        fp_hat = fuel_pct_hat(r["diesel"], r["tariff_pct"], m)
        ex_rps = r["revenue_per_shipment_usd"] / (1 + fp_hat / 100)
        ex_cwt = r["revenue_per_cwt_usd"] / (1 + fp_hat / 100)
        rows.append(dict(period=fp, method=m, diesel=r["diesel"], tariff_pct=r["tariff_pct"], fuel_pct_hat=fp_hat,
                         rps=r["revenue_per_shipment_usd"], rps_ex_fuel_hat=ex_rps, cwt=r["revenue_per_cwt_usd"],
                         cwt_ex_fuel_hat=ex_cwt, wps=r["weight_per_shipment_lbs"]))
oos = pd.DataFrame(rows)
print(oos.round(2).to_string())
for m in ["structural", "linear"]:
    a, b = oos[(oos.method == m) & (oos.period == "FY2025Q4")].iloc[0], oos[(oos.method == m) & (oos.period == "FY2026Q4")].iloc[0]
    base_cwt_yoy = 100 * (b["cwt_ex_fuel_hat"] / a["cwt_ex_fuel_hat"] - 1)
    print(f"{m:10s}: base (ex-fuel) revenue/cwt YoY = {base_cwt_yoy:+.1f}%   "
          f"[management, 8-K 2026-06-25: 'a slight decline in base revenue per hundredweight']")
    res.setdefault("oos_fy26q4", {})[m] = round(base_cwt_yoy, 1)
# out-of-range warning: in-sample diesel max vs FY26Q4
print(f"FY26Q4 diesel {k.loc['FY2026Q4', 'diesel']:.2f} is {k.loc['FY2026Q4', 'diesel'] - rc['diesel'].max():+.2f} $/gal "
      "beyond the in-sample range: the structural model leans on the published tariff to extrapolate; the linear one cannot.")

# ------------------------------------------------------------------ revenue bridge
section("3. Revenue bridge, YoY, exact log decomposition")
k["ltl_rev_implied"] = k["operating_days"] * k["avg_daily_shipments_k"] * 1e3 * k["revenue_per_shipment_usd"] / 1e6
k["ltl_share_of_revenue"] = k["ltl_rev_implied"] / k["revenue_musd"]
print("Implied LTL revenue / reported segment revenue: "
      f"median {k['ltl_share_of_revenue'].median():.3f}, range {k['ltl_share_of_revenue'].min():.3f}-{k['ltl_share_of_revenue'].max():.3f}")
k["fuel_pct_hat"] = np.where(k["tariff_pct"].notna(), rho * k["tariff_pct"], np.nan)
L = np.log
b = pd.DataFrame(index=k.index)
b["days"] = L(k["operating_days"]).diff(4)
b["shipments_per_day"] = L(k["avg_daily_shipments_k"]).diff(4)
b["weight_per_shipment"] = L(k["weight_per_shipment_lbs"]).diff(4)
b["fuel"] = L(1 + k["fuel_pct_hat"] / 100).diff(4)
b["base_yield_per_cwt"] = L(k["revenue_per_cwt_usd"] / (1 + k["fuel_pct_hat"] / 100)).diff(4)
b["yield_per_cwt_total"] = L(k["revenue_per_cwt_usd"]).diff(4)
b["ltl_revenue"] = L(k["ltl_rev_implied"]).diff(4)
chk = b[["days", "shipments_per_day", "weight_per_shipment", "yield_per_cwt_total"]].sum(axis=1) - b["ltl_revenue"]
# revenue/shipment = revenue/cwt * weight/100, so the identity holds up to rounding of reported stats
print(f"identity check, max |sum of components - log revenue change| = {chk.abs().max():.4f}")
show = (100 * b).loc["FY2024Q1":, ["ltl_revenue", "days", "shipments_per_day", "weight_per_shipment", "fuel", "base_yield_per_cwt"]]
print("Log-points (~%) contribution to YoY LTL revenue change:"); print(show.round(1).to_string())
show.to_csv(OUT / "revenue_bridge_yoy.csv")
res["bridge_fy26q4"] = show.loc["FY2026Q4"].round(1).to_dict()

r = show.loc["FY2026Q4"]
fig, ax = plt.subplots(figsize=(8, 4.5))
parts = ["days", "shipments_per_day", "weight_per_shipment", "fuel", "base_yield_per_cwt"]
labels = ["Operating days", "Shipments/day", "Weight/shipment", "Fuel surcharge", "Base yield/cwt"]
cum = 0
for i, (p, lab) in enumerate(zip(parts, labels)):
    v = r[p]
    ax.bar(i, v, bottom=cum, color="C2" if v >= 0 else "C3")  # negative height draws downward from cum
    ax.text(i, cum + v + (0.4 if v >= 0 else -0.9), f"{v:+.1f}", ha="center", fontsize=9)
    cum += v
ax.bar(len(parts), cum, color="C0"); ax.text(len(parts), cum + 0.4, f"{cum:+.1f}", ha="center", fontsize=9)
ax.set_xticks(range(len(parts) + 1)); ax.set_xticklabels(labels + ["LTL revenue"], rotation=20, fontsize=8)
ax.axhline(0, color="k", lw=0.8)
ax.set_title("FY2026 Q4 vs FY2025 Q4: what drove LTL revenue (log-points, ~%)\nfuel split uses the published tariff x realized ratio")
fig.tight_layout(); fig.savefig(FIG / "b1_fy26q4_revenue_bridge.png", dpi=130); plt.close(fig)

# ------------------------------------------------------------------ weight elasticity
section("4. Weight elasticity of revenue/cwt")
# Naive time series: 4-quarter log change of yield/cwt on weight/shipment + diesel (HAC errors). Biased: FedEx's
# 2022-23 general rate increases coincided with falling weight, so pricing gets attributed to weight.
d = pd.DataFrame({"dl_cwt": L(k["revenue_per_cwt_usd"]).diff(4), "dl_wps": L(k["weight_per_shipment_lbs"]).diff(4),
                  "dl_diesel": L(k["diesel"]).diff(4)}).dropna()
m = sm.OLS(d["dl_cwt"], sm.add_constant(d[["dl_wps", "dl_diesel"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
naive, naive_ci = m.params["dl_wps"], m.conf_int().loc["dl_wps"].tolist()
print(f"naive time series: beta={naive:.2f} (95% CI {naive_ci[0]:.2f} to {naive_ci[1]:.2f}), n={int(m.nobs)}"
      " -> implies heavier shipments earn LESS per shipment: not credible (pricing confounded)")
# Preferred: Priority vs Economy panel, 4-quarter log changes, quarter fixed effects. Quarter FE absorb everything
# common to both services that quarter (rate increases, fuel, macro); beta is identified from the two services'
# relative weight moves. Standard errors clustered by quarter.
import statsmodels.formula.api as smf
pan = []
for seg in ["priority", "economy"]:
    pan.append(pd.DataFrame({"q": k.index, "seg": seg, "lc": L(k[f"revenue_per_cwt_usd_{seg}"]),
                             "lw": L(k[f"weight_per_shipment_lbs_{seg}"])}))
pan = pd.concat(pan)
pan["dc"] = pan.groupby("seg")["lc"].diff(4)
pan["dw"] = pan.groupby("seg")["lw"].diff(4)
pan = pan.dropna()
mp = smf.ols("dc ~ dw + C(q)", pan).fit(cov_type="cluster", cov_kwds={"groups": pan["q"]})
beta, ci = mp.params["dw"], mp.conf_int().loc["dw"].tolist()
print(f"preferred panel (Priority/Economy x quarter FE): beta={beta:.2f} (95% CI {ci[0]:.2f} to {ci[1]:.2f}), n={int(mp.nobs)}")
print(f"=> a 10% heavier shipment lowers revenue/cwt ~{-10 * beta:.1f}% but raises revenue/shipment ~{10 * (1 + beta):.1f}%")
res["weight_elasticity"] = {"preferred_beta": round(beta, 2), "ci95": [round(c, 2) for c in ci], "n": int(mp.nobs),
                            "naive_beta": round(naive, 2), "naive_ci95": [round(c, 2) for c in naive_ci]}
# weight-adjusted base yield YoY for recent quarters: strip the mechanical weight effect from base yield
adj = (b["base_yield_per_cwt"] - beta * b["weight_per_shipment"]) * 100
print("Weight-adjusted base yield/cwt YoY (log-pts) - a like-for-like price signal:")
print(adj.loc["FY2025Q1":].round(1).to_string())
res["weight_adjusted_base_yield_yoy"] = adj.loc["FY2025Q1":].round(1).to_dict()

# ------------------------------------------------------------------ Jun-Sep 2026 fuel tailwind
section("5. Fuel effect in FDXF's Jun-Sep 2026 transition period (reports 2026-10-29)")
d_now, t_now = period_avg("2026-06-01", "2026-09-30")
d_ly, t_ly = period_avg("2025-06-01", "2025-09-30")
fp_now, fp_ly = rho * t_now, rho * t_ly
print(f"diesel {d_ly:.2f} -> {d_now:.2f}; tariff {t_ly:.1f}% -> {t_now:.1f}%; modeled realized fuel {fp_ly:.1f}% -> {fp_now:.1f}%")
print(f"=> fuel alone lifts revenue/shipment by about {100 * ((1 + fp_now / 100) / (1 + fp_ly / 100) - 1):+.1f}% YoY")
res["jun_sep_2026"] = {"diesel": [round(d_ly, 2), round(d_now, 2)], "fuel_pct": [round(fp_ly, 1), round(fp_now, 1)],
                       "fuel_lift_rps_pct": round(100 * ((1 + fp_now / 100) / (1 + fp_ly / 100) - 1), 1)}

section("6. 2027 fuel headwind (EIA STEO forecasts $4.49/gal diesel for 2027; Sept 2026 averaged $6.29)")
d_q4, t_q4 = period_avg("2026-10-01", "2026-10-31")  # latest weeks available
for label, price in [("Oct 2026 to date", d_q4), ("EIA 2027 forecast", 4.49)]:
    tp = float(tariff_pct(np.array([price]))[0])
    print(f"{label:18s} diesel ${price:.2f} -> tariff {tp:.1f}% -> realized ~{rho * tp:.1f}%")
fp_now_q4 = rho * float(tariff_pct(np.array([d_q4]))[0])
fp_27 = rho * float(tariff_pct(np.array([4.49]))[0])
head = 100 * ((1 + fp_27 / 100) / (1 + fp_now_q4 / 100) - 1)
print(f"=> if diesel follows EIA, fuel alone moves revenue/shipment {head:+.1f}% from the Oct-2026 run-rate; "
      f"vs Jun-Sep 2026 ({fp_now:.1f}% fuel): {100 * ((1 + fp_27 / 100) / (1 + fp_now / 100) - 1):+.1f}%")
res["fuel_2027"] = {"oct2026_diesel": round(d_q4, 2), "oct2026_fuel_pct": round(fp_now_q4, 1), "eia_2027_diesel": 4.49,
                    "eia_2027_fuel_pct": round(fp_27, 1), "rps_change_vs_oct2026_pct": round(head, 1),
                    "rps_change_vs_junsep2026_pct": round(100 * ((1 + fp_27 / 100) / (1 + fp_now / 100) - 1), 1)}

fig, ax = plt.subplots(figsize=(8, 4.5))
xs = np.linspace(3.3, 6.5, 100)
ax.plot(xs, tariff_pct(xs), label="Published tariff (2025-06-09)", color="0.5")
ax.plot(xs, rho * tariff_pct(xs), label=f"Structural model: {rho:.2f} x tariff", color="C0")
ax.plot(xs, np.polyval(lin, xs), "--", label="Linear fit on 8 quarters", color="C1")
ax.scatter(rc["diesel"], rc["fuel_pct"], color="k", zorder=3, label="FDXF disclosed quarters (CY24-25)")
for fp in ["FY2025Q4", "FY2026Q4"]:
    ax.axvline(k.loc[fp, "diesel"], color="C3", lw=0.8, ls=":")
    ax.text(k.loc[fp, "diesel"], 12, fp, rotation=90, fontsize=8, color="C3")
ax.axvline(d_now, color="C4", lw=0.8, ls=":"); ax.text(d_now, 12, "Jun-Sep 2026", rotation=90, fontsize=8, color="C4")
ax.set_xlabel("Diesel $/gal (EIA, 10-day lag)"); ax.set_ylabel("Fuel surcharge, % of ex-fuel revenue")
ax.set_title("Fuel surcharge: published tariff vs what FedEx Freight actually realizes")
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(FIG / "b2_fuel_model.png", dpi=130); plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(d.index if False else k.index, k["weight_per_shipment_lbs"], marker="o", ms=3)
ax.set_xticks(range(0, len(k), 4)); ax.set_xticklabels(k.index[::4], rotation=30, fontsize=8)
ax.axvline(list(k.index).index("FY2026Q1") - 0.5, color="C3", ls=":", lw=1)
ax.text(list(k.index).index("FY2026Q1") - 0.4, 1150, "NMFC density classes\neffective 2025-07-19", fontsize=8, color="C3")
ax.set_title("Weight per shipment (lbs): 6-year decline, turned up after the NMFC change")
fig.tight_layout(); fig.savefig(FIG / "b3_weight_per_shipment.png", dpi=130); plt.close(fig)

(OUT / "results.json").write_text(json.dumps(res, indent=2, default=float))
print("\nwritten:", OUT)
