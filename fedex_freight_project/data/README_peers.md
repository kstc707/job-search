# Peer LTL carrier data (public, SEC EDGAR)

This is a quarterly and monthly LTL volume and yield dataset for FedEx Freight's four largest public peers. It is
meant as an "LTL industry index", so FedEx Freight's volume decline can be split into a market part and a
FedEx-specific part. Everything comes from 8-K exhibits on EDGAR, downloaded 2026-10-23 with User-Agent
`Sai Teja Koppolu skppolu1@memphis.edu`.

**Rebuild:**

```
.venv/bin/python -I scripts/fetch_peer_filings.py data/raw/sec_edgar/peers [TICKER ...]   # ~1,140 docs, ~190 MB
.venv/bin/python -I scripts/parse_peer_kpis.py data/raw/sec_edgar/peers data/processed
.venv/bin/python -I scripts/validate_peer_kpis.py data/processed
```

## Sources

| Ticker | Company (CIK) | Unit covered | Documents |
|---|---|---|---|
| ODFL | Old Dominion Freight Line (878927) | Whole company (≈99% LTL) | Earnings releases (Item 2.02 Ex. 99.1) and mid-quarter "update" releases (Item 7.01) |
| SAIA | Saia, Inc. (1177702) | LTL operating statistics. Revenue and operating income are consolidated | Earnings releases and "LTL operating data" releases (Item 8.01/7.01) |
| XPO | XPO, Inc. (1166003) | North American LTL segment | Earnings releases and monthly "North American LTL operating data" releases (from 2023) |
| ARCB | ArcBest Corp. (**894405**; note that 894081 is a different company) | Asset-Based segment (ABF Freight) | Earnings releases and their "business update" exhibit (Ex. 99.2), plus Item 7.01 mid-quarter updates |

`fetch_peer_filings.py` saves every HTML document of every 8-K filed since 2017-01-01 with Item 2.02, 7.01 or 8.01
into `raw/sec_edgar/peers/<TICKER>/<filing date>_<document>.htm`.

- That is 1,139 documents. Each was checked to be HTML or XBRL, not an error page.
- `.done_<accession>` marker files make re-runs incremental.
- The HTML (~190 MB) is git-ignored (`peers/*/*.htm`). The submissions JSONs are committed.

Documents are recognized by **content, not by item number**:
- **Earnings release:** any document containing the carrier's LTL operating-statistics rows.
- **Monthly update:** any document reporting YoY % for a named month.
- **Table parsing:** cells are read straight from the HTML `<td>`s (no colspan duplication). In each statistics row,
  the first number is the current quarter and the second is the same quarter a year earlier.
- **Assigning the quarter:** each release is assigned to the last calendar quarter that ended at least 15 days
  before its filing date.
- **Duplicates:** if a quarter appears in several documents, the earliest-filed one wins.

## Outputs (`processed/`)

| File | Content |
|---|---|
| `peer_ltl_quarterly_kpis.csv` | Tidy long format, one row per ticker × quarter × metric. Columns: `ticker, period (YYYYQn), period_end, metric, value, unit, prior_year_value, source_file, filed, basis` |
| `peer_ltl_quarterly_kpis_wide.csv` | One row per ticker × quarter |
| `peer_ltl_monthly_kpis.csv` | Monthly **YoY % changes** as reported (`unit = yoy_pct`), with `n_reports` and `first_reported_value` |
| `_peer_ltl_quarterly_rows_audit.csv` | Each value plus the exact source table row it came from |
| `_peer_restatement_check.csv` | Prior-year column of each release vs. the value originally reported |
| `_peer_monthly_vs_quarterly_check.csv`, `_peer_validation_report.txt` | Validation outputs |

**`basis` values:**
- `as_reported` (1,733 rows)
- `restated: prior-year column of the following year's release` (89): used only where no as-reported value
  exists or the old definition differs (Saia 2017)
- `derived: …` (39): the per-day value is the quarter total ÷ workdays, or weight = 2000 × tons ÷ shipments, where a
  release gives only totals

**Canonical metrics (quarterly):**
- Volume and days: `workdays`, `shipments_per_day`, `tons_per_day`, `weight_per_shipment_lbs`
- Yield: `revenue_per_cwt_usd`, `revenue_per_cwt_ex_fuel_usd`, `revenue_per_shipment_usd`,
  `revenue_per_shipment_ex_fuel_usd`
