"""Build the one-page overview PDF for hiring managers (reports/overview/) from reports/site/headline.json.
Shorter than the two-page brief: the question, three findings, the locked forecast, what I'd build, links.
Printed to PDF with the pre-installed headless Chromium. Run after build_report.py:
.venv/bin/python -I scripts/build_overview.py
"""
import base64
import html
import json
import pathlib
import subprocess

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = REP / "overview"
OUT.mkdir(parents=True, exist_ok=True)
H = json.loads((REP / "site/headline.json").read_text())
CHROME = "/opt/pw-browsers/chromium"


def img(rel):
    return f'<img src="data:image/png;base64,{base64.b64encode((REP / rel).read_bytes()).decode()}" alt="">'


def e(k):
    v = str(H[k])
    return html.escape("−" + v[1:] if v.startswith("-") else v)


def pct(x):
    return f"{x:+.1f}%".replace("-", "−")


pf = pd.read_csv(ROOT / "ds/prospective_forecasts.csv")
pre = pf[pf["pre_registered_best"]].set_index(["ticker", "period"])
fdx = pre.loc[("FDX", "Jun-Sep 2026 (FDXF transition period)")]
peers = " · ".join(f"{t} {pct(pre.loc[(t, '2026Q3'), 'yoy_log_pct'])}" for t in ["ODFL", "SAIA", "XPO", "ARCB"])

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Market or Share? FedEx Freight overview</title>
<style>
@page {{ size: Letter; margin: 0.45in 0.55in; }}
body {{ font: 9.6pt/1.42 "DejaVu Serif", Georgia, serif; color: #14202b; margin: 0; }}
h1 {{ font: 800 22pt/1.05 "DejaVu Sans Condensed", "DejaVu Sans", Arial, sans-serif; margin: 0 0 3pt; }}
h2 {{ font: 700 10.5pt/1.2 "DejaVu Sans Condensed", "DejaVu Sans", sans-serif; margin: 10pt 0 4pt; border-top: 1pt solid #14202b; padding-top: 4pt; }}
.meta {{ white-space: nowrap; font: 7.2pt/1.4 "DejaVu Sans Mono", monospace; color: #4c5864; display: flex; justify-content: space-between; gap: 10pt;
        border: 1pt solid #14202b; padding: 4pt 6pt; margin-bottom: 8pt; }}
.lede {{ font-size: 10.4pt; margin: 4pt 0 0; }}
.two {{ display: grid; grid-template-columns: 1.08fr 1fr; gap: 12pt; align-items: start; }}
img {{ width: 100%; display: block; }}
ol {{ margin: 0; padding-left: 13pt; }} li {{ margin: 0 0 5pt; }}
.neg {{ color: #c4501f; white-space: nowrap; }}
.lock {{ display: flex; gap: 14pt; align-items: center; border-top: 2pt solid #14202b; border-bottom: 0.6pt solid #d6dbd9; padding: 6pt 0; margin-top: 2pt; }}
.lock b {{ font: 800 30pt/1 "DejaVu Sans Condensed", sans-serif; color: #c4501f; white-space: nowrap; }}
.small {{ font: 7pt/1.45 "DejaVu Sans Mono", monospace; color: #4c5864; }}
table {{ border-collapse: collapse; width: 100%; font: 8.4pt/1.38 "DejaVu Sans", sans-serif; }}
td {{ border-top: 0.6pt solid #d6dbd9; padding: 3pt 8pt 3pt 0; vertical-align: top; }}
td:first-child {{ font-weight: 700; white-space: nowrap; color: #2a78d6; }}
</style></head><body>
<div class="meta"><span>Sai Teja Koppolu · MS Data Science, University of Memphis · skppolu1@memphis.edu · +1 901-343-7273</span><span>Oct 23, 2026</span></div>
<h1>Market or share? What explains FedEx Freight's lost volume</h1>
<p class="lede">FedEx Freight's share of daily shipments among the five largest public LTL carriers fell <b class="neg">{e('share_total')} log-%</b>
from mid-2021 to mid-2026. I asked how much of that is price, using only public SEC filings and a method written down before any model was fitted.</p>

<h2>Three findings</h2>
<div class="two"><div>{img('ds/figures/ds6_share_annual.png')}</div><div><ol>
<li><b>Price explains {e('share_price')} of the {e('share_total')} log-points.</b> I estimated share's response to relative price on the four competitors only
(elasticity −{e('elas_b0')}; placebo p = {e('placebo_p')}) and applied it to FedEx out of sample. It accounts for the 2022–23 loss, when FedEx raised relative price ~{e('rel_2023')}%.</li>
<li><b class="neg">{e('share_nonprice')} is not price.</b> FedEx lost share in the year after Yellow's shutdown and in the year to mid-2026 while its relative price was
<i>falling</i>. That points to account retention (bundle unwinding, the spin-off), not pricing.</li>
<li><b>Simple beats fancy here.</b> Over {e('n_test')} out-of-sample carrier-quarters, a carrier's own in-quarter data cut error {e('own_gain')}% vs naive
(p = {e('own_p')}); machine learning added {e('ml_gain')}%, not significant. The value of FedEx's daily data is at the account level.</li>
</ol></div></div>

<h2>A forecast locked before the answer exists</h2>
<div class="lock"><b>{pct(fdx['yoy_log_pct'])}</b><div>FedEx Freight shipments per day, June–September 2026 vs 2025 (80% range {pct(fdx['lo80'])} to {pct(fdx['hi80'])}).
FedEx Freight reports October 29. For comparison, BofA's estimate is −3.0%.
<div class="small">Peers, Q3 2026: {peers}. Forecast file SHA-256 {e('lock_hash')} committed in {e('lock_commit')} before any of them report.</div></div></div>

<h2>What I would build first with FedEx Freight's data</h2>
<table>
<tr><td>Retention</td><td>Account-level share early warning: expected weekly shipments per account, drift flagged before churn, ranked by volume at risk. One point of shipments ≈ ${e('oi_vol')}M operating income a year.</td></tr>
<tr><td>Pricing</td><td>Price response by lane, shipment size and commodity; the {e('ratio')}:1 price-to-volume exchange rate as a guardrail.</td></tr>
<tr><td>Fuel</td><td>FedEx realizes {e('rho')}× its published fuel surcharge; at EIA's 2027 diesel forecast, fuel alone takes {e('fuel27_abs')}% off revenue per shipment.</td></tr>
</table>

<h2>More detail</h2>
<p class="small">2-minute video: Koppolu_FedEx_Freight_overview.mp4 · Two-page brief: Koppolu_FedEx_Freight_Market_or_Share.pdf ·
Code, pre-registration, model card and {e('n_tests')} automated tests: github.com/kstc707/job-search (fedex_freight_project).<br>
Sources: SEC EDGAR (FedEx, FDXF, ODFL, SAIA, XPO, ARCB), FRED, BTS/ORNL FAF5.7.1, EIA, fedexfreight.com fuel table. Charts generated in Python.
Limits: 90 test carrier-quarters; five public carriers are a sample of LTL; no FedEx internal data. Independent work, not affiliated with FedEx, not investment advice.</p>
</body></html>"""
src = OUT / "overview.html"
src.write_text(doc)
pdf = OUT / "Koppolu_FedEx_Freight_overview.pdf"
subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True, timeout=120)
print("written", pdf, f"{pdf.stat().st_size / 1024:.0f} KB")
