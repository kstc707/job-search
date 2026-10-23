# Quick EDA and project options

Every number below is printed by `scripts/eda.py` (full output: `reports/eda_output.txt`). Figures are in
`reports/figures/`.

## What the data says

### 1. The freight downturn is real but uneven across indicators (`01_freight_cycle.png`)

- **Cass shipments** (all modes, NSA):
  - Post-COVID peak was 2022-08 at 1.278. The low was 0.886 in 2026-01, and the latest value is 1.062 (2026-09). The
    seasonally adjusted (STL) trend is 18.6% below its 2018 peak.
  - YoY was negative in **48 of 57 months** from 2022-01. It turned positive only in the last two prints (+1.9%
    in 2026-09).
- **ATA truck tonnage** (SA) is only 4.3% below its 2022-09 peak. Manufacturing industrial production (IPMAN) is at
  its post-2021 high (2026-09) and has been up 1–2% YoY since mid-2025.
  - The indicators disagree. Tonnage is weighted toward heavy and truckload freight. Cass covers shipper-paid
    freight across modes.
- **Pricing.** The LTL PPI rose 23.6% from June 2022 to Sept 2026. The truckload PPI rose 7.9% over the same
  period. LTL kept pricing discipline through the downturn while truckload rates fell, then both jumped in 2026 as
  diesel went from about $3.70 to $6.29/gal.
- **Truck employment** has fallen from about 1,590k (2022) to about 1,470k, which signals capacity leaving the
  market.

### 2. Seasonality (`02_seasonality.png`)

- **Cass shipments (2016–2019 profile):** January is 6.3% below trend and May is 5.7% above it. The STL seasonal
  swing is −10.7% to +6.2%.
- **FedEx Freight:** fiscal Q3 (Dec–Feb) is the weakest quarter every year, because of holidays and winter weather.
  In FY2025, ADS was 92.0k / 91.0k / 85.1k / 92.1k for Q1–Q4. Any YoY or forecast work needs operating-day and
  seasonal adjustment.

### 3. FedEx Freight: volume down a quarter from peak, yield doubled, and a shift to lighter freight (`03_fedex_freight_kpis.png`)

| | Peak / start | Latest (FY2026 Q4, quarter ended May 2026) |
|---|---|---|
| Avg daily shipments | 117.3k (FY2021 Q4) | **86.7k (−26.1%)**. YoY negative for **8 straight quarters** |
| Weight per shipment | 1,202 lbs (FY2018 Q3) | 948 lbs (low of 913 lbs in FY2025 Q2) |
| Revenue per cwt | $20.41 (FY2017 Q4) | $43.79 |
| Segment operating margin | 23.9% (FY2023 Q1) | 6.6% (0.4% in FY2026 Q3). Includes $492M of FY2026 spin-off costs |

- Fiscal-year roll-up:

  | | FY2023 | FY2026 |
  |---|---|---|
  | ADS (k) | 99.7 | 86.1 |
  | Revenue ($M) | 9,632 | 8,795 |
  | Segment operating income ($M) | 1,925 | 616 |

- FedEx Freight held price, as the high yield shows, and lost volume.
- Lighter shipments push revenue/cwt up mechanically, so revenue/cwt overstates real price gains. This matters for
  the NMFC density-classification point.

### 4. Recently, FedEx volume is falling faster than the macro indicators (`04_fedex_vs_macro_yoy.png`)

**Correlation of FedEx ADS YoY with macro YoY, same quarter:**

| Indicator | All quarters (n = 33) | Excluding COVID quarters (n = 26) |
|---|---|---|
| IPMAN | 0.77 | 0.52 |
| ATA tonnage | 0.42 | 0.67 |
| Cass | 0.83 | 0.57 |

The all-quarter correlations are inflated by COVID. The macro series explain part of the cycle, not all of it.

**Last 4 quarters (FY2026 Q1–Q4), YoY:**

| Series | YoY change |
|---|---|
| FedEx ADS | −2.2%, −4.0%, −5.8%, −5.9% |
| IPMAN | +1.0 to +1.8% |
| ATA tonnage | −0.3 to +1.9% |
| Cass | −3.4 to −7.3% |

FedEx is tracking below industrial output but roughly in line with Cass. Without peer carriers' data, we can't
yet tell whether the gap is lost market share (spin-off, lost bundled discounts, price discipline) or an LTL-wide
slump.

### 5. FAF5 doesn't capture the downturn (`05_faf5_truck_commodities.png`)

- Truck tons in FAF5.7.1 *rose* 1.4% from 2022 to 2024 (12.67B to 12.84B tons). These are annual, modeled
  estimates, and gravel, gasoline and farm products dominate them.
