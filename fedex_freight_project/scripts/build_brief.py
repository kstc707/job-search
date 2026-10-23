"""Build the two-page PDF brief (reports/brief/) from reports/site/headline.json and the Python figures.
The HTML is printed to PDF with the pre-installed headless Chromium.
Run after build_report.py: .venv/bin/python -I scripts/build_brief.py
"""
import base64
import html
import json
import pathlib
import subprocess

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = REP / "brief"
OUT.mkdir(parents=True, exist_ok=True)
H = json.loads((REP / "site/headline.json").read_text())
CHROME = "/opt/pw-browsers/chromium"


def img(rel):
    return f'<img src="data:image/png;base64,{base64.b64encode((REP / rel).read_bytes()).decode()}" alt="">'


def e(k):
    return html.escape(str(H[k]))


pf = pd.read_csv(ROOT / "ds/prospective_forecasts.csv")
pre = pf[pf["pre_registered_best"]].set_index(["ticker", "period"])
ens = pf[pf["model"] == "ensemble"].set_index(["ticker", "period"])
order = [("FDX", "Jun-Sep 2026 (FDXF transition period)", "FDX Jun-Sep 2026"), ("ODFL", "2026Q3", "ODFL Q3 2026"),
         ("SAIA", "2026Q3", "SAIA Q3 2026"), ("XPO", "2026Q3", "XPO Q3 2026"), ("ARCB", "2026Q3", "ARCB Q3 2026")]
