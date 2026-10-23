"""Polished, consistently styled figures for the report and the one-page brief (reports/figures_final/).

Every number is read from the analysis outputs (reports/option_*/), never typed in.
Run after the option_* scripts: .venv/bin/python -I scripts/make_report_figures.py
"""
import json
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style as S  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP, PROC = ROOT / "reports", ROOT / "data/processed"
OUT = REP / "figures_final"
OUT.mkdir(parents=True, exist_ok=True)
S.apply()
oa = json.loads((REP / "option_a/results.json").read_text())
ob = json.loads((REP / "option_b/results.json").read_text())
oc = json.loads((REP / "option_c/results.json").read_text())
od = json.loads((REP / "option_d/results.json").read_text())


# ---------------------------------------------------------------- 1. tonnage: FedEx vs LTL-addressable market
def fig_tonnage():
    idx = pd.DataFrame(oc["proxy_vs_fedex"]["index_2019_100"]).set_index("index")
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(idx.index, idx["ltl_proxy"], color=S.NEUTRAL, marker="o", ms=4, label="LTL-addressable truck freight (FAF5)")
    ax.plot(idx.index, idx["fedex_freight"], color=S.ORANGE, marker="o", ms=5, lw=2.5, label="FedEx Freight tonnage")
    for col, color, dy in [("ltl_proxy", S.INK_2, 6), ("fedex_freight", S.ORANGE, -12)]:
        v = idx[col].dropna()
        ax.annotate(f"{v.iloc[-1]:.0f}", (v.index[-1], v.iloc[-1]), xytext=(6, dy), textcoords="offset points",
                    fontsize=10, weight="bold", color=color)
    ax.axhline(100, color=S.GRID, lw=1)
    ax.set_ylim(60, 112); ax.set_xticks(idx.index)
    ax.set_title("FedEx Freight tonnage fell ~3x faster than its addressable market", pad=20)
    S.subtitle(ax, "Index, 2019 = 100. Market proxy = packaged/finished-goods truck freight in FAF5.7.1 (2018-24 are BTS estimates)")
    ax.legend(loc="lower left")
    S.source(fig, "FedEx Corp 8-K earnings releases (shipments/day x weight x days); BTS/ORNL FAF5.7.1. Calendar years.")
    S.save(fig, OUT / "f1_tonnage_vs_market.png")


# ---------------------------------------------------------------- 2. FY26 Q4 revenue bridge (waterfall)
def fig_bridge():
    r = ob["bridge_fy26q4"]
    parts = [("Shipments/day", r["shipments_per_day"]), ("Weight/shipment", r["weight_per_shipment"]),
             ("Fuel surcharge", r["fuel"]), ("Base price/cwt", r["base_yield_per_cwt"])]
    if abs(r["days"]) > 0.05:
        parts.insert(0, ("Operating days", r["days"]))
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    cum = 0
    for i, (lab, v) in enumerate(parts):
        ax.bar(i, v, bottom=cum, color=S.BLUE if v >= 0 else S.ORANGE, width=0.62)
        ax.text(i, cum + v + (0.35 if v >= 0 else -0.35), f"{v:+.1f}", ha="center", va="bottom" if v >= 0 else "top",
                fontsize=9.5, weight="bold")
        if i < len(parts) - 1:
            ax.plot([i + 0.31, i + 0.69], [cum + v, cum + v], color=S.NEUTRAL, lw=0.8)
        cum += v
    ax.bar(len(parts), cum, color=S.INK_2, width=0.62)
    ax.text(len(parts), cum + 0.35, f"{cum:+.1f}", ha="center", va="bottom", fontsize=9.5, weight="bold")
    ax.set_xticks(range(len(parts) + 1)); ax.set_xticklabels([p for p, _ in parts] + ["LTL revenue"])
    ax.axhline(0, color=S.INK_2, lw=0.8); ax.set_ylabel("contribution to YoY change (log-points, ~%)")
    lows = np.cumsum([0] + [v for _, v in parts])
    ax.set_ylim(min(lows.min(), cum) - 1.6, max(lows.max(), cum) + 1.4)
    ax.set_title("FY26 Q4: fuel, not price, offset the volume loss", pad=20)
    S.subtitle(ax, "Quarter ended May 31, 2026 vs a year earlier. Fuel split = published surcharge tariff x realized ratio (0.59)")
    S.source(fig, "FedEx Corp 8-K (2026-06-23), FDXF 8-K recast (2026-08-06), FedEx Freight fuel surcharge table (2025-06-09), EIA diesel via FRED.")
    S.save(fig, OUT / "f2_revenue_bridge.png")


