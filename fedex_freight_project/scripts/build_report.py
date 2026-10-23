"""Build the shareable report page (reports/site/index.html) from the analysis outputs.

Every number is read from the results files at build time and every chart is a Python (matplotlib) figure from
reports/, embedded as a data URI. Run after the analysis scripts: .venv/bin/python -I scripts/build_report.py
"""
import base64
import html
import json
import pathlib
import re
import subprocess

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP, PROC, DS = ROOT / "reports", ROOT / "data/processed", ROOT / "ds"
SITE = REP / "site"
SITE.mkdir(parents=True, exist_ok=True)
load = lambda p: json.loads((REP / p).read_text())  # noqa: E731
ob, oc, od = load("option_b/results.json"), load("option_c/results.json"), load("option_d/results.json")
nr, sr = load("ds/nowcast_results.json"), load("ds/share_results.json")
post = load("ds/posthoc_results.json")


def f1(x, signed=False):
    return f"{x:+.1f}" if signed else f"{x:.1f}"


def img(path):
    return "data:image/png;base64," + base64.b64encode((REP / path).read_bytes()).decode()


# ---------------------------------------------------------------- locked forecasts
pf = pd.read_csv(DS / "prospective_forecasts.csv")
lock_hash = (DS / "prospective_forecasts.sha256").read_text().split()[0]
try:
    lock_commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", str(DS / "prospective_forecasts.csv")],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip() or "uncommitted"
except (subprocess.CalledProcessError, FileNotFoundError):
    lock_commit = "uncommitted"
pre = pf[pf["pre_registered_best"]].set_index(["ticker", "period"])
ens = pf[pf["model"] == "ensemble"].set_index(["ticker", "period"])
order = [("FDX", "Jun-Sep 2026 (FDXF transition period)"), ("FDX", "FY2027Q1"), ("ODFL", "2026Q3"),
         ("SAIA", "2026Q3"), ("XPO", "2026Q3"), ("ARCB", "2026Q3")]
label = {"FY2027Q1": "Jun-Aug 2026", "Jun-Sep 2026 (FDXF transition period)": "Jun-Sep 2026 (reported Oct 29)"}
rows = ""
for key in order:
    r, e = pre.loc[key], ens.loc[key]
    rows += (f"<tr{' class=\"win\"' if key[1].startswith('Jun-Sep') else ''}><td>{key[0]}</td><td>{html.escape(label.get(key[1], key[1]))}</td>"
             f"<td>{r['yoy_log_pct']:+.1f}%</td><td>{r['lo80']:+.1f}% to {r['hi80']:+.1f}%</td><td>{e['yoy_log_pct']:+.1f}%</td>"
             f"<td>{int(r['own_monthly_months_used'])}</td></tr>")
fdx_nc = pre.loc[("FDX", "Jun-Sep 2026 (FDXF transition period)"), "yoy_log_pct"]

# ---------------------------------------------------------------- headline numbers
ann = {a["cq"]: a for a in sr["annual_q2"]}
tot = sr["anchor_robustness"]["Q2"]
prim = sr["elasticity_specs"]["primary: peers, carrier FE, +lag"]
m = nr["metrics_all"]
idx = pd.DataFrame(oc["proxy_vs_fedex"]["index_2019_100"]).set_index("index")
dd = od["dollars"]
n_tests = None
try:
    out = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "tests"], cwd=ROOT, capture_output=True, text=True)
    n_tests = re.search(r"(\d+) passed", out.stdout).group(1)
except Exception:  # noqa: BLE001
    n_tests = "all"