rows = "".join(f"<tr><td>{lab}</td><td>{pre.loc[(t, p), 'yoy_log_pct']:+.1f}%</td>"
               f"<td>{pre.loc[(t, p), 'lo80']:+.1f} to {pre.loc[(t, p), 'hi80']:+.1f}</td><td>{ens.loc[(t, p), 'yoy_log_pct']:+.1f}%</td></tr>"
               for t, p, lab in order)

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Market or Share? FedEx Freight brief</title>
<style>
@page {{ size: Letter; margin: 0.42in 0.5in; }}
body {{ font: 9.2pt/1.38 "DejaVu Serif", Georgia, serif; color: #14202b; margin: 0; }}
h1 {{ font: 800 21pt/1.05 "DejaVu Sans Condensed", "DejaVu Sans", Arial, sans-serif; margin: 0 0 2pt; }}
h2 {{ font: 700 11pt/1.2 "DejaVu Sans Condensed", "DejaVu Sans", sans-serif; margin: 9pt 0 3pt; border-top: 1pt solid #14202b; padding-top: 4pt; }}
.meta {{ font: 7.4pt/1.4 "DejaVu Sans Mono", monospace; color: #4c5864; display: flex; justify-content: space-between; gap: 10pt;
        border: 1pt solid #14202b; padding: 4pt 6pt; margin-bottom: 7pt; }}
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); border-top: 2pt solid #14202b; border-bottom: 0.6pt solid #d6dbd9; margin: 6pt 0; }}
.stat {{ padding: 4pt 6pt 5pt 0; }} .stat + .stat {{ border-left: 0.6pt solid #d6dbd9; padding-left: 6pt; }}
.stat b {{ display: block; font: 800 16pt/1 "DejaVu Sans Condensed", sans-serif; }}
.stat span {{ font-size: 7.4pt; color: #4c5864; line-height: 1.3; display: block; margin-top: 2pt; }}
.neg {{ color: #c4501f; }}
ul {{ margin: 2pt 0; padding-left: 12pt; }} li {{ margin: 2pt 0; }}
img {{ width: 100%; display: block; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 9pt; align-items: start; }}
.small {{ font: 6.9pt/1.4 "DejaVu Sans Mono", monospace; color: #4c5864; }}
.pb {{ break-before: page; }}
table {{ border-collapse: collapse; width: 100%; font: 7.8pt/1.35 "DejaVu Sans", sans-serif; }}
td, th {{ border-top: 0.6pt solid #d6dbd9; padding: 2.5pt 6pt 2.5pt 0; text-align: left; vertical-align: top; }}
th {{ font-weight: 400; color: #4c5864; font-size: 7pt; }}
table.build td:first-child {{ font-weight: 700; white-space: nowrap; }}
</style></head><body>
<div class="meta"><span>Sai Teja Koppolu · MS Data Science, University of Memphis · skppolu1@memphis.edu · +1 901-343-7273</span><span>Data as of Oct 23, 2026 · public data only</span></div>
<h1>Market or share? What explains FedEx Freight's lost volume</h1>
<p>FedEx Freight has lost about a sixth of its share of the five largest public LTL carriers' shipments since mid-2021.
I estimated how shipment share responds to relative price using its four public competitors only, applied it to FedEx out of sample,
and locked forecasts of every carrier's next quarter before any of them report. Methods were pre-registered (committed before fitting).</p>
<div class="stats">
 <div class="stat"><b class="neg">{e('share_total')}</b><span>FedEx share of 5-carrier shipments, mid-2021 to mid-2026 (log-%)</span></div>
 <div class="stat"><b>{e('share_price')}</b><span>explained by FedEx's relative price</span></div>
 <div class="stat"><b class="neg">{e('share_nonprice')}</b><span>not price: the Yellow year and the spin-off year</span></div>
 <div class="stat"><b>{e('fdx_nc')}%</b><span>locked forecast, FedEx shipments/day Jun-Sep 2026 (reports Oct 29)</span></div>
</div>
<h2>1. How much of the share loss is price?</h2>
<div class="two"><div>{img('ds/figures/ds6_share_annual.png')}</div><div>
<ul>
<li><b>Share-price elasticity {e('elas_b0')}</b> within the year, {e('elas_lr')} with one lag (peers only, carrier fixed effects; 95% CI {e('elas_ci')}).
Placebo with prices shuffled within carrier: p = {e('placebo_p')}. Robust to ex-fuel prices and quarter fixed effects; leave-one-carrier-out beats no-change for 3 of 4.</li>
<li><b>2022-23:</b> FedEx raised relative price ~{e('rel_2023')}%; price explains essentially all of that year's share loss (yield-first).</li>
<li><b>2023-24 and 2025-26:</b> share fell {e('np_2024')} and {e('np_2026')} log-points beyond price, while FedEx's relative price was falling.
Peers absorbed Yellow's customers; then the spin-off and bundle unwinding. These are retention questions.</li>
</ul></div></div>
<h2>2. Forecasts made before the answers exist</h2>
<div class="two"><div>{img('ds/figures/ds1_model_mae.png')}</div><div>
<table><tr><th>Carrier</th><th>Pre-registered</th><th>80% interval</th><th>ML ensemble</th></tr>{rows}</table>
<p class="small" style="margin-top:3pt">SHA-256 {e('lock_hash')} in commit {e('lock_commit')}. BofA's estimate for FedEx's Sept quarter: -3.0%.</p>
<ul>
<li>{e('n_test')} carrier-quarters, {e('n_dates')} issue dates, rolling origin, nested tuning, features gated by EDGAR filing dates.</li>
<li>Own intra-quarter data cuts error {e('own_gain')}% vs naive (Diebold-Mariano p = {e('own_p')}). ML improves {e('ml_gain')}%, <b>not significant</b> (p = {e('ens_p')}).
For FedEx alone nothing beats naive, so with FedEx's daily data the value is in longer horizons and account-level share.</li>
</ul></div></div>
<div class="pb"></div>
<h2>3. Is pricing holding, or is it fuel?</h2>
<div class="two"><div>{img('figures_final/f2_revenue_bridge.png')}</div><div>{img('figures_final/f3_fuel_model.png')}</div></div>
<ul><li>FedEx collects <b>{e('rho')}x</b> its published fuel surcharge (sd {e('rho_sd')}, 8 quarters). FY26 Q4 base revenue/cwt {e('oos')}% (management: "slight decline");
weight-adjusted price {e('wadj_lo')}% to {e('wadj_hi')}%. At EIA's 2027 diesel, fuel alone takes {e('fuel27_abs')}% off revenue per shipment.</li></ul>
<h2>4. What a point is worth, and where freight grows</h2>
<div class="two"><div>{img('figures_final/f4_value_of_a_point.png')}</div><div>{img('figures_final/f5_lanes.png')}</div></div>
<p>Revenue from volume adds {e('vol_c')}¢ of operating income per dollar, price/mix {e('price_c')}¢ ({e('d_n')} quarters). One point of shipments is about ${e('oi_vol')}M a year,
~${e('per_share')} a share at ~{e('mult')}x. LTL-type freight on 250+ mile interstate lanes grows {e('lane_cagr')}%/yr to 2035 in FAF5.</p>
<h2>5. What I would build with FedEx Freight's data</h2>
<table class="build">
<tr><td>Retention</td><td>Account-level share early warning: expected weekly shipments per account, drift flags ranked by volume at risk, starting with formerly bundled accounts. Evaluated the same way: pre-registered, rolling-origin, vs naive.</td></tr>
<tr><td>Pricing</td><td>Segment-level price response (lane, size, commodity) from renewals and GRIs; the {e('ratio')}:1 price-volume exchange rate as guardrail.</td></tr>
<tr><td>Revenue integrity</td><td>Predicted shipment density vs dimensioner reads under density-based NMFC classes; inspect the largest expected differences first.</td></tr>
<tr><td>Fuel</td><td>Realized-to-tariff fuel ratio by contract, ahead of falling diesel.</td></tr>
</table>
<p class="small" style="margin-top:6pt">Tested: pre-registration and deviations log in ds/; point-in-time features; no-look-ahead tests; Diebold-Mariano (HLN); block bootstrap; conformal intervals
with measured coverage; placebo and leave-one-carrier-out checks; {e('n_tests')} automated tests. Negative results reported. Sources: SEC EDGAR (FedEx, FDXF, ODFL, SAIA, XPO, ARCB),
FRED, BTS/ORNL FAF5.7.1, EIA, fedexfreight.com fuel table. All charts generated in Python. Code: github.com/kstc707/job-search. Independent work; not affiliated with FedEx; not investment advice.</p>
</body></html>"""
src = OUT / "brief.html"
src.write_text(doc)
pdf = OUT / "Koppolu_FedEx_Freight_Market_or_Share.pdf"
subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True, timeout=120)
print("written", pdf, f"{pdf.stat().st_size / 1024:.0f} KB")
