"""Write the project README from the shared headline numbers (reports/site/headline.json)."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
H = json.loads((ROOT / "reports/site/headline.json").read_text())
peer = (f"| Relative to 4 public LTL peers (ODFL, SAIA, XPO, ARCB), shipments/day YoY since FY2023 | **{H['rel_mean']} pp/yr** "
        f"(last 4 quarters: {H['rel_last4']}) |\n") if H.get("rel_mean", "n/a") != "n/a" else ""
peer_mae = ""
for m in ("peer_ar", "peer", "peer_macro_ar"):
    if m + "_mae" in H:
        peer_mae += f", `{m}` {H[m + '_mae']} pp"

text = f"""# FedEx Freight: market or share? (public data only)

An independent analysis of FedEx Freight's volume decline, yield and lanes, built to accompany a Data Science
Internship application. **Every input is public:** SEC EDGAR filings (FedEx Corp, FedEx Freight Holding Co.
and four LTL peers), FRED, BTS/ORNL Freight Analysis Framework 5.7.1, EIA diesel prices, and FedEx Freight's
published fuel surcharge table. No synthetic data.

**Deliverables:**

| | |
|---|---|
| Interactive report | `reports/site/index.html`, published at https://claude.ai/artifact/Ee3dgrWjP7n7E8FSMNHTuA (private until shared) |
| Two-page brief (PDF) | `reports/brief/Koppolu_FedEx_Freight_Market_or_Share.pdf` |
| Email draft | `reports/email_draft.md` |
| External benchmarks (guidance, valuation, peer data, NMFC, diesel) | `reports/external_benchmarks.md` |
| Data inventory | `data/README.md`, `data/README_peers.md` |

## Headline results (as of 2026-10-23)

| Question | Answer |
|---|---|
| FedEx Freight tonnage, 2019→2024 vs LTL-addressable truck freight (FAF5) | **{H['fedex_ton']}%** vs **{H['mkt_ton']}%** |
{peer}| Nowcast: shipments/day YoY, Jun–Sep 2026 (FDXF reports Oct 29) | **{H['nc']}%** (80%: {H['nc_lo']}% to {H['nc_hi']}%) |
| Realized fuel surcharge / published tariff | **{H['rho']}** (sd {H['rho_sd']}, 8 quarters) |
| FY26 Q4 base revenue/cwt YoY (out-of-sample) vs management's "slight decline" | {H['oos']}%; weight-adjusted price **{H['wadj']}%** |
| Fuel effect on revenue/shipment: Jun–Sep 2026 / at EIA's 2027 diesel | {H['fuel_lift']}% / **{H['fuel27']}%** |
| Operating income per point of shipments / per point of price | **${H['oi_vol']}M / ${H['oi_price']}M** a year; 1 pt price ≈ {H['ratio']} pts volume |
| Value of one point of shipments at ~{H['mult']}x EV/adj. op. income | ≈ ${H['per_share']}/share |

## The four analyses

| Script | Question | Method |
|---|---|---|
| `scripts/option_a_nowcast.py` | Market or FedEx? Nowcast for Oct 29 | Rolling-origin backtest of naive, AR, macro, ridge and peer-index models on 33 fiscal quarters (COVID base effects excluded); intervals from each model's own out-of-sample errors; FedEx-vs-peer gap |
| `scripts/option_b_yield.py` | Price, weight or fuel? | Structural fuel model (published tariff × realized ratio, LOO-CV vs linear, out-of-sample test at record diesel); exact log revenue bridge; weight elasticity from a Priority/Economy panel with quarter fixed effects |
| `scripts/option_c_faf_lanes.py` | Where is freight going? | LTL-addressable proxy from FAF5 (2.7M rows); shift-share 2019→2024; 2035 lane growth; directional imbalance; k-means zone clustering (weak structure, reported as such) |
| `scripts/option_d_value_sensitivity.py` | What is a point worth? | Incremental margins on volume vs price/mix revenue (HAC), converted to $ and per-share value at the market multiple |

Backtest MAE (pp, one quarter ahead): best `{H['best']}` {H['best_mae']}, naive {H['naive_mae']}, macro+AR {H['macro_mae']}{peer_mae}.

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
"""
(ROOT / "README.md").write_text(text)
print("README written")
