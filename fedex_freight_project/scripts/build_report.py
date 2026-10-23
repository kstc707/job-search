"""Build the shareable report page (reports/site/index.html) from the analysis outputs.

Every number on the page is read from reports/option_*/ outputs or the processed CSVs at build time, so the
page cannot drift from the analysis. Charts are drawn client-side with Chart.js from an embedded JSON blob.
Run after all option_* scripts: .venv/bin/python -I scripts/build_report.py
"""
import html
import json
import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP, PROC, RAW = ROOT / "reports", ROOT / "data/processed", ROOT / "data/raw"
SITE = REP / "site"
SITE.mkdir(parents=True, exist_ok=True)

oa = json.loads((REP / "option_a/results.json").read_text())
ob = json.loads((REP / "option_b/results.json").read_text())
oc = json.loads((REP / "option_c/results.json").read_text())
od = json.loads((REP / "option_d/results.json").read_text())
k = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"])
HAS_PEERS = (REP / "option_a/fedex_vs_peers_quarterly.csv").exists()


def f1(x, signed=False):
    return f"{x:+.1f}" if signed else f"{x:.1f}"


def r(x, nd=0):
    return round(float(x), nd)


# ---------------------------------------------------------------- data for charts
D = {}
idx = pd.DataFrame(oc["proxy_vs_fedex"]["index_2019_100"]).set_index("index")
D["tonnage"] = {"years": [int(y) for y in idx.index], "market": [r(v, 1) for v in idx["ltl_proxy"]],
                "fedex": [None if pd.isna(v) else r(v, 1) for v in idx["fedex_freight"]]}

bt = pd.read_csv(REP / "option_a/backtest_predictions.csv", parse_dates=["period_end"])
scores = pd.DataFrame(oa["backtest"]).set_index("model")
best = scores.index[0]
act = bt.drop_duplicates("fiscal_period")[["fiscal_period", "y"]]
D["backtest"] = {"labels": act["fiscal_period"].tolist(), "actual": [r(100 * v, 1) for v in act["y"]],
                 "best": [r(100 * v, 1) if pd.notna(v) else None for v in bt[bt.model == best]["yhat"]],
                 "best_name": best}
nc = pd.DataFrame(oa["nowcast"]["models"]).set_index("model")
D["nowcast"] = {m: {"y": r(nc.loc[m, "yhat_pct"], 1), "lo": r(nc.loc[m, "lo80_pct"], 1), "hi": r(nc.loc[m, "hi80_pct"], 1),
                    "mae": r(nc.loc[m, "backtest_mae_pp"], 2)} for m in nc.index if pd.notna(nc.loc[m, "lo80_pct"])}

br = ob["bridge_fy26q4"]
D["bridge"] = [["Shipments/day", br["shipments_per_day"]], ["Weight/shipment", br["weight_per_shipment"]],
               ["Fuel surcharge", br["fuel"]], ["Base price/cwt", br["base_yield_per_cwt"]]]

tab = pd.read_csv(RAW / "external/fedex_freight_fuel_surcharge_table_2025-06-09.csv")
tab = tab[tab["eia_index_cents"] % 10 == 0]
rc = pd.read_csv(PROC / "fdxf_calendar_quarterly_kpis_recast.csv")
dsl = pd.read_csv(RAW / "fred/GASDESW.csv", parse_dates=[0], index_col=0, na_values=".")["GASDESW"].dropna().shift(1)
rc["start"] = pd.to_datetime(dict(year=rc["calendar_year"], month=3 * rc["calendar_quarter"] - 2, day=1))
rc["diesel"] = [dsl[s:s + pd.offsets.QuarterEnd(0)].mean() for s in rc["start"]]
rc["fuel_pct"] = 100 * (rc["revenue_per_shipment_usd"] / rc["revenue_per_shipment_ex_fuel_usd"] - 1)
rho = ob["fuel_model"]["rho_mean"]
D["fuel"] = {"tariff": [[r(c / 100, 2), r(p, 2)] for c, p in zip(tab["eia_index_cents"], tab["surcharge_pct"])],
             "model": [[r(c / 100, 2), r(rho * p, 2)] for c, p in zip(tab["eia_index_cents"], tab["surcharge_pct"])],
             "obs": [[r(d, 2), r(f, 2), p] for d, f, p in zip(rc["diesel"], rc["fuel_pct"], rc["period"])],
             "now": [ob["jun_sep_2026"]["diesel"][1], ob["jun_sep_2026"]["fuel_pct"][1]],
             "y27": [ob["fuel_2027"]["eia_2027_diesel"], ob["fuel_2027"]["eia_2027_fuel_pct"]]}

