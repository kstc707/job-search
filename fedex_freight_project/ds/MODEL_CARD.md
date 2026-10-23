# Model card: LTL carrier shipments nowcast (`ltlds`)

## Intended use

- **What it does.** It estimates a carrier's year-over-year change in average daily shipments for a quarter that has
  ended but whose results have not been published yet (the issue date is the quarter's last day).
- **Who it is for.** Planning or investor-relations analysts who need a number before the release.
- **Not intended for:**
  - forecasts more than one quarter ahead;
  - customer-level or lane-level decisions;
  - investment decisions.

## Data

- **Source.** Public SEC filings for five carriers: FedEx Freight (FDX), ODFL, SAIA, XPO and ARCB. FDX quarters are
  FedEx fiscal quarters; the others are calendar quarters. Macro series come from FRED.
- **Size.** 192 carrier-quarters in total. 138 have a target and are outside the COVID window. 90 of those fall in
  the test period (2022Q1 to 2026Q2).
- **Point-in-time construction.**
  - A monthly operating update is used only if its EDGAR filing date is on or before the issue date.
  - A quarter's results count as published 45 days after it ends.
  - Each macro month counts once the following month has ended.
- **Known gap.** FRED returns today's revised values (no data vintages).

## Models

| Model | Status | Description |
|---|---|---|
| `naive` | Baseline | Last quarter's YoY carried forward |
| `own_monthly` | Pre-registered | The carrier's own monthly updates filed by τ; otherwise `naive` |
| `market` | Pre-registered | Other carriers' monthly updates filed by τ; otherwise `naive` |
| `ridge`, `gbm`, `ensemble` | Pre-registered | Pooled models over 19 features in 6 groups. Tuned by nested expanding-window CV |
| `hybrid`, `ridge_select` | **Post-hoc** (`DEVIATIONS.md` #1) | `hybrid` = `own_monthly` when available, else `ensemble`. `ridge_select` = ridge with feature groups chosen by nested CV |

## Evaluation

**Protocol.** Rolling origin, 2022Q1–2026Q2: 90 carrier-quarters on 36 issue dates. Every model is refit at every
origin, using only targets published before that origin.

| Model | MAE (pp) | 90% CI | MASE | DM vs naive (p) | 80% coverage, pooled / Mondrian | FDX MAE |
|---|---|---|---|---|---|---|
| `hybrid` (post-hoc) | **1.77** | | 0.54 | 0.028 | 0.79 / 0.80 | 3.56 |
| `own_monthly` | 1.86 | 1.54–2.23 | 0.57 | **0.001** | 0.79 / 0.78 | 3.49 |
| `ridge_select` (post-hoc) | 2.47 | | 0.76 | 0.34 | 0.87 | 3.74 |
| `ensemble` | 2.53 | 2.14–2.96 | 0.78 | 0.23 | 0.81 / 0.81 | 3.56 |
| `gbm` | 2.81 | 2.40–3.28 | 0.86 | 0.81 | 0.82 | 4.02 |
| `ridge` | 2.88 | 2.48–3.31 | 0.88 | 0.66 | 0.77 | 3.69 |
| `naive` | 3.27 | 2.71–3.89 | 1.00 | — | 0.72 | 3.49 |
| `market` | 6.72 | 5.87–7.64 | 2.06 | worse, p<0.001 | 0.78 | 7.56 |

**Pre-registered usefulness criterion** (MAE at most 0.9 × naive, and DM p < 0.10). Met by `own_monthly`. Not met by
`ridge`, `gbm` or `ensemble`.

**Ablation** (change in MAE when a group is dropped; each variant retuned at every origin):

| Feature group | Ridge | GBM |
|---|---|---|
| Own history | +0.86 | +0.43 |
| Own monthly | +0.71 | +0.47 |
| Market | −0.21 | −0.26 |
| Macro | −0.40 | −0.01 |
| Price/mix | −0.25 | −0.10 |

The macro, market and price features add noise at this sample size.

**Permutation importance** (temporal holdout, 30 repeats): own history is the main driver for both models; ridge
also relies on own monthly. For GBM, own history adds +2.30 pp of MAE when permuted.

**Intervals**
- Split-conformal intervals hit their nominal coverage on average.
- Quantile GBM under-covers badly (0.51).
- Rows with no monthly data of their own (FDX, and ARCB before its updates are filed) under-cover even with
  group-conditional calibration (≈0.66–0.71). Treat those intervals as optimistic.

**Largest errors.** FDX in FY2023–24, during the share collapse. ARCB in 2023 and 2025, around its exit from
truckload-rated freight.

## Limitations

- **Small sample.** There are 36 test issue dates, so the gains of 12–22% from ML are not statistically
  distinguishable from naive.
- **Structural events the models can't see in advance:** Yellow's shutdown in 2023, ArcBest's truckload exit, and the
  FedEx spin-off.
- **No data vintages.**
- **FDX is idiosyncratic.** No model beats naive for FDX alone.

## Prospective test

- Locked 2026-10-23 in `ds/prospective_forecasts.csv` (SHA-256 in `ds/prospective_forecasts.sha256`).
- Covers ODFL, SAIA, XPO and ARCB 2026Q3, plus FDX's Jun–Aug and Jun–Sep 2026 windows.
- Scored with `scripts/ds_score_prospective.py`.

## Implication for an internal deployment

A carrier's own intra-quarter data is the only signal that significantly beats naive here. FedEx has daily
internal shipment counts, so an end-of-quarter nowcast is largely solved. The modeling value is at longer horizons,
and at account and lane level, where share shifts start.