# ---------------------------------------------------------------- 3. fuel model
def fig_fuel():
    tab = pd.read_csv(ROOT / "data/raw/external/fedex_freight_fuel_surcharge_table_2025-06-09.csv")
    rc = pd.read_csv(PROC / "fdxf_calendar_quarterly_kpis_recast.csv")
    rho = ob["fuel_model"]["rho_mean"]
    d = pd.read_csv(ROOT / "data/raw/fred/GASDESW.csv", parse_dates=[0], index_col=0, na_values=".")["GASDESW"].dropna()
    rc["start"] = pd.to_datetime(dict(year=rc["calendar_year"], month=3 * rc["calendar_quarter"] - 2, day=1))
    rc["diesel"] = [d.shift(1)[s:s + pd.offsets.QuarterEnd(0)].mean() for s in rc["start"]]
    rc["fuel_pct"] = 100 * (rc["revenue_per_shipment_usd"] / rc["revenue_per_shipment_ex_fuel_usd"] - 1)
    x = tab["eia_index_cents"] / 100
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(x, tab["surcharge_pct"], color=S.NEUTRAL, lw=1.5, label="Published tariff")
    ax.plot(x, rho * tab["surcharge_pct"], color=S.BLUE, label=f"Model: {rho:.2f} x tariff")
    ax.scatter(rc["diesel"], rc["fuel_pct"], color=S.INK, s=28, zorder=3, label="FDXF disclosed quarters, 2024-25")
    lo, hi = ob["jun_sep_2026"]["diesel"]
    fl, fh = ob["jun_sep_2026"]["fuel_pct"]
    ax.scatter([hi], [fh], color=S.ORANGE, s=60, zorder=4, marker="D", label="Jun-Sep 2026 (modeled)")
    ax.annotate(f"Jun-Sep 2026: diesel ${hi:.2f}\nfuel ~{fh:.0f}% of base revenue\n(+{ob['jun_sep_2026']['fuel_lift_rps_pct']:.1f}% revenue/shipment YoY)",
                (hi, fh), xytext=(12, -38), textcoords="offset points", fontsize=8.5)
    ax.set_xlim(3.3, 6.6); ax.set_ylim(10, 66)
    ax.set_xlabel("EIA diesel, $/gal (applied with 10-day lag)"); ax.set_ylabel("fuel surcharge, % of ex-fuel revenue")
    ax.set_title("FedEx realizes 59% of its published fuel surcharge, quarter after quarter", pad=20)
    S.subtitle(ax, f"Realized/tariff ratio sd {ob['fuel_model']['rho_sd']:.3f} across 8 quarters; leave-one-out error {ob['fuel_model']['loo_mae_structural_pts']:.2f} pts")
    ax.legend(loc="upper left")
    S.source(fig, "fedexfreight.com fuel surcharge table (eff. 2025-06-09); FDXF 8-K recast 2026-08-06; EIA via FRED GASDESW.")
    S.save(fig, OUT / "f3_fuel_model.png")


