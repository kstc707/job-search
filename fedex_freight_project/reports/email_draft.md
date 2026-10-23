Subject: Data Science Internship applicant: a public-data nowcast of FedEx Freight's Jun-Sep volumes

Hi [Hiring manager name],

I recently applied for the Data Science Internship at FedEx Freight. Rather than send a generic follow-up, I spent
some time on a question I expect your team works on: how much of FedEx Freight's volume decline is the freight
market, and how much is specific to FedEx Freight. I used only public data: SEC filings for FedEx, FDXF and four
LTL peers, FRED, the federal Freight Analysis Framework, and FedEx Freight's published fuel surcharge table.

A few results:
- From 2019 to 2024, the packaged and finished goods that move LTL fell 4.4% by weight; FedEx
  Freight's tonnage fell 31.4%.
- Against the four public LTL carriers (Old Dominion, Saia, XPO, ArcBest), FedEx Freight's shipments
  per day have run 5.6 points a year behind the peer index since FY2023 (last four quarters:
  +1.6, -0.5, -4.0, -5.7). Price doesn't explain it: FedEx's weight-adjusted price rose less than Old Dominion's
  or XPO's, and XPO still grew volume.
- FedEx Freight collects 0.59x its published fuel surcharge, almost exactly, quarter after quarter. That
  separates fuel from price: weight-adjusted, like-for-like price was up +2.1% to +2.7% in the
  quarter ended May 2026.
  At EIA's 2027 diesel forecast, fuel flips to a -7.7% headwind on revenue per shipment.
- One point of shipments is worth about $21M of operating income a year; one point of price is worth
  about 2.1 points of volume.

My backtested nowcast for the June-September period you report on October 29: shipments per day -5.9% year
over year (80% range -10.1% to -0.4%). I'll compare it with the actual release.

Two-page brief attached. Interactive version: https://claude.ai/artifact/Ee3dgrWjP7n7E8FSMNHTuA. Code and tests: https://github.com/kstc707/job-search
(fedex_freight_project).

I'm based in Memphis and would value 15 minutes to walk through the method, or to hear which of these questions
matter most to your team.

Best regards,
Sai Teja Koppolu
MS Data Science, University of Memphis
skppolu1@memphis.edu | +1 901-343-7273 | https://github.com/kstc707
