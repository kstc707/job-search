# Pre-registration: LTL volume nowcasting and share-price modeling

Written and committed **2026-10-23, before any model in `ltlds/` was fitted**. Its purpose is to fix the targets,
information sets, splits, metrics and success criteria in advance, so the evaluation cannot be tuned to the results.
Any deviation is logged in `ds/DEVIATIONS.md` with the reason.

## Business questions

1. **Demand forecasting.** Can a model give an LTL carrier's quarterly shipments per day before the carrier reports,
   and beat the forecasts a planner would use by default? Here, "a carrier" is FedEx Freight or one of its four
   public peers.
2. **Share and price.** How much of FedEx Freight's lost share of LTL shipments is explained by its price relative to
   competitors, and how much is not?

## Task 1: nowcasting carrier volume

**Unit, target and timing**
- **Unit:** carrier × reporting quarter.
  - Carriers: FDX (FedEx Freight segment, fiscal quarters), ODFL, SAIA, XPO (North American LTL), ARCB (Asset-Based).
- **Target:** `y = 100 × ln(SPD_q / SPD_{q-4})`, the YoY log change in average shipments per day.
- **Issue time τ:** the last day of quarter q. That is after the quarter ends and before the carrier reports
  (reports come about 3–6 weeks later).

**Information set at τ (point-in-time):**
- The carrier's own results for quarter q-1 and earlier. These are reported within ~6 weeks of quarter end, so they
  are always known at τ.
- The carrier's own monthly updates for months inside q, **only if filed on or before τ**. The EDGAR filing date
  decides this.
- Peers' (excluding self) monthly updates for months inside q, filed on or before τ, and peers' quarter q-1 results.
- Monthly macro series for the first two months of q. The third month is not yet published at τ. Weekly diesel uses
  all weeks of q.
- **Known limitation:** FRED returns today's revised data, not the values published at the time (no vintages). Revisions
  to industrial production and the ATA index are usually small.

**Sample**
- All carrier-quarters with a defined target from 2017.
- **Excluded:** rows whose quarter or YoY base overlaps the COVID shock, meaning windows ending 2020-03-01 to
  2021-08-31. They are excluded from both training and scoring.
- **Yellow shutdown** (July 2023): included, not dummied, in the primary analysis.

**Evaluation**
- **Splits:** expanding-window, rolling-origin.
  - A test row issued at τ is predicted by a model trained only on rows whose target was published before τ
    (issue date + 45 days < τ).
  - **Test period:** every row issued on or after **2022-01-01**.
- **Tuning:** nested. Hyperparameters are chosen inside each training set on its own last 8 issue dates (an inner
  expanding window), never on test rows.

**Models (fixed list)**

| Model | Description |
|---|---|
| `naive` | Last quarter's YoY carried forward (ŷ = y_{q-1}) |
| `market` | Mean YoY of the peers' monthly updates filed by τ; falls back to `naive` |
| `own_monthly` | Mean of the carrier's own monthly updates filed by τ; falls back to `naive` |
| `ridge` | Pooled ridge with carrier indicators, standardized features, missing values imputed with missing-indicator flags |
| `gbm` | Histogram gradient boosting (native missing-value handling), small tuned grid |
| `ensemble` | Mean of `ridge` and `gbm` |

**Metrics**
- **Primary:** MAE in YoY percentage points over all test rows.
- **Secondary:** RMSE; MASE (relative to `naive`); directional accuracy; MAE by carrier and for FDX alone.

**Significance test**
- Diebold–Mariano test with the Harvey–Leybourne–Newbold small-sample correction.
- It is run on the loss differential (absolute error) averaged per issue date.
- **Primary comparison:** best model vs `naive`.

**Prediction intervals**
- Nominal 80%, built by split-conformal from each model's own earlier out-of-sample errors (rolling). Quantile
  gradient boosting is the comparison.
- Report empirical coverage and mean width.

**Interpretation**
- **Ablation:** drop one feature group at a time (own history, own monthly, market, macro, price/mix, carrier ID)
  and report the change in MAE.
- **Permutation importance:** computed on the final fitted model.

**Success criteria (stated in advance)**
- A model is called **useful** if its MAE is at most 0.90 × the `naive` MAE **and** its Diebold–Mariano p-value is
  below 0.10.
- Intervals are **calibrated** if empirical coverage is within 70–90% for a nominal 80%.
- If no model meets the bar, the report says so.

**Prospective test**
- Forecasts for the next unreported quarter of all five carriers will be written to `ds/prospective_forecasts.csv`
  with a SHA-256 hash, and committed before any of them report:
  - ODFL, SAIA, XPO and ARCB: calendar Q3 2026.
  - FDX: its June–August 2026 window, plus the June–September window FDXF reports on 2026-10-29.
- They will be scored once the actuals are published.

## Task 2: share and relative price

**Definitions**
- **Share:** each carrier's average daily shipments as a share of the five carriers' total in a calendar quarter.
  FDX fiscal quarters are mapped to the calendar quarter they overlap by two months.
- **Relative price:** a carrier's weight-adjusted revenue per cwt ÷ the shipment-weighted mean of the other four
  carriers.
  - Weight adjustment: `ln p − β ln w`, with β the cross-carrier elasticity from `option_b` (−0.57).
  - Revenue per cwt **including fuel** for all five. Ex-fuel is a robustness check for ODFL, SAIA and XPO only.

**Model**
- Panel regression of `Δ4 ln share` on `Δ4 ln relative price`, current quarter and one lag, with carrier fixed
  effects.
- **Estimated on the four peers only**, then applied out-of-sample to FDX. FDX's residual is its share change not
  explained by price.

**Validation**
- Leave-one-carrier-out prediction error.
- Permutation placebo: shuffle relative price within carrier, 2,000 times, to get the null distribution of the
  elasticity.
- Robustness: include FDX in estimation; add or drop the lag; use ex-fuel prices.

**Changepoints**
- PELT changepoint detection on FDX's Δ4 log share, with a BIC-style penalty.
- Stability check: rerun with leave-one-quarter-out and half and double the penalty.

**Reported result:** explained vs unexplained share change for FDX, by detected regime.

## What would change the conclusions

1. **If price explains the 2022–24 share loss but not the 2025–26 loss,** the account-retention hypothesis from the
   report stands.
2. **If price explains neither,** the price argument weakens.
3. **If price explains both,** the report's claim that "price doesn't explain it" is wrong and gets corrected.
