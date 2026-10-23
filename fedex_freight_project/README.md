# FedEx Freight: market or share? (public data, data science project)

What explains FedEx Freight's lost LTL volume, and what will it report next? Everything here uses public data:
SEC EDGAR filings for FedEx Corp, FedEx Freight and four LTL peers (ODFL, SAIA, XPO, ARCB), FRED, BTS/ORNL FAF5.7.1,
EIA, and FedEx Freight's published fuel surcharge table. Every chart is generated in Python (matplotlib).

| Deliverable | Where |
|---|---|
| **One-page overview (PDF)** | `reports/overview/Koppolu_FedEx_Freight_overview.pdf` |
| **2-minute video** (synthetic-voice narration plus on-screen captions) | `reports/video/Koppolu_FedEx_Freight_overview.mp4`, `reports/video/narration_script.md` |
| Report page | `reports/site/index.html`, published at https://claude.ai/artifact/Ee3dgrWjP7n7E8FSMNHTuA (private until shared) |
| Two-page brief (PDF) | `reports/brief/Koppolu_FedEx_Freight_Market_or_Share.pdf` |
| **Data science project** | `ds/` (pre-registration, deviations log, model card, locked forecasts), `ltlds/` (package), `scripts/ds_*.py` |
| Email draft | `reports/email_draft.md` |
| External benchmarks | `reports/external_benchmarks.md` |
| Data inventory | `data/README.md`, `data/README_peers.md` |

## Results (as of 2026-10-23)

| Question | Answer |
|---|---|
| FedEx share of five-carrier shipments, mid-2021 to mid-2026 | **-16.7 log-%** |
| ... explained by relative price (elasticity estimated on the four peers only, 0.65; placebo p = 0.015) | -7.9 |
| ... not explained by price (the Yellow year and the spin-off year) | **-8.7** |
| Locked forecast: FedEx shipments/day, Jun-Sep 2026 (FDXF reports Oct 29) | **-6.0%**; SHA-256 committed in e4e6b9d |
| Nowcast accuracy, 2022-26 out of sample | Own intra-quarter data: -43% error vs naive (DM p = 0.001). ML: -12 to 22%, not significant (p = 0.23) |
| Fuel | Realized = 0.59 x published tariff; 2027 at EIA diesel: -7.7% revenue/shipment |
| Value | 1 pt of shipments ~ $21M operating income/yr (~$2.66/share); 1 pt of price ~ 2.1 pts of volume |

## How it is built

- `ds/PREREGISTRATION.md` was committed before any model was fitted. `ds/DEVIATIONS.md` logs every later change.
- `ltlds/panel.py` builds point-in-time features: a monthly update counts only if filed on EDGAR by the forecast date.
- `ltlds/evaluate.py` runs the rolling-origin backtest with nested tuning, the Harvey-Leybourne-Newbold Diebold-Mariano
  test, and rolling and group-conditional conformal intervals.
- `ltlds/share.py` builds the share panel, the weight-adjusted relative price, the panel elasticity, the permutation
  placebo, and changepoint detection with a simulation-calibrated penalty.
- `scripts/option_*.py` hold the earlier analyses: fuel model, revenue bridge, FAF5 lanes, value sensitivity.
- `tests/`: 31 tests. They check that downloads are real data, that the data ties out to the filings,
  that no model trains on unpublished targets, conformal coverage on synthetic data, the power of the DM test,
  changepoint recovery, and the integrity of the forecast-file hash.

## Reproduce

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash scripts/download_data.sh
.venv/bin/python -I scripts/fetch_peer_filings.py data/raw/sec_edgar/peers
bash scripts/run_all.sh
```

After the actuals are published: `.venv/bin/python -I scripts/ds_score_prospective.py --fdx-junsep-yoy-pct <reported>`.

## Limits

- **Small sample:** 90 test carrier-quarters on 36 issue dates.
- **No data vintages** from FRED.
- **Public peers are a sample** of the LTL market.
- **Quarter alignment:** FedEx fiscal quarters are mapped to calendar quarters.
- **Intervals for FedEx are optimistic:** about 65-71% backtest coverage at a nominal 80%.
- **No internal data:** nothing here uses FedEx internal data.

Independent work, not affiliated with or endorsed by FedEx, not investment advice.
