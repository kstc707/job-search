# Data inventory: FedEx Freight demand project

Everything here is real, public data. Downloaded 2026-10-23. Re-download with `bash scripts/download_data.sh`
from the project root.

Every file was checked after download. FRED files start with the `observation_date,` CSV header. SEC files are
real EDGAR HTML/XBRL documents, not error pages. The FAF5 zip and xlsx files are real archives, and the PDF is a
real PDF. Parsed SEC figures were tied back to the filings' own totals (see "Validation" below).

Large files are git-ignored and must be re-downloaded: the FAF5 zip/CSV, the FAF5 parquet copy, and the FedEx Corp
release HTML.

---

## 1. FRED (`raw/fred/`)

Source URL pattern: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>`. Series page:
`https://fred.stlouisfed.org/series/<ID>`. Every file has two columns: `observation_date` and `<ID>` (value).

| File | Series | Units / adjustment | Frequency | Date range |
|---|---|---|---|---|
| `TRUCKD11.csv` | ATA Truck Tonnage Index | Index 2015=100, SA | Monthly | 2000-01 to 2026-07 |
| `FRGSHPUSM649NCIS.csv` | Cass Freight Index: Shipments | Index Jan 1990=1, **NSA** | Monthly | **2016-01** to 2026-09 |
| `FRGEXPUSM649NCIS.csv` | Cass Freight Index: Expenditures | Index Jan 1990=1, NSA | Monthly | 2016-01 to 2026-09 |
| `INDPRO.csv` | Industrial Production: Total | Index 2017=100, SA | Monthly | 1919-01 to 2026-09 |
| `IPMAN.csv` | Industrial Production: Manufacturing (NAICS) | Index 2017=100, SA | Monthly | 1972-01 to 2026-09 |
| `PCU484122484122.csv` | PPI: General Freight Trucking, Long-Distance **LTL** | Index Dec 2003=100, NSA | Monthly | 2003-12 to 2026-09 |
| `PCU484121484121.csv` | PPI: General Freight Trucking, Long-Distance **TL** | Index Dec 2003=100, NSA | Monthly | 2003-12 to 2026-09 |
| `PCU4841248412.csv` | PPI: General Freight Trucking, Long-Distance (all) | Index Dec 2003=100, NSA | Monthly | 2003-12 to 2026-09 |
| `TSIFRGHT.csv` | BTS Freight Transportation Services Index | Index 2000=100, SA | Monthly | 2000-01 to 2026-07 |
| `CES4348400001.csv` | All Employees, Truck Transportation | Thousands, SA | Monthly | 1990-01 to 2026-09 |
| `RAILFRTCARLOADSD11.csv` | Rail Freight Carloads | Carloads, SA | Monthly | 2000-01 to 2026-07 |
| `RAILFRTINTERMODALD11.csv` | Rail Freight Intermodal Traffic | Containers & trailers, SA | Monthly | 2000-01 to 2026-07 |
| `GASDESW.csv` | US Diesel Sales Price | $/gallon, NSA | **Weekly** | 1994-03-21 to 2026-10-19 |
| `ISRATIO.csv` | Total Business Inventories/Sales Ratio | Ratio, SA | Monthly | 1992-01 to 2026-08 |
| `WHLSLRIRSA.csv` | Merchant Wholesalers Inventories/Sales Ratio | Ratio, SA | Monthly | 1992-01 to 2026-08 |
| `AMTMNO.csv` | Manufacturers' New Orders: Total Manufacturing | $ millions, SA | Monthly | 1992-02 to 2026-08 |
| `DGORDER.csv` | Manufacturers' New Orders: Durable Goods | $ millions, SA | Monthly | 1992-02 to 2026-08 |
| `RSXFS.csv` | Advance Retail Sales: Retail Trade | $ millions, SA | Monthly | 1992-01 to 2026-09 |