H = {
    "lock_commit": lock_commit, "lock_hash": lock_hash[:12] + "…", "lock_hash_full": lock_hash,
    "share_total": f1(tot["actual"], True), "share_price": f1(tot["explained"], True), "share_nonprice": f1(tot["unexplained"], True),
    "fdx_nc": f1(fdx_nc, True),
    "elas_b0": f"{abs(prim['b0']):.2f}", "elas_lr": f"{abs(prim['long_run']):.2f}",
    "elas_ci": f"{prim['b0_ci'][0]:.2f} to {prim['b0_ci'][1]:.2f}", "placebo_p": f"{sr['placebo']['p_value']:.3f}",
    "rel_2023": f"{ann['2023Q2']['d4_rel']:.0f}", "np_2024": f1(ann["2024Q2"]["unexplained"], True),
    "np_2026": f1(ann["2026Q2"]["unexplained"], True),
    "fedex_ton": f1(idx["fedex_freight"].iloc[-1] - 100, True), "mkt_ton": f1(idx["ltl_proxy"].iloc[-1] - 100, True),
    "n_dates": nr["diebold_mariano"]["own_monthly_vs_naive"]["T"], "n_test": int(m["naive"]["n"]),
    "own_gain": f"{100 * (1 - m['own_monthly']['mase']):.0f}", "own_p": f"{nr['diebold_mariano']['own_monthly_vs_naive']['p']:.3f}",
    "ml_gain": f"{100 * (1 - m['ridge']['mase']):.0f} to {100 * (1 - m['ensemble']['mase']):.0f}",
    "ens_p": f"{nr['diebold_mariano']['ensemble_vs_naive']['p']:.2f}",
    "rho": f"{ob['fuel_model']['rho_mean']:.2f}", "rho_sd": f"{ob['fuel_model']['rho_sd']:.3f}",
    "oos": f1(ob["oos_fy26q4"]["structural"], True), "loo": f"{ob['fuel_model']['loo_mae_structural_pts']:.2f}",
    "wadj_lo": f1(ob["peer_check"]["fy26q4_weight_adj_range"][0], True), "wadj_hi": f1(ob["peer_check"]["fy26q4_weight_adj_range"][1], True),
    "fuel27": f1(ob["fuel_2027"]["rps_change_vs_oct2026_pct"], True),
    "fuel27_abs": f1(abs(ob["fuel_2027"]["rps_change_vs_oct2026_pct"])),
    "d_n": od["ex_covid"]["n"], "vol_c": f"{100 * od['ex_covid']['volume_margin']:.0f}", "price_c": f"{100 * od['ex_covid']['price_margin']:.0f}",
    "oi_vol": f"{dd['oi_per_volume_pt']:.0f}", "per_share": f"{dd['value_per_volume_pt_per_share']:.2f}", "mult": f"{dd['ev_to_adj_oi']:.0f}",
    "ratio": f"{dd['volume_pts_offset_by_1pt_price']:.1f}",
    "lane_cagr": f"{oc['lanes']['cagr_2024_2035_pct']:.1f}", "tn_net": f1(oc["imbalance"]["TN"]["net_pct"], True),
    "n_tests": n_tests,
}
IMG = {"img_ds6": "ds/figures/ds6_share_annual.png", "img_f0": "figures_final/f0_fedex_vs_peers.png",
       "img_f1": "figures_final/f1_tonnage_vs_market.png", "img_ds1": "ds/figures/ds1_model_mae.png",
       "img_ds3": "ds/figures/ds3_ablation.png", "img_f2": "figures_final/f2_revenue_bridge.png",
       "img_f3": "figures_final/f3_fuel_model.png", "img_f4": "figures_final/f4_value_of_a_point.png",
       "img_f5": "figures_final/f5_lanes.png", "img_c4": "option_c/figures/c4_imbalance_map.png"}

page = (ROOT / "scripts/report_template.html").read_text()
for k, v in H.items():
    page = page.replace("{{" + k + "}}", html.escape(str(v)))
for k, v in IMG.items():
    page = page.replace("{{" + k + "}}", img(v))
page = page.replace("{{prospective_rows}}", rows)
left = sorted(set(re.findall(r"\{\{(\w+)\}\}", page)))
if left:
    raise SystemExit(f"unfilled placeholders: {left}")
(SITE / "index.html").write_text(page)
(SITE / "headline.json").write_text(json.dumps(H, indent=2))
print("written", SITE / "index.html", f"{len(page) / 1e6:.1f} MB")
