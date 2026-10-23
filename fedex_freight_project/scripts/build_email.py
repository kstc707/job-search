"""Draft the follow-up email to the hiring manager from the same headline numbers as the report."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
H = json.loads((ROOT / "reports/site/headline.json").read_text())
peer = (f"- Relative to the four public LTL carriers (Old Dominion, Saia, XPO, ArcBest), FedEx Freight's shipments "
        f"per day have run {H['rel_mean']} points a year versus the peer index since FY2023 "
        f"(last four quarters: {H['rel_last4']}).\n") if "rel_mean" in H else ""
body = f"""Subject: Data Science Internship applicant: a public-data nowcast of FedEx Freight's Jun-Sep volumes

Hi [Hiring manager name],

I recently applied for the Data Science Internship at FedEx Freight. Rather than send a generic follow-up, I spent
some time on a question I expect your team works on: how much of FedEx Freight's volume decline is the freight
market, and how much is specific to FedEx Freight. I used only public data: SEC filings for FedEx, FDXF and four
LTL peers, FRED, the federal Freight Analysis Framework, and FedEx Freight's published fuel surcharge table.

A few results:
- From 2019 to 2024, the packaged and finished goods that move LTL fell {H['mkt_ton']}% by weight; FedEx Freight's
  tonnage fell {H['fedex_ton']}%.
{peer}- FedEx Freight collects {H['rho']}x its published fuel surcharge, almost exactly, quarter after quarter. That
  separates fuel from price: weight-adjusted, like-for-like price was up about {H['wadj']}% in the May quarter.
  At EIA's 2027 diesel forecast, fuel flips to a {H['fuel27']}% headwind on revenue per shipment.
- One point of shipments is worth about ${H['oi_vol']}M of operating income a year; one point of price is worth
  about {H['ratio']} points of volume.

My backtested nowcast for the June-September period you report on October 29: shipments per day {H['nc']}% year
over year (80% range {H['nc_lo']}% to {H['nc_hi']}%). I'll compare it with the actual release.

Two-page brief attached. Interactive version: [report link]. Code and tests: https://github.com/kstc707/job-search
(fedex_freight_project).

I'm based in Memphis and would value 15 minutes to walk through the method, or to hear which of these questions
matter most to your team.

Best regards,
Sai Teja Koppolu
MS Data Science, University of Memphis
skppolu1@memphis.edu | +1 901-343-7273 | https://github.com/kstc707
"""
out = ROOT / "reports/email_draft.md"
out.write_text(body)
print(body)