lanes = pd.read_csv(REP / "option_c/lane_forecast_state_pairs.csv", index_col=0).sort_values("add_ktons", ascending=False).head(12)
D["lanes"] = [[i.replace("->", " → "), r(a / 1e3, 2), r(c, 1)] for i, a, c in zip(lanes.index, lanes["add_ktons"], lanes["cagr_pct"])]
ss = pd.read_csv(REP / "option_c/shift_share_by_state.csv", index_col=0)
im = pd.read_csv(REP / "option_c/directional_imbalance_by_state.csv", index_col=0)
D["maps"] = {"shift": {s: r(v, 1) for s, v in ss["regional_pct"].items() if isinstance(s, str)},
             "imb": {s: r(v, 1) for s, v in im["net_pct"].items() if isinstance(s, str)}}

D["kpi"] = {"labels": k["fiscal_period"].tolist(), "ads": k["avg_daily_shipments_k"].tolist(),
            "wps": k["weight_per_shipment_lbs"].tolist()}

if HAS_PEERS:
    rel = pd.read_csv(REP / "option_a/fedex_vs_peers_quarterly.csv")
    D["peers"] = {"labels": rel["fiscal_period"].tolist(), "fedex": [r(100 * v, 1) for v in rel["y"]],
                  "peers": [r(100 * v, 1) for v in rel["peer_yoy"]], "gap": [r(v, 1) for v in rel["fedex_minus_peers_pp"]]}
    py = pd.read_csv(REP / "option_a/peer_index_monthly_yoy.csv", index_col=0, parse_dates=True).dropna()
    D["peer_recent"] = [[f"{d:%b %Y}", r(100 * v, 1), int(n)] for d, v, n in zip(py.index[-6:], py["peer_yoy"][-6:], py["n_tickers"][-6:])]

# ---------------------------------------------------------------- headline numbers
fx24 = D["tonnage"]["fedex"][-1]; mk24 = D["tonnage"]["market"][-1]
ncb = D["nowcast"].get("peer_ar") or D["nowcast"].get(best)
nc_name = "peer_ar" if "peer_ar" in D["nowcast"] else best
base = oa["nowcast"]["base_ads_k"]
dd = od["dollars"]
H = {
    "fedex_ton": f1(fx24 - 100, True), "mkt_ton": f1(mk24 - 100, True),
    "fedex_ton_abs": f1(abs(fx24 - 100)), "mkt_ton_abs": f1(abs(mk24 - 100)),
    "nat_abs": f1(abs(oc["shift_share"]["national_growth_pct"])),
    "nc": f1(ncb["y"], True), "nc_lo": f1(ncb["lo"], True), "nc_hi": f1(ncb["hi"], True),
    "nc_ads": f"{base * np.exp(ncb['y'] / 100):.1f}", "base_ads": f"{base:.1f}",
    "oi_vol": f"{dd['oi_per_volume_pt']:.0f}", "oi_price": f"{dd['oi_per_price_pt']:.0f}",
    "ratio": f"{dd['volume_pts_offset_by_1pt_price']:.1f}", "per_share": f"{dd['value_per_volume_pt_per_share']:.2f}",
    "mult": f"{dd['ev_to_adj_oi']:.0f}", "rho": f"{rho:.2f}", "rho_sd": f"{ob['fuel_model']['rho_sd']:.3f}",
    "fuel_lift": f1(ob["jun_sep_2026"]["fuel_lift_rps_pct"], True), "fuel27": f1(ob["fuel_2027"]["rps_change_vs_oct2026_pct"], True),
    "wadj": f1(ob["weight_adjusted_base_yield_yoy"]["FY2026Q4"], True),
    "beta": f"{ob['weight_elasticity']['preferred_beta']:.2f}",
    "beta_ci": f"{ob['weight_elasticity']['ci95'][0]:.2f} to {ob['weight_elasticity']['ci95'][1]:.2f}",
    "beta_naive": f"{ob['weight_elasticity']['naive_beta']:.2f}",
    "beta_pct10": f"{-10 * ob['weight_elasticity']['preferred_beta']:.1f}",
    "d_n": od["ex_covid"]["n"], "vol_c": f"{100 * od['ex_covid']['volume_margin']:.0f}",
    "vol_ci": f"{100 * od['ex_covid']['volume_ci'][0]:.0f} to {100 * od['ex_covid']['volume_ci'][1]:.0f}",
    "price_c": f"{100 * od['ex_covid']['price_margin']:.0f}",
    "price_ci": f"{100 * od['ex_covid']['price_ci'][0]:.0f} to {100 * od['ex_covid']['price_ci'][1]:.0f}",
    "oos": f1(ob["oos_fy26q4"]["structural"], True),
    "lane_cagr": f"{oc['lanes']['cagr_2024_2035_pct']:.1f}",
    "nat": f1(oc["shift_share"]["national_growth_pct"], True),
    "tn_net": f1(oc["imbalance"]["TN"]["net_pct"], True),
    "best": best, "best_mae": f"{scores.loc[best, 'mae_pp']:.1f}",
    "naive_mae": f"{scores.loc['naive_last', 'mae_pp']:.1f}", "macro_mae": f"{scores.loc['macro3_ar', 'mae_pp']:.1f}",
    "n_test": int(scores.loc[best, "n"]),
}
if HAS_PEERS:
    H["rel_mean"] = f1(oa["relative_vs_peers"]["mean_since_fy23_pp"], True)
    last4 = list(oa["relative_vs_peers"]["by_quarter_pp"].values())[-4:]
    H["rel_last4"] = ", ".join(f1(v, True) for v in last4)
    for m in ["peer_ar", "peer", "peer_macro_ar"]:  # noqa
        if m in scores.index:
            H[m + "_mae"] = f"{scores.loc[m, 'mae_pp']:.1f}"

