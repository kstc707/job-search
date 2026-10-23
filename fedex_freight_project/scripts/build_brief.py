"""Build the two-page PDF brief (reports/brief/) for the email attachment.

Numbers come from reports/site/headline.json (written by build_report.py) and figures from
reports/figures_final/, so the brief, the web page and the email all quote identical values.
The HTML is printed to PDF with the pre-installed headless Chromium.
Run after build_report.py and make_report_figures.py: .venv/bin/python -I scripts/build_brief.py
"""
import base64
import html
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = REP / "brief"
OUT.mkdir(parents=True, exist_ok=True)
H = json.loads((REP / "site/headline.json").read_text())
FIG = REP / "figures_final"
CHROME = "/opt/pw-browsers/chromium"


def img(name):
    b = base64.b64encode((FIG / name).read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b}" alt="">'


def e(k):
    return html.escape(str(H[k]))


has_peers = "rel_mean" in H
peer_line = (f"<li><b>FedEx Freight's shipments per day have run {e('rel_mean_abs')} points a year behind its four public LTL peers</b> "
             f"since FY2023 (last four quarters: {e('rel_last4')} points). The peer index was flat ({e('peer_junsep')}%) over Jun-Aug 2026.</li>"
             f"<li><b>Price doesn't explain it.</b> Weight-adjusted, FedEx's price rose {e('wadj_lo')}% to {e('wadj_hi')}% vs Old Dominion "
             f"{e('odfl_adj')}% and XPO {e('xpo_adj')}%, and XPO still grew shipments. That points to sales coverage, bundle unwinding and service.</li>") if has_peers else ""
peer_fig = img("f0_fedex_vs_peers.png") if (FIG / "f0_fedex_vs_peers.png").exists() else img("f1_tonnage_vs_market.png")
second_fig = img("f1_tonnage_vs_market.png") if (FIG / "f0_fedex_vs_peers.png").exists() else ""
peer_bt = ((f" Same-month peer data didn't beat it either ({e('peer_ar_mae')} pp): FedEx's volume follows its own trajectory, "
            f"which is what a share problem looks like. The headline is a combination fixed in advance (persistence + peers + macro); "
            f"backtest MAE {e('combo_mae')} pp, best of the set.") if "peer_ar_mae" in H else "")