Why the extra series: industrial production, manufacturing orders and inventory/sales ratios drive LTL demand.
The LTL and TL PPIs are the only public price index for LTL. Diesel drives fuel surcharges. Rail intermodal is a
substitute mode. Truck employment is a capacity proxy.

## 2. Freight Analysis Framework v5.7.1 (`raw/faf5/`)

Source page: https://faf.ornl.gov/faf5/ (BTS/FHWA, hosted by ORNL). This is the latest release (FAF5.7.1, files
dated 2025-08-07).

| File | Source URL | Notes |
|---|---|---|
| `FAF5.7.1.zip` (292 MB, git-ignored) | https://faf.ornl.gov/faf5/Data/Download_Files/FAF5.7.1.zip | "Regional database for 2017-2024 and forecasts for 2030-2050 (mid-range)". Contains `FAF5.7.1.csv` plus a copy of the metadata |
| `FAF5.7.1/FAF5.7.1.csv` (1.2 GB, git-ignored) | unzipped from the above | 2,671,386 rows × 56 columns. No nulls, no negative values |
| `FAF5_metadata.xlsx` | https://faf.ornl.gov/faf5/data/FAF5_metadata.xlsx | Code lookups: State, FAF Zone (Domestic: 132 zones; Foreign: 8), Commodity (SCTG2: 42), Mode (8), Trade Type, Distance Band. The code tables match the copy in the zip exactly. Only the "Data Dictionary" text sheet differs |
| `CFS_area_code_FAF5_zone_id.xlsx` | https://faf.ornl.gov/faf5/data/CFS%20area%20code%20-%20FAF5%20zone%20id.xlsx | Census CFS area ↔ FAF zone crosswalk |
| `FAF5_User_Guide.pdf` | https://faf.ornl.gov/faf5/data/FAF5%20User%20Guide.pdf | 14-page user guide |

- **Granularity:** annual. Each row is origin zone × destination zone × domestic mode × commodity (SCTG2) × trade
  type × distance band, plus foreign origin/destination and in/out modes for trade flows.
- **Years:** 2017 is the base year (benchmarked to the 2017 CFS). 2018–2024 are estimates. 2030, 2035, 2040, 2045
  and 2050 are forecasts.
- **Key columns:**
  - Codes: `dms_orig`, `dms_dest`, `dms_mode` (1 = Truck), `sctg2`, `trade_type`, `dist_band`, `fr_orig`/`fr_dest`.
  - Measures: `tons_<yr>` (thousand tons), `value_<yr>` (million 2017 $), `current_value_<yr>` (million current $,
    2018–2024 only) and `tmiles_<yr>` (million ton-miles).
- **Processed copy:** `processed/faf5_7_1.parquet` (git-ignored) is a typed copy for fast loading, built by
  `scripts/faf5_to_parquet.py`.
- **Sanity check:** total tons are about 19.8–20.2 billion per year, and truck mode is 64% of 2024 tons. Both are
  in line with BTS's published FAF totals.

## 3. SEC EDGAR (`raw/sec_edgar/`)

All requests sent `User-Agent: Sai Teja Koppolu skppolu1@memphis.edu`, as EDGAR requires.

### 3a. FedEx Freight Holding Company, Inc.: ticker FDXF, **CIK 2082247**