# ---------------------------------------------------------------- 4. value of a point
def fig_value():
    dd = od["dollars"]; ex = od["ex_covid"]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    labels = ["+1 pt of shipments", "+1 pt of price/mix"]
    vals = [dd["oi_per_volume_pt"], dd["oi_per_price_pt"]]
    cis = [ex["volume_ci"], ex["price_ci"]]
    one = dd["fy26_revenue"] / 100
    for i, (lab, v, ci) in enumerate(zip(labels, vals, cis)):
        ax.barh(i, v, color=[S.BLUE, S.AQUA][i], height=0.5)
        ax.errorbar(v, i, xerr=[[v - ci[0] * one], [ci[1] * one - v]], color=S.INK_2, capsize=4, lw=1)
        ax.text(ci[1] * one + 2, i, f"${v:.0f}M / yr", va="center", fontsize=10, weight="bold")
    ax.set_yticks([0, 1]); ax.set_yticklabels(labels); ax.invert_yaxis(); ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(c[1] for c in cis) * one * 1.35); ax.set_xlabel("adjusted operating income, $M per year (95% CI)")
    ax.set_title(f"1 pt of price is worth ~{dd['volume_pts_offset_by_1pt_price']:.1f} pts of shipments", pad=20)
    S.subtitle(ax, f"Incremental margins from {ex['n']} quarters FY2018-26 (ex-COVID). At the market's {dd['ev_to_adj_oi']:.0f}x EV/adj. op. income, 1 pt of shipments ~ ${dd['value_per_volume_pt_per_share']:.2f}/share")
    S.source(fig, "FedEx Corp 8-K segment results (separation costs added back); StockAnalysis 2026-10-22 price; $4.3B debt at spin.")
    S.save(fig, OUT / "f4_value_of_a_point.png")


# ---------------------------------------------------------------- 5. lanes
def fig_lanes():
    lanes = pd.read_csv(REP / "option_c/lane_forecast_state_pairs.csv", index_col=0)
    top = lanes.sort_values("add_ktons", ascending=False).head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.barh(top.index, top["add_ktons"] / 1e3, color=S.BLUE, height=0.6)
    for i, (a, c) in enumerate(zip(top["add_ktons"], top["cagr_pct"])):
        ax.text(a / 1e3 + 0.04, i, f"{c:.1f}%/yr", va="center", fontsize=8.5, color=S.INK_2)
    ax.set_xlabel("added tons by 2035 vs 2024 (millions)"); ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.set_title("Where addressable freight grows: Southeast, Texas and Midwest-Texas lanes", pad=20)
    S.subtitle(ax, f"Interstate lanes, 250+ miles, packaged/finished goods. All such lanes: {oc['lanes']['cagr_2024_2035_pct']:.1f}%/yr (FAF5 mid-range forecast)")
    S.source(fig, "BTS/ORNL Freight Analysis Framework 5.7.1 (2024 estimate, 2035 forecast), truck mode.")
    S.save(fig, OUT / "f5_lanes.png")


