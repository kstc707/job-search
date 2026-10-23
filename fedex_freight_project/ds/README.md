# Data science project: LTL volume nowcasting and share-price modeling

The data analysis in `../reports/` describes what happened. This directory is the modeling project:
- problems stated in advance and pre-registered;
- models fitted and compared against baselines;
- significance tests and calibrated uncertainty;
- every post-hoc change logged;
- forecasts locked before the outcomes are known.

| File | What it is |
|---|---|
| `PREREGISTRATION.md` | Targets, information sets, splits, metrics and success criteria, committed before any model was fitted (commit `4ccfa5f`) |
| `DEVIATIONS.md` | Every change made after seeing results, with reason and safeguard |
| `MODEL_CARD.md` | Intended use, data, evaluation, limitations |
| `prospective_forecasts.csv` + `.sha256` | Forecasts locked 2026-10-23 (commit `e4e6b9d`) for the peers' Q3 2026 and FDXF's Jun–Sep 2026 |

Code lives in `../ltlds/` (package) and `../scripts/ds_*.py` (runners). Outputs and figures are in `../reports/ds/`.
Tests are in `../tests/test_ds.py`.

## Task 1: nowcasting carrier shipments (five carriers pooled)

**Setup**
- 192 carrier-quarters; 90 test rows from 2022 to 2026.
- Point-in-time features, gated by EDGAR filing dates.
- Rolling origin with nested tuning.
- Significance by Diebold–Mariano with the Harvey–Leybourne–Newbold correction; intervals by conformal prediction.

**Results**
- **The carrier's own intra-quarter monthly data is the only significant gain.** MAE 1.86 pp vs 3.27 for naive
  (−43%, p = 0.001).
- **Pooled ridge, gradient boosting and their ensemble improve 12–22% but are not significant** at 36 issue dates
  (best p = 0.23).
- **Peers' same-month data alone is worse than naive** (MAE 6.72). Carriers' volumes diverge, which is itself the
  share story.
- **Ablation:** macro, market and price features hurt at this sample size; own history and own monthly data carry
  the forecast.
- **Intervals:** conformal intervals reach nominal coverage on average. Group-conditional (Mondrian) calibration
  fixes a pooled-calibration problem (FDX coverage was 56%). Quantile GBM under-covers (0.51).

## Task 2: how much of FedEx Freight's lost share is price?

**Setup**
- Share of the five carriers' daily shipments, against weight-adjusted relative revenue per cwt.
- Elasticity estimated on the **four peers only**, then applied to FedEx out of sample.

**Elasticity**
- −0.65 (95% CI −0.99 to −0.31), long-run −0.98.
- Within-carrier permutation placebo: p = 0.015.
- Robust to ex-fuel prices (−0.96) and to time fixed effects (−1.45).
- Leave-one-carrier-out: beats "no change" for 3 of 4 carriers.

**FedEx, mid-2021 to mid-2026** (Q2-to-Q2 annual changes, which sum exactly)

| Component | Change in share |
|---|---|
| Total | −16.7 log-% |
| Explained by relative price | −7.9 |
| Not explained by price | −8.7 |

Results are similar for any anchor quarter: the total is −9.8 to −16.7 and the price share is 40–55%.

| Year to Q2 | Actual | Price | Not price |
|---|---|---|---|
| 2023 (FedEx raised relative price ~10%) | −9.4 | −10.4 | +0.9 |
| 2024 (the year after Yellow's shutdown) | −3.3 | +2.5 | **−5.8** |
| 2026 (through the spin-off) | −3.7 | +1.8 | **−5.6** |

**Conclusion**
- The 2022–23 share loss was price-driven: the yield-first strategy.
- The 2023–24 loss (peers absorbed Yellow's customers) and the 2025–26 loss (spin-off and bundle unwinding) were
  **not** price. In 2025–26 FedEx's relative price was falling.
- This sharpens the earlier "price doesn't explain it" claim. It holds for the recent period, not for 2022–23.

**Changepoints.** A simulation-calibrated detector found no breaks. At 20 overlapping points it would raise a false
alarm 24% of the time anyway, so this is reported as a negative result and the event-dated split is used instead
(`DEVIATIONS.md` #2).

## Reproduce

```
.venv/bin/python -I scripts/ds_build_panel.py
.venv/bin/python -I scripts/ds_nowcast_eval.py        # ~20 min (nested tuning, ablation, importance)
.venv/bin/python -I scripts/ds_nowcast_posthoc.py
.venv/bin/python -I scripts/ds_conformal_groups.py
.venv/bin/python -I scripts/ds_share_model.py
.venv/bin/python -m pytest -q tests
```