nowcast_fig = img("f6_nowcast.png") if (FIG / "f6_nowcast.png").exists() else ""

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Market or Share? FedEx Freight brief</title>
<style>
@page {{ size: Letter; margin: 0.42in 0.5in; }}
body {{ font: 9.2pt/1.38 "DejaVu Serif", Georgia, serif; color: #14202b; margin: 0; }}
h1 {{ font: 800 22pt/1.05 "DejaVu Sans Condensed", "DejaVu Sans", Arial, sans-serif; margin: 0 0 2pt; letter-spacing: -0.2pt; }}
h2 {{ font: 700 11.5pt/1.2 "DejaVu Sans Condensed", "DejaVu Sans", sans-serif; margin: 10pt 0 3pt; border-top: 1pt solid #14202b; padding-top: 5pt; }}
.meta {{ font: 7.6pt/1.4 "DejaVu Sans Mono", monospace; color: #4c5864; display: flex; justify-content: space-between; gap: 10pt;
        border: 1pt solid #14202b; padding: 4pt 6pt; margin-bottom: 8pt; }}
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); border-top: 2pt solid #14202b; border-bottom: 0.6pt solid #d6dbd9; margin: 6pt 0; }}
.stat {{ padding: 5pt 6pt 6pt 0; }} .stat + .stat {{ border-left: 0.6pt solid #d6dbd9; padding-left: 6pt; }}
.stat b {{ display: block; font: 800 17pt/1 "DejaVu Sans Condensed", sans-serif; }}
.stat span {{ font-size: 7.6pt; color: #4c5864; line-height: 1.3; display: block; margin-top: 2pt; }}
.neg {{ color: #c4501f; }} .pos {{ color: #2a78d6; }}
ul {{ margin: 3pt 0; padding-left: 12pt; }} li {{ margin: 2pt 0; }}
img {{ width: 100%; display: block; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10pt; }}
.call {{ border-left: 2.5pt solid #2a78d6; padding: 3pt 0 3pt 8pt; margin: 6pt 0; }}
.small {{ font: 7pt/1.4 "DejaVu Sans Mono", monospace; color: #4c5864; }}
.pb {{ break-before: page; }}
table {{ border-collapse: collapse; width: 100%; font: 7.8pt/1.35 "DejaVu Sans", sans-serif; }}
td {{ border-top: 0.6pt solid #d6dbd9; padding: 3pt 6pt 3pt 0; vertical-align: top; }}
td:first-child {{ font-weight: 700; white-space: nowrap; }}
</style></head><body>
<div class="meta"><span>Sai Teja Koppolu · MS Data Science, University of Memphis · skppolu1@memphis.edu · +1 901-343-7273</span><span>Data as of Oct 23, 2026 · public data only</span></div>
<h1>Market or share? FedEx Freight's volume, yield and lanes from public data</h1>
<p>FedEx Freight's daily shipments are down a quarter from their 2021 peak. Using SEC filings (FedEx, FDXF and four public LTL peers),
FRED, the federal Freight Analysis Framework and FedEx Freight's published fuel tariff, I separated the freight market from FedEx-specific
volume, priced the yield-versus-volume trade-off, and nowcast the Jun-Sep 2026 period FDXF reports on Oct 29.</p>
<div class="stats">
 <div class="stat"><b class="neg">{e('fedex_ton')}%</b><span>FedEx Freight tonnage 2019-2024, vs {e('mkt_ton')}% for LTL-type truck freight</span></div>
 <div class="stat"><b>{e('nc')}%</b><span>Nowcast, shipments/day Jun-Sep 2026 YoY (80%: {e('nc_lo')}% to {e('nc_hi')}%)</span></div>
 <div class="stat"><b>${e('oi_vol')}M</b><span>Op. income per year from 1 pt of shipments; 1 pt of price = {e('ratio')} pts of volume</span></div>
 <div class="stat"><b class="pos">{e('fuel_lift')}%</b><span>Fuel lift to revenue/shipment Jun-Sep 2026; {e('fuel27')}% at EIA's 2027 diesel</span></div>
</div>
<h2>1. Market or FedEx?</h2>
<ul>
 <li><b>LTL-type freight fell {e('mkt_ton_abs')}% by weight from 2019 to 2024</b> (FAF5); FedEx Freight's tonnage fell {e('fedex_ton_abs')}%. The level gap holds under three definitions of the market.</li>
 {peer_line}
</ul>
<div class="two"><div>{peer_fig}</div><div>{second_fig}</div></div>
<h2>2. Nowcast for Oct 29, backtested</h2>
<div class="two"><div>{nowcast_fig}</div><div>
<div class="call">Jun-Sep 2026 shipments per day: <b>{e('nc')}% YoY</b> (~{e('nc_ads')}k/day vs ~{e('base_ads')}k), 80% range {e('nc_lo')}% to {e('nc_hi')}%.
BofA published -3.0%; management guided to exit 2026 flat to slightly positive.</div>
<p>Each model was refit at each of {e('n_test')} past quarters on data available at the time and scored out of sample. Macro indicators alone
(MAE {e('macro_mae')} pp) lost to last quarter's trend ({e('naive_mae')} pp).{peer_bt}</p></div></div>
<div class="pb"></div>
<h2>3. Yield: price, weight or fuel?</h2>
<div class="two"><div>{img('f2_revenue_bridge.png')}</div><div>{img('f3_fuel_model.png')}</div></div>
<ul>
 <li>FedEx collects <b>{e('rho')}x its published fuel surcharge</b> (sd {e('rho_sd')} over 8 quarters), so the tariff splits fuel from price even at record diesel.
 Out of sample, FY26 Q4 base revenue/cwt comes out at {e('oos')}%; management called it a slight decline.</li>
 <li>Heavier shipments lower revenue/cwt mechanically (elasticity {e('beta')}, 95% CI {e('beta_ci')}, from Priority vs Economy with quarter fixed effects).
 A cross-carrier panel gives {e('beta_x')} ({e('beta_x_ci')}). Weight-adjusted, like-for-like price was <b>{e('wadj_lo')}% to {e('wadj_hi')}%</b> in FY26 Q4;
 weight per shipment is rising industry-wide, so FedEx's +3% is not a FedEx-specific density effect.</li>
</ul>
<h2>4. The exchange rate between price and volume</h2>
<div class="two"><div>{img('f4_value_of_a_point.png')}</div><div>{img('f5_lanes.png')}</div></div>
<p>Each revenue dollar from volume added {e('vol_c')} cents of operating income; from price/mix, {e('price_c')} cents ({e('d_n')} quarters, ex-COVID).
At the market's ~{e('mult')}x EV/adjusted operating income, one point of shipments is worth about ${e('per_share')} per share.</p>
<h2>5. What I would build with FedEx Freight's data</h2>
<table>
<tr><td>Retention</td><td>Account-level volume early warning (incl. formerly bundled accounts), ranked by volume at risk for the sales team. Each point retained ~${e('oi_vol')}M op. income/yr.</td></tr>
<tr><td>Pricing</td><td>Price response by lane and segment from renewals and GRIs; the {e('ratio')}:1 price-volume exchange rate as a guardrail in the new pricing system.</td></tr>
<tr><td>Revenue integrity</td><td>Predict shipment density from shipper, commodity and history; route the biggest expected differences from dimensioner data to inspection under density-based NMFC classes.</td></tr>
<tr><td>Fuel</td><td>Realized/tariff fuel ratio by contract; plan for 2027, when EIA's diesel path turns fuel into a {e('fuel27')}% revenue/shipment headwind.</td></tr>
<tr><td>Network</td><td>Imbalance-aware lane pricing: Tennessee is a net receiver ({e('tn_net')}%); Mountain-state lanes are heavily inbound.</td></tr>
</table>
<p class="small" style="margin-top:8pt">Sources: SEC EDGAR (FedEx Corp, FDXF, ODFL, SAIA, XPO, ARCB), FRED (ATA, Cass, Fed industrial production, BLS PPI, EIA diesel), BTS/ORNL FAF5.7.1,
fedexfreight.com fuel surcharge table, press reports of analyst estimates. Code, tests and full report: github.com/kstc707/job-search (fedex_freight_project).
Independent analysis for a job application; not affiliated with or endorsed by FedEx; not investment advice.</p>
</body></html>"""
src = OUT / "brief.html"
src.write_text(doc)
pdf = OUT / "Koppolu_FedEx_Freight_Market_or_Share.pdf"
subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True, timeout=120)
print("written", pdf, f"{pdf.stat().st_size / 1024:.0f} KB")