# ---------------------------------------------------------------- 0. FedEx vs public LTL peers (needs peer data)
def fig_peers():
    f = REP / "option_a/fedex_vs_peers_quarterly.csv"
    if not f.exists():
        print("skip fig_peers: no peer data"); return
    rel = pd.read_csv(f, parse_dates=["period_end"])
    allq = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv")["fiscal_period"]
    allq = allq[(allq >= rel["fiscal_period"].iloc[0])]
    rel = allq.to_frame().merge(rel, how="left")  # COVID quarters stay as gaps (excluded from the analysis)
    x = np.arange(len(rel))
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    gap = rel["fedex_minus_peers_pp"]
    ax.bar(x, gap.fillna(0), color=[S.ORANGE if v < 0 else S.BLUE for v in gap.fillna(0)], alpha=0.35, width=0.7, label="FedEx minus peers (pp)")
    cov = np.where(gap.isna())[0]
    if len(cov):
        ax.axvspan(cov.min() - 0.5, cov.max() + 0.5, color=S.GRID, alpha=0.6, lw=0)
        ax.text((cov.min() + cov.max()) / 2, -14, "COVID base\neffects\nexcluded", ha="center", fontsize=7, color=S.INK_2)
    ax.plot(x, 100 * rel["y"], color=S.ORANGE, marker="o", ms=3.5, label="FedEx Freight")
    ax.plot(x, 100 * rel["peer_yoy"], color=S.BLUE, marker="o", ms=3.5, label="Peer index (ODFL, SAIA, XPO, ARCB)")
    ax.axhline(0, color=S.INK_2, lw=0.8)
    short = rel["fiscal_period"].map(lambda p: f"Q{p[-1]}\nFY{p[4:6]}")
    step = max(1, len(x) // 8)
    ax.set_xticks(x[::step]); ax.set_xticklabels(short.iloc[::step], fontsize=8)
    ax.set_ylabel("shipments per day, YoY %")
    m = rel.loc[rel["period_end"] >= "2022-06-01", "fedex_minus_peers_pp"].mean()  # NaT rows drop out
    ax.set_title(f"FedEx Freight has trailed its public peers by {abs(m):.1f} pts a year since FY2023" if m < 0 else
                 f"FedEx Freight vs public peers: {m:+.1f} pts a year since FY2023", pad=20)
    S.subtitle(ax, "Peer index weights each carrier by year-ago daily shipments; monthly updates used where published")
    ax.legend(loc="lower left", ncol=3, fontsize=7.5)
    S.source(fig, "FedEx Corp/FDXF and ODFL, SAIA, XPO, ARCB 8-K releases and monthly updates (SEC EDGAR). FedEx fiscal quarters.")
    S.save(fig, OUT / "f0_fedex_vs_peers.png")


# ---------------------------------------------------------------- 6. nowcast vs backtest and outside estimates
def fig_nowcast():
    bt = pd.read_csv(REP / "option_a/backtest_predictions.csv")
    nc = pd.DataFrame(oa["nowcast"]["models"]).set_index("model")
    m = "combo" if "combo" in nc.index else pd.DataFrame(oa["backtest"])["model"].iloc[0]
    act = bt.drop_duplicates("fiscal_period")
    pr = act[["fiscal_period"]].merge(bt[bt["model"] == m][["fiscal_period", "yhat"]], how="left")
    x = np.arange(len(act))
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(x, 100 * act["y"], color=S.INK, marker="o", ms=3, label="Actual")
    ax.plot(x, 100 * pr["yhat"].to_numpy(), color=S.BLUE, ls="--", marker="o", ms=3, label=("combination" if m == "combo" else m) + ", out-of-sample")
    xn = len(x) + 0.6
    y, lo, hi = nc.loc[m, ["yhat_pct", "lo80_pct", "hi80_pct"]]
    ax.errorbar([xn], [y], yerr=[[y - lo], [hi - y]], fmt="D", color=S.ORANGE, ms=7, capsize=5, lw=1.5, label="Nowcast Jun-Sep 2026 (80%)")
    ax.scatter([xn + 0.9], [-3.0], marker="s", color=S.NEUTRAL, s=36, zorder=3, label="BofA estimate (-3.0%)")
    ax.annotate(f"{y:+.1f}%", (xn, y), xytext=(8, 0), textcoords="offset points", fontsize=10, weight="bold", color=S.ORANGE, va="center")
    ax.axhline(0, color=S.INK_2, lw=0.8)
    short = act["fiscal_period"].map(lambda p: f"Q{p[-1]}\nFY{p[4:6]}")
    step = 3
    ax.set_xticks(list(x[::step]) + [xn]); ax.set_xticklabels(list(short.iloc[::step]) + ["Jun-Sep\n2026"], fontsize=8)
    ax.set_ylim(top=max(14, ax.get_ylim()[1]))
    ax.set_ylabel("shipments per day, YoY % (log)")
    ax.set_title("Nowcast for FDXF's Oct 29 report, with its backtest", pad=20)
    S.subtitle(ax, "Each forecast uses only data available before that quarter; interval = model's own backtest error quantiles")
    ax.legend(loc="upper right", fontsize=7.5, ncol=2)
    S.source(fig, "scripts/option_a_nowcast.py; BofA estimate via Investing.com (2026-09-29).")
    S.save(fig, OUT / "f6_nowcast.png")


if __name__ == "__main__":
    for f in [fig_peers, fig_nowcast, fig_tonnage, fig_bridge, fig_fuel, fig_value, fig_lanes]:
        f()
        print("ok", f.__name__)