The CIK was found in `https://www.sec.gov/files/company_tickers.json`. Filing list:
`submissions_CIK0002082247.json` (from https://data.sec.gov/submissions/CIK0002082247.json).
Archive base: `https://www.sec.gov/Archives/edgar/data/2082247/<accession>/`.

| File | Filing | What's in it |
|---|---|---|
| `10-K_FY2026_fdxf-20260531.htm` | 10-K, filed 2026-08-05, acc. 0001628280-26-053359 | First 10-K, FY ended 2026-05-31. Carve-out GAAP financials for FY2026 and FY2025, plus annual LTL stats (ADS, weight/shipment, revenue/shipment, revenue/cwt, Priority vs Economy) |
| `8-K_2026-06-25_*.htm` | 8-K Item 2.02, acc. 0001628280-26-045515 | Q4 FY2026 earnings release (Ex. 99.1). Stats appear only as text bullets. Includes the 7-month transition-period guidance |
| `8-K_2026-08-06_*.htm` | 8-K Item 2.02, acc. 0001628280-26-054314 | Announces the **fiscal-year change to Dec 31**. Ex. 99.1 recasts CY2024 and CY2025 quarterly results and operating stats onto the new presentation, including ex-fuel yields, tonnage and length of haul |
| `8-K_2026-09-02_*.htm`, `8-K_2026-10-02_*.htm` | 8-K Item 8.01 (and 5.08) | Management change and annual-meeting date. No financial data |
| `Form10-12B-A_2026-04-10.htm` | 10-12B/A cover document | Spin-off registration cover. The information statement is a separate exhibit and was **not** downloaded |

### 3b. FedEx Corp: CIK 1048911 (`raw/sec_edgar/fedex_corp_earnings/`, HTML git-ignored)

Before the June 2026 spin-off, FedEx Freight was a FedEx Corp reporting segment. FedEx Corp's quarterly earnings
8-Ks (Item 2.02, Ex. 99.1) include a "FedEx Freight Segment Financial and Operating Highlights" table. That table is
the only public source of quarterly FedEx Freight history.

- `scripts/fetch_fedex_corp_earnings.py` downloaded all 47 Item 2.02 exhibits filed from 2015-12 to 2026-07.
- File names are `<filing date>_<original name>.htm`.

### 3c. Extracted KPI tables (`processed/`)

**`fedex_freight_segment_quarterly_kpis.csv`**: FedEx Freight segment, **fiscal quarters FY2017Q4–FY2026Q4**
(37 quarters, no gaps). Built by `scripts/parse_fedex_freight_segment.py`.

| Column | Meaning |
|---|---|
| `fiscal_period`, `fiscal_year`, `fiscal_quarter`, `period_end` | FedEx fiscal year ends May 31. Q1 ends Aug, Q2 Nov, Q3 Feb, Q4 May |
| `revenue_musd`, `operating_income_musd`, `operating_margin_pct` | Segment revenue and operating income ($ millions) |
| `operating_days` | Operating weekdays in the quarter |
| `avg_daily_shipments_k` | Average daily shipments (thousands), total plus `_priority` / `_economy` |
| `weight_per_shipment_lbs` | Composite weight per shipment (lbs), plus `_priority` / `_economy` |
| `revenue_per_shipment_usd` | Composite revenue per shipment ($), plus `_priority` / `_economy` |
| `revenue_per_cwt_usd` | Composite revenue per hundredweight ($), plus `_priority` / `_economy` |
| `value_basis` | `as_reported` = from that quarter's own release. FY2017Q4 and FY2018Q1–Q3 come from the prior-year column of the following year's release |
| `source_file` | Which release each row came from |

**`fdxf_calendar_quarterly_kpis_recast.csv`**: FDXF's own recast, **calendar quarters 2024Q1–2025Q4** (8
quarters), on the post-spin-off presentation basis. Built by `scripts/parse_fdxf_recast.py`. It has the columns
above plus:

- `total_shipments`, `total_tonnage`, `tonnage_per_day`
- `avg_length_of_haul_miles`
- `revenue_per_shipment_ex_fuel_usd`, `revenue_per_cwt_ex_fuel_usd`
- `separation_and_other_musd` (spin-off costs)

**Audit files:**

- `_fedex_corp_segment_rows.csv` holds every row parsed from every release, with its section label and both the
  current-year and prior-year values.
- `_fedex_corp_segment_rows_long.csv` is the same data mapped to canonical metric names.

### Validation of the SEC extraction