if not HAS_PEERS:
    H["rel_mean"] = H["rel_last4"] = "n/a"

score_rows = "".join(
    f"<tr{' class=\"win\"' if m == best else ''}><td>{html.escape(m)}</td><td>{int(s['n'])}</td><td>{s['mae_pp']:.1f}</td>"
    f"<td>{s['rmse_pp']:.1f}</td><td>{s['bias_pp']:+.1f}</td><td>{100 * s['direction_hit']:.0f}%</td></tr>"
    for m, s in scores.iterrows())
MODEL_DESC = {"naive_last": "last quarter's YoY carried forward", "mean4": "average of the last four quarters",
              "ar1": "regression on last quarter's YoY", "macro3": "manufacturing output, truck tonnage, Cass shipments",
              "macro3_ar": "macro3 plus last quarter", "ridge_all": "ridge on 14 macro series plus last quarter",
              "peer": "public LTL peers' shipments/day, same months", "peer_ar": "peers plus last quarter",
              "peer_macro_ar": "peers, macro, last quarter"}
nowcast_rows = "".join(
    f"<tr{' class=\"win\"' if m == nc_name else ''}><td>{html.escape(m)}</td><td>{html.escape(MODEL_DESC.get(m, ''))}</td>"
    f"<td>{v['y']:+.1f}%</td><td>{v['lo']:+.1f}% to {v['hi']:+.1f}%</td><td>{v['mae']:.1f}</td></tr>"
    for m, v in sorted(D["nowcast"].items(), key=lambda kv: kv[1]["mae"]))

TEMPLATE = (ROOT / "scripts/report_template.html").read_text()
page = TEMPLATE.replace("/*__DATA__*/{}", json.dumps(D, separators=(",", ":")))
for key, val in H.items():
    page = page.replace("{{" + key + "}}", html.escape(str(val)))
page = page.replace("{{score_rows}}", score_rows).replace("{{nowcast_rows}}", nowcast_rows)
page = page.replace("{{peers_display}}", "" if HAS_PEERS else "hidden")
leftover = sorted(set(__import__("re").findall(r"\{\{(\w+)\}\}", page)))
if leftover:
    raise SystemExit(f"unfilled placeholders: {leftover}")
(SITE / "index.html").write_text(page)
(SITE / "headline.json").write_text(json.dumps(H, indent=2))
print("written", SITE / "index.html", f"{len(page) / 1024:.0f} KB", "peers:", HAS_PEERS)
