# Deviations from the pre-registration

Every change made after seeing results, why it was made, and how it is kept honest.

| # | Date | Deviation | Reason | Safeguard |
|---|---|---|---|---|
| 1 | 2026-10-23 | **Added two post-hoc nowcast models:** `hybrid` (the carrier's own monthly updates when filed, else the ensemble) and `ridge_select` (feature groups chosen by nested CV inside each training set) | The ablation showed that the macro, market and price features hurt ridge, and that own monthly data dominates | Both are labeled post-hoc in every table. Neither replaces the pre-registered `best_model`. The prospective Q3 2026 test is the unbiased check |
| 2 | 2026-10-23 | **Task 2 regimes come from a fixed event date** (spin-off announced 2024-12-19, so 2024Q4 onward), not from detected changepoints | The calibrated detector found no break. At this length (20 overlapping YoY points, φ≈0.95), its simulated false-alarm rate is 0.24, so a detected break would not have been credible either | The split is set by an external event date, not chosen by searching the data. The changepoint result is reported as a negative result |
| 3 | 2026-10-23 | **The permutation placebo for the share elasticity covers b0 only** | The pre-registration did not say which coefficient the placebo tests | b0 is the pre-registered primary coefficient |
| 4 | 2026-10-23 | **Prediction intervals are group-conditional (Mondrian) conformal**, grouped by whether the carrier's own monthly update was available at τ. This replaces pooled conformal for the prospective forecasts | Pooled intervals averaged two very different error regimes. They under-covered FedEx (56%) and over-covered carriers with monthly data (96%) | Both versions are reported side by side in `reports/ds/conformal_groups.csv`. Rows without own monthly data still under-cover (~66–71% vs 80%), and this is stated |