- **Quarters tie to the 10-K.** FY2026 quarterly revenue sums to $8,795M, which is the FY2026 revenue in the 10-K.
  Segment operating income sums to $616M, which is the FY2026 segment figure in the 10-K and the Q4 release.
  Days-weighted ADS = 86.1k, which matches the 10-K.
- **FY2026 Q4 matches the FDXF release.** FedEx Corp's numbers ($2,408M revenue, $158M operating income, 86.7k ADS,
  948 lbs, $415.22/shipment, $43.79/cwt) match FDXF's own Q4 release.
- **The recast ties to annual totals.** CY2025 quarters sum to $8,778M revenue and $1,022M operating income. CY2024
  quarters sum to $9,092M and $1,532M. Both match the recast's annual tables. Also, total shipments ÷ operating
  days = ADS.
- **Restatements.** Each release's prior-year column was compared with the value originally reported a year
  earlier. Operating statistics (ADS, weight, yield) were never restated, except a $2.97 change to FY2020Q4
  revenue/shipment. **FY2024 revenue was restated up by $80–94M per quarter** in the FY2025 releases (a FedEx
  reporting change), and operating income moved by $1–7M in a few quarters. The CSV keeps the **as-reported**
  values. Use `_fedex_corp_segment_rows.csv` if you need the restated ones.

## 4. What failed or is missing, and why

| Item | Status | Why |
|---|---|---|
| FDXF **10-Q** | **None exists yet** | FDXF switched to a Dec 31 fiscal year. As of 2026-10-23, EDGAR shows no 10-Q. The first one is likely for the quarter ended 2026-09-30. Results for June–Sept 2026 are not public yet |
| `TRUCKN11` (ATA tonnage, NSA) | 404, removed | The series ID doesn't exist on FRED. Only the SA version (`TRUCKD11`) is available |
| Cass index before 2016 | Not on FRED | FRED's Cass series start in 2016-01, although Cass's index base is 1990. Seasonality is estimated from 2016 onward only |
| FedEx Freight operating stats before FY2017Q4 | Not in 8-K exhibits | FedEx Corp releases before June 2018 have no Freight operating-stats table. Those stats were in a separate "Statistical Book" on FedEx's investor site, not on EDGAR |
| FedEx Corp special filings (2018-09-06, 2022-09-15, 2024-09-03, 2026-07-21) | Downloaded, not parsed | These are recasts or a preliminary-results notice. They don't contain the standard quarterly Freight table. The 2026-07-21 file recasts FedEx Corp *without* Freight after the spin |
| Form 10 information statement (Ex. 99.1 to the 10-12B/A) | Not downloaded | It overlaps with the 10-K. Fetch it if older carve-out history is needed |

## 5. Caveats that matter for modeling

- **Three different reporting bases.** FedEx Corp segment numbers use fiscal quarters (Aug/Nov/Feb/May). FDXF's
  recast uses calendar quarters and a new expense presentation. The FDXF 10-K uses carve-out GAAP: FY2026 operating
  income is **$540M** there versus **$616M** as a FedEx segment. Don't mix bases in one series without a bridge.
- **Spin-off costs distort operating income from FY2026.** Separation and other costs were $492M in FY2026. Use
  adjusted figures, or volume and yield metrics, for trend work.
- **Fuel distorts yield in 2026.** Diesel rose from about $3.70/gal (late 2025) to $6.29 (Sept 2026). The FY2026 Q4
  jump in revenue/shipment (+11.5% YoY) is mostly fuel surcharge. Use the ex-fuel yields in the FDXF recast.
- **FAF5 is modeled, annual, and doesn't separate LTL from truckload.** 2018–2024 values are BTS estimates, not
  survey observations. Truck tons are dominated by bulk commodities (gravel, gasoline, agriculture). FAF shows truck
  tons *up* 1.4% from 2022 to 2024 while the Cass shipments index fell. It can't explain FedEx's quarterly volume
  decline.
- **Small sample.** There are 37 quarterly observations, and COVID quarters dominate any correlation. Keep models
  small and backtest honestly.