- In LTL-relevant manufactured goods, 2022 to 2024:

  | Commodity | Truck tons change |
  |---|---|
  | Textiles/leather | −16.6% |
  | Misc. manufactured products | −9.9% |
  | Machinery | −5.7% |
  | Mixed freight | +0.4% |
  | Electronics | +0.4% |
  | Pharmaceuticals | +15.4% |
  | Base metals | +18.3% |

- FAF is useful for **where** freight is (lanes, commodities, long-run 2030–2050 growth). It isn't useful for
  **when** volume moves.

---

## Project options (ranked by how much real data science they show)

### Option A (recommended): "Market or share?" A nowcast of FedEx Freight volume, plus a gap decomposition

**Question:** how much of the shipment decline is the freight market, and how much is FedEx-specific?

1. **Build a quarterly model** of ADS YoY on macro indicators: IPMAN, ATA tonnage, Cass, inventory/sales ratio,
   durable-goods orders and the LTL/TL PPI spread.
   - Monthly indicators get aggregated to FedEx fiscal quarters.
   - Add a seasonal and operating-day adjustment.
   - Use small, regularized models: dynamic regression/ARIMAX and ridge, compared against seasonal-naive and
     drift baselines.
   - Run a **rolling-origin backtest** with prediction intervals.
2. **Add an LTL peer index** built from public filings of other LTL carriers (Old Dominion, Saia, XPO, ArcBest).
   Their earnings releases report shipments or tonnage per day (still to be confirmed per carrier when collecting). Estimate FedEx's implied share over time.
3. **Decompose the residual.** "Expected given the market" minus "actual" gives the FedEx-specific gap. Check
   whether it widened after the spin-off and bundle changes.
4. **Write a dated nowcast** for calendar Q3 2026 (Jul–Sep) before FDXF reports it. The first FDXF 10-Q isn't out
   yet, so the email can include a prediction that gets checked against reality.

**Skills shown:** time-series feature engineering across mixed frequencies, honest out-of-sample evaluation,
uncertainty, causal-style decomposition, and data engineering from SEC filings. This maps directly to the likely
intern work (demand forecasting and retention).

**Weaknesses:**
- There are about 37 quarterly points, so the model must stay simple. Overfitting is the main risk.
- The peer data has to be collected first, which adds about a day. Without it, the "share" half is a hypothesis.
- FDXF's next report uses calendar quarters, and the fiscal-quarter history must be bridged to them.
- FedEx's internal team has far better data, so frame the work as a method demo, not "here's what you're missing".

### Option B: Yield and mix decomposition (price vs weight vs fuel vs haul)

**Question:** how much of the rise in revenue/shipment is base price, how much is fuel surcharge, and how much is
heavier or lighter freight?

1. Run a price/volume/mix bridge each quarter using:
   - The FDXF recast's ex-fuel yields, length of haul and Priority/Economy split.
   - Diesel prices for the fuel-surcharge pass-through.
2. Fit a small regression of revenue/cwt on weight/shipment and diesel to show the "lighter freight inflates
   revenue/cwt" effect. Then look at FY2026 Q4 (weight +3%, revenue/shipment +11.5%) in light of the NMFC density
   change.

**Skills shown:** analytical decomposition and econometric reasoning. It's directly relevant to pricing/yield.

**Weaknesses:**
- The data is aggregate. We can't see shipment density or freight class.
- Only 8 quarters of ex-fuel data are public.
- With one or two post-NMFC quarters, the NMFC effect can't be separated from the fuel and mix effects.
- This is more FP&A than DS.

### Option C: Regional and commodity LTL opportunity map (FAF5)

**Question:** which origin–destination lanes and commodities are growing or shrinking in the freight LTL carries?
Filter FAF to manufactured and mixed goods, truck mode and 250+ mile distances.

1. Run a shift-share analysis (national trend vs commodity mix vs regional effect) for 2017–2024.
2. Use the 2030–2050 FAF forecasts for long-run lane growth, and cluster zones by growth and commodity profile.
3. Add a Memphis/Southeast view.

**Skills shown:** large-data wrangling (2.7M rows), geospatial/lane analysis and clustering.

**Weaknesses:**
- FAF can't separate LTL from truckload.
- 2018–2024 are modeled estimates.
- The data is annual and shows no downturn, so it can't speak to the current volume problem.
- There's no FedEx data at regional level to validate against.
- Mostly aggregation, so it's the weakest on modeling.

**Recommendation: A, with one chart from B** (fuel vs base yield) as supporting context. A answers the question a
hiring manager would actually ask ("is the volume drop us or the market?"). It uses the strongest data (37 quarters
of real FedEx KPIs plus monthly macro data). It also ends with a falsifiable prediction they can check.