- Financials: `revenue_musd`, `operating_income_musd`, `operating_ratio_pct`, `adjusted_operating_ratio_pct` (XPO)
- Other: `length_of_haul_miles`, `shipments_total`, `tons_total`

**Monthly metrics:** `shipments_per_day_yoy_pct`, `tons_per_day_yoy_pct`, `weight_per_shipment_yoy_pct`,
`revenue_per_day_yoy_pct`, `revenue_per_cwt_yoy_pct`.

## Coverage

**Quarterly:**

| Ticker | Periods | n quarters | Volume (ship/day, tons/day, weight) | Yield | Financials |
|---|---|---|---|---|---|
| ODFL | 2016Q4–2026Q2 | 39 | all 39 | rev/cwt and rev/shipment, incl. and ex-fuel, all 39 | revenue, op income, OR, all 39 |
| SAIA | 2017Q1–2026Q2 | 38 | all 38 (2017 from 2018 releases' prior-year column) | rev/cwt and rev/shipment 38; ex-fuel 2020Q1+ | revenue, op income, OR, 38 |
| XPO | 2016Q4–2026Q2 | 39 | all 39 | rev/cwt incl. and ex-fuel 2019Q4+; rev/shipment 2023Q1+ | LTL revenue, op income, OR and adjusted OR, 39 |
| ARCB | 2016Q4–2026Q2 | 39 | all 39 (tons/day derived from tonnage ÷ workdays through 2023) | billed rev/cwt 2017Q1+, rev/shipment 39 | Asset-Based revenue, op income, OR, 39 |

**Monthly (YoY %):**

| Ticker | Months | Cadence |
|---|---|---|
| ODFL | 2017-02 → 2026-08 (37–38 months) | Middle month of each quarter |
| SAIA | 2017-01 → 2026-08 (77 months; weight 2019-10+) | First two months of each quarter |
| XPO | 2023-05 → 2026-08 (14 months) | One month per quarter |
| ARCB | 2020-04 → 2026-08 (77 months; weight and rev/cwt 2022-01+) | Every month |

**Latest data, as of 2026-10-23:**
- **No peer has reported Q3 2026 yet.** ODFL's 2026-10-22 8-K is a dividend notice. Q3 earnings normally come in
  late October.
- The most recent hard data is the July–August 2026 monthly updates:

  | Carrier | Month | Shipments/day | Tons/day | Weight/shipment | Other |
  |---|---|---|---|---|---|
  | ODFL | Aug | −2.4% | −0.9% | +1.7% | Revenue/day +12.4% |
  | SAIA | Jul | +0.8% | +7.8% | +7.0% | |
  | SAIA | Aug | +1.1% | +8.7% | +7.5% | |
  | XPO | Aug | +5.7% | +3.7% | −1.8% | |
  | ARCB | Jul | −3.3% | +8.1% | +11.8% | |
  | ARCB | Aug | −4% | +9% | +14% | preliminary, rounded |

## Validation (`scripts/validate_peer_kpis.py`)

1. **Totals ÷ workdays = reported per-day values.** PASS. n = 92 for shipments and 69 for tonnage; the largest
   difference is 0.05%, which is rounding of totals reported in thousands.
2. **Weight identity** (tons/day × 2000 ÷ shipments/day = weight per shipment). PASS for all 155 quarter-tickers
   where all three exist. The largest difference is 0.06%.
3. **Operating ratio = 1 − operating income ÷ revenue.** PASS for 155 quarter-tickers, within 0.12 pp.
   - This check caught Saia's Q4 releases, which open with a full-year reconciliation table. The operating ratio is
     now taken from the operating-statistics table.
4. **Four quarters sum to the full-year column of the Q4 release.** PASS for 70 ticker-years of revenue and
   operating income. ODFL, SAIA and ARCB match exactly. XPO is within $4M, because it reports whole $M per quarter.
5. **Restatements.** There were 1,494 prior-year comparisons, and **no volume or yield metric was restated by more
   than 1%.** The 20 restatements above 1% are all financial:
   - XPO operating income and OR: 2023–2024 segment re-allocations.
   - ARCB Asset-Based operating income: 4 quarters.
   - Values are kept **as originally reported**. Use `_peer_restatement_check.csv` to see the restated values.
6. **Monthly vs. quarterly.** The mean of the monthly YoY figures was compared with quarterly YoY computed from
   per-day values, across 303 quarter-metrics.
   - The median gap is **0.50 pp**: ARCB 0.07, ODFL 0.54, XPO 0.63, SAIA 0.96.
   - The 12 cases above 3 pp are all one or two months against a weather- or Omicron-hit quarter: Feb-2021 storms
     (2021Q1) and Jan-2022 (2022Q1).
   - When a month was reported twice (preliminary, then final), the latest report is kept. Only one month was
     revised by more than 2.5 pp (ARCB Apr-2025 tons/day, from +1% to +3.6%).
7. **Spot checks.** I printed the source rows for 2018Q2, 2022Q3 and 2026Q2 for each carrier and checked them by
   hand; see `_peer_ltl_quarterly_rows_audit.csv`.

## Definition changes and breaks to know about

- **Saia, 2018 redefinition of "LTL".** Releases for 2017 and earlier split LTL and TL shipments. From 2018, "LTL"
  covers both, so weight per shipment jumps from about 1,120 to about 1,300 lbs.
  - 2017 quarters therefore come from the 2018 releases' prior-year column, on the new basis.
  - Saia's own 2017 releases on the old basis are **not** used for levels.
  - Saia monthly YoY values for 2017 are on the old basis. That's fine for YoY, but not for levels.
- **ArcBest mix change.** In 2023–2024 ABF reduced truckload-rated "transactional" shipments moving through its
  network.
  - Tonnage per day fell 17–20% YoY in 2024Q1–Q2 while shipments fell only about 5%, and weight per shipment fell
    from about 1,330 to about 1,100 lbs.
  - Treat ARCB tonnage as mix-distorted for 2023–2025. Shipments per day are the cleaner volume measure.
  - ArcBest also uses half-day workdays (for example 63.5).
- **Yellow Corp. shutdown (July–Aug 2023).** Peer shipments jump from 2023Q3 to 2024Q2: Saia +12% to +18% YoY and
  XPO +5% to +8%. That is share captured from a failed competitor, not demand. Model it with an event dummy.
- **XPO.** These are North American LTL segment figures throughout. The GXO (2021) and RXO (2022) spin-offs don't
  change the LTL statistics, and no volume restatement exceeds 1%.
  - Revenue per cwt is only available from 2019Q4, and revenue per shipment from 2023Q1. Older releases label yield
    "gross revenue per shipment" without saying whether fuel is included, so it was left out.
- **Saia financials** are consolidated (they include small non-LTL revenue). **ODFL** revenue is total revenue,
  about 99% LTL services.
- **ODFL 2016Q4–2018** releases give only quarterly totals (in thousands). Per-day values for those quarters are
  derived as total ÷ workdays, which is accurate to within 0.05% where both exist.
- **Calendar quarters.** All peers report on calendar quarters. FedEx Freight's history uses fiscal quarters ending
  Feb/May/Aug/Nov. Use the monthly YoY series to re-align, or compare FedEx quarters to the overlapping calendar
  quarter.

## What's missing, and why

- **No Q3 2026 peer earnings yet.** None had been filed as of 2026-10-23.
- **Large private LTL carriers aren't covered:** Estes, R+L, Southeastern, AAA Cooper, TForce Freight (part of TFI
  International, which reports in a foreign-issuer format) and Averitt. The four peers plus FedEx Freight are the
  public core of the market, not the whole market.
- **Yellow (YELL)** wasn't collected. It stopped operating in 2023, and adding it would only matter for a 2017–2023
  market-total reconstruction.
- **No failed downloads.** Every 8-K in scope was fetched. I fixed one wrong CIK during collection: ARCB is 894405,
  not 894081.

## Quick read: aggregate shipments per day for the four peers

| Quarter | Peer total YoY | FedEx Freight YoY |
|---|---|---|
| 2025Q2 | −3.9% | −1.1% (FY25Q4, Mar–May 2025) |
| 2025Q3 | −3.5% | −2.2% (FY26Q1, Jun–Aug) |
| 2025Q4 | −3.3% | −4.0% (FY26Q2, Sep–Nov) |
| 2026Q1 | −1.0% | −5.8% (FY26Q3, Dec–Feb) |
| 2026Q2 | −0.1% | −5.9% (FY26Q4, Mar–May 2026) |

FedEx Freight's quarters are shifted by about one month against the calendar quarters, so this is indicative only.
Read this way, the peer group stabilized in the first half of 2026 while FedEx Freight kept declining, which puts
the recent gap at about 5–6 pp.
