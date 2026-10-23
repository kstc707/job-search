# FedEx Freight: market or share? (public data only)

An independent analysis of FedEx Freight's volume decline, yield and lanes, built to accompany a Data Science
Internship application. **Every input is public:** SEC EDGAR filings (FedEx Corp, FedEx Freight Holding Co.
and four LTL peers), FRED, BTS/ORNL Freight Analysis Framework 5.7.1, EIA diesel prices, and FedEx Freight's
published fuel surcharge table. No synthetic data.

**Deliverables:**

| | |
|---|---|
| Interactive report | `reports/site/index.html` (also published as a private claude.ai page) |
| Two-page brief (PDF) | `reports/brief/Koppolu_FedEx_Freight_Market_or_Share.pdf` |
| Email draft | `reports/email_draft.md` |
| External benchmarks (guidance, valuation, peer data, NMFC, diesel) | `reports/external_benchmarks.md` |
| Data inventory | `data/README.md`, `data/README_peers.md` |

## Headline results (as of 2026-10-23)

| Question | Answer |
|---|---|
| FedEx Freight tonnage, 2019→2024 vs LTL-addressable truck freight (FAF5) | **-31.4%** vs **-4.4%** |
| Relative to 4 public LTL peers (ODFL, SAIA, XPO, ARCB), shipments/day YoY since FY2023 | **-5.7 pp/yr** (last 4 quarters: +1.6, -0.5, -4.0, -5.7) |
| Nowcast: shipments/day YoY, Jun–Sep 2026 (FDXF reports Oct 29) | **-6.0%** (80%: -9.9% to -0.4%) |
| Realized fuel surcharge / published tariff | **0.59** (sd 0.009, 8 quarters) |
| FY26 Q4 base revenue/cwt YoY (out-of-sample) vs management's "slight decline" | +0.3%; weight-adjusted price **+2.7%** |
| Fuel effect on revenue/shipment: Jun–Sep 2026 / at EIA's 2027 diesel | +8.1% / **-7.7%** |
| Operating income per point of shipments / per point of price | **$21M / $45M** a year; 1 pt price ≈ 2.1 pts volume |
| Value of one point of shipments at ~19x EV/adj. op. income | ≈ $2.66/share |

## The four analyses

| Script | Question | Method |
|---|---|---|
| `scripts/option_a_nowcast.py` | Market or FedEx? Nowcast for Oct 29 | Rolling-origin backtest of naive, AR, macro, ridge and peer-index models on 33 fiscal quarters (COVID base effects excluded); intervals from each model's own out-of-sample errors; FedEx-vs-peer gap |
| `scripts/option_b_yield.py` | Price, weight or fuel? | Structural fuel model (published tariff × realized ratio, LOO-CV vs linear, out-of-sample test at record diesel); exact log revenue bridge; weight elasticity from a Priority/Economy panel with quarter fixed effects |
| `scripts/option_c_faf_lanes.py` | Where is freight going? | LTL-addressable proxy from FAF5 (2.7M rows); shift-share 2019→2024; 2035 lane growth; directional imbalance; k-means zone clustering (weak structure, reported as such) |
| `scripts/option_d_value_sensitivity.py` | What is a point worth? | Incremental margins on volume vs price/mix revenue (HAC), converted to $ and per-share value at the market multiple |

Backtest MAE (pp, one quarter ahead): best `ar1` 3.3, naive 3.8, macro+AR 4.1, `peer_ar` 3.7 pp, `peer` 5.9 pp, `peer_macro_ar` 4.3 pp.

## Reproduce

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash scripts/download_data.sh       # ~550 MB: FRED, FAF5, SEC EDGAR (FedEx, FDXF), fuel table
.venv/bin/python -I scripts/fetch_peer_filings.py   # peer 8-Ks (ODFL, SAIA, XPO, ARCB)
bash scripts/run_all.sh             # parse, analyze, figures, report, brief, email, tests
```

`tests/` checks that downloads are real data, that extracted KPIs tie out to the 10-K and FDXF's recast totals,
that the backtest never trains on its test quarter, and that the decompositions add up.

## Limits

About 37 quarterly observations; FAF 2018–2024 values are BTS model estimates and FAF can't separate LTL from
truckload; public peers are a sample of the LTL market; the fuel model extrapolates a 2025 tariff table; nothing
here uses FedEx internal data. Independent work, not affiliated with or endorsed by FedEx, not investment advice.
