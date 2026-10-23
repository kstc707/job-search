"""Build the one-page personal summary (reports/summary/): what I did, why, and why the role fits.
Numbers come from reports/site/headline.json. Writes a PDF (headless Chromium) and an editable Markdown copy.
Run after build_report.py: .venv/bin/python -I scripts/build_summary.py
"""
import html
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REP = ROOT / "reports"
OUT = REP / "summary"
OUT.mkdir(parents=True, exist_ok=True)
H = json.loads((REP / "site/headline.json").read_text())
CHROME = "/opt/pw-browsers/chromium"


def e(k):
    v = str(H[k])
    return html.escape("−" + v[1:] if v.startswith("-") else v)


TITLE = "FedEx Freight project: what I did, and why"
CONTACT = "Sai Teja Koppolu · Memphis, TN · skppolu1@memphis.edu · +1 901-343-7273 · github.com/kstc707"
BODY = f"""
<h2>What I did</h2>
<p>After applying for the Intern–Data Scientist role with Pricing Science &amp; Analysis, I wanted to show how I would work on a real question. I chose one I expect matters to FedEx Freight right now: from mid-2021 to mid-2026, its share of daily shipments among the
five largest public LTL carriers fell {e('share_total').lstrip('−')} log-points, about a sixth. How much of that is price, and how much is something else?</p>
<p>Using only public data (SEC filings for FedEx Freight and four public competitors, FRED, the FAF5 freight database and EIA), I:</p>
<ul>
<li>built a quarterly carrier panel in which each number is used only after it was filed, so no model sees the future;</li>
<li>estimated how shipment share responds to relative price using the four competitors only, then applied it to FedEx out of sample;</li>
<li>backtested models from a naive baseline to gradient boosting over 2022–2026, testing whether differences were real;</li>
<li>locked a forecast of FedEx Freight's June–September shipments per day (<b>{e('fdx_nc')}%</b>) before the October 29 report, with its fingerprint committed to GitHub.</li>
</ul>
<p><b>What I found:</b> price explains the 2022–23 share loss, but not the losses in the year after Yellow's shutdown or the year
to mid-2026, when FedEx's relative price was falling. That suggests price alone won't win the share back. A carrier's own in-quarter data cut forecast error {e('own_gain')}%;
machine learning added no significant gain, and I reported that too.</p>

<h2>Why I did it this way</h2>
<p>Pricing decisions in freight rest on numbers that have to hold up. I wanted to show that I check data
before trusting it, write my methods down first, test every model against a simple baseline, and say plainly when complexity does not help.
Locking the forecast in advance keeps me honest: on October 29 it will be right or wrong in public.</p>

<h2>Why I'm a good fit</h2>
<ul>
<li><b>Analyst experience:</b> as a Data Analyst Intern with the Shelby County District Attorney General's office, I produce weekly
KPI reporting for leadership and automated hand counts with Python and SQL. As a Product
Analyst at TCS, I turned business questions into KPIs with product managers and engineers.</li>
<li><b>Pricing and logistics projects:</b> a discount and margin analysis of 10,194 retail order lines (discounts above 20% turned
margin negative), and late-delivery prediction on 65,752 orders, where a two-predictor logistic regression matched gradient boosting.</li>
<li><b>Foundation:</b> MS in Data Science, University of Memphis (GPA 3.9), Weil Graduate Fellowship, Teaching Assistant for
Machine Learning. Tools: SQL, Python, Power BI, Excel, PowerPoint.</li>
</ul>

<h2>Why this role matters to me</h2>
<p>I want to build my career where analysis drives decisions, and pricing is where that is most direct: an estimate changes what a
customer is quoted and whether they stay. This project reached the limit of public data: quarterly numbers for five carriers. An internship
with Pricing Science &amp; Analysis would let me bring the same discipline to account-level and lane-level pricing data, learn from a team that makes these decisions every day,
and grow that career here in Memphis, where I live.</p>
<p>I would welcome 15 minutes to walk through the project, or to hear which questions matter most to your team.
Thank you for considering my application.</p>
<p class="sig">Sai Teja Koppolu <span class="small">· Code: github.com/kstc707/job-search · Public data only; not affiliated with FedEx.</span></p>
"""

doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(TITLE)}</title>
<style>
@page {{ size: Letter; margin: 0.4in 0.6in; }}
body {{ font: 9.7pt/1.4 "DejaVu Serif", Georgia, serif; color: #14202b; margin: 0; }}
h1 {{ font: 800 19pt/1.1 "DejaVu Sans Condensed", "DejaVu Sans", Arial, sans-serif; margin: 0 0 4pt; }}
h2 {{ font: 700 10.8pt/1.2 "DejaVu Sans Condensed", "DejaVu Sans", sans-serif; margin: 9pt 0 3pt; border-top: 1pt solid #14202b; padding-top: 4pt; }}
.meta {{ font: 7.4pt/1.4 "DejaVu Sans Mono", monospace; color: #4c5864; border-bottom: 1pt solid #14202b; padding-bottom: 5pt; margin-bottom: 10pt; }}
p {{ margin: 0 0 5pt; }} ul {{ margin: 0 0 5pt; padding-left: 14pt; }} li {{ margin: 0 0 2pt; }}
.sig {{ font-weight: 700; margin-top: 6pt; }}
span.small {{ font-weight: 400; }}
.small {{ font: 7.2pt/1.45 "DejaVu Sans Mono", monospace; color: #4c5864; margin-top: 6pt; }}
</style></head><body>
<div class="meta">{html.escape(CONTACT)}</div>
<h1>{html.escape(TITLE)}</h1>
{BODY}
</body></html>"""
src = OUT / "summary.html"
src.write_text(doc)
pdf = OUT / "Koppolu_FedEx_Freight_project_summary.pdf"
subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True, timeout=120)

# editable Markdown copy of the same text
md = BODY
for a, b in [(r"<h2>(.*?)</h2>", r"\n## \1\n"), (r"<b>(.*?)</b>", r"**\1**"), (r"<li>", "- "), (r"</li>", ""),
             (r'<p class="sig">(.*?)</p>', r"\n\1\n"), (r'<p class="small">', "\n_"), (r"(not affiliated with FedEx\.)</p>", r"\1_"),
             (r"</?(ul|p)>", "\n"), (r"<[^>]+>", ""), (r"\n(?!\n|- |#)(?=\S)", " ")]:
    md = re.sub(a, b, md, flags=re.S)
md = re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in md.splitlines()))
(OUT / "Koppolu_FedEx_Freight_project_summary.md").write_text(f"# {TITLE}\n\n{CONTACT}\n{html.unescape(md).rstrip()}\n")
print("written", pdf, f"{pdf.stat().st_size / 1024:.0f} KB")
