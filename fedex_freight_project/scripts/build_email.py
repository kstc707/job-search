"""Draft the follow-up email to the hiring manager from the same headline numbers as the report."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
H = json.loads((ROOT / "reports/site/headline.json").read_text())
price_ok = all(k in H for k in ("wadj_hi", "odfl_adj", "xpo_adj")) and \
    float(H["wadj_hi"]) < min(float(H["odfl_adj"]), float(H["xpo_adj"]))
price_line = ("Price doesn't explain it: FedEx's weight-adjusted price rose less than Old Dominion's\n"
              "  or XPO's, and XPO still grew volume.\n") if price_ok else "\n"
peer = (f"- Against the four public LTL carriers (Old Dominion, Saia, XPO, ArcBest), FedEx Freight's shipments\n"
        f"  per day have run {H['rel_mean_abs']} points a year behind the peer index since FY2023 (last four quarters:\n"
        f"  {H['rel_last4']}). " + price_line) if "rel_mean_abs" in H else ""
body = f"""Subject: Data Science Internship applicant: a public-data nowcast of FedEx Freight's Jun-Sep volumes

Hi [Hiring manager name],

I recently applied for the Data Science Internship at FedEx Freight. Rather than send a generic follow-up, I spent
some time on a question I expect your team works on: how much of FedEx Freight's volume decline is the freight
market, and how much is specific to FedEx Freight. I used only public data: SEC filings for FedEx, FDXF and four
LTL peers, FRED, the federal Freight Analysis Framework, and FedEx Freight's published fuel surcharge table.

A few results:
- From 2019 to 2024, the packaged and finished goods that move LTL fell {H['mkt_ton_abs']}% by weight; FedEx
  Freight's tonnage fell {H['fedex_ton_abs']}%.
{peer}- FedEx Freight collects {H['rho']}x its published fuel surcharge, almost exactly, quarter after quarter. That
  separates fuel from price: weight-adjusted, like-for-like price was up {H['wadj_lo']}% to {H['wadj_hi']}% in the
  quarter ended May 2026.
  At EIA's 2027 diesel forecast, fuel flips to a {H['fuel27']}% headwind on revenue per shipment.
- One point of shipments is worth about ${H['oi_vol']}M of operating income a year; one point of price is worth
  about {H['ratio']} points of volume.

My backtested nowcast for the June-September period you report on October 29: shipments per day {H['nc']}% year
over year (80% range {H['nc_lo']}% to {H['nc_hi']}%). I'll compare it with the actual release.

Two-page brief attached. Interactive version: https://claude.ai/artifact/Ee3dgrWjP7n7E8FSMNHTuA. Code and tests: https://github.com/kstc707/job-search
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
