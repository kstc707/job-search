"""Quick EDA: freight-cycle trends, seasonality, the 2023-2026 downturn, and FedEx Freight KPIs.

Run from the project root:  .venv/bin/python scripts/eda.py
Writes figures to reports/figures/ and prints every number quoted in reports/eda_summary.md.
"""
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, PROC, FIG = ROOT / "data/raw", ROOT / "data/processed", ROOT / "reports/figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 200)
DOWNTURN = ("2022-06-01", "2026-09-30")


def fred(sid):
    s = pd.read_csv(RAW / f"fred/{sid}.csv", parse_dates=["observation_date"], index_col=0, na_values=".")[sid]
    return s.dropna()


def shade(ax):
    ax.axvspan(pd.Timestamp(DOWNTURN[0]), pd.Timestamp(DOWNTURN[1]), color="0.9", zorder=0)


def section(t):
    print(f"\n=== {t} ===")


# ---------------------------------------------------------------- 1. macro freight cycle
section("1. Freight cycle (FRED)")
monthly = {k: fred(k) for k in ["TRUCKD11", "FRGSHPUSM649NCIS", "FRGEXPUSM649NCIS", "INDPRO", "IPMAN",
                                "PCU484122484122", "PCU484121484121", "TSIFRGHT", "CES4348400001",
                                "ISRATIO", "RAILFRTINTERMODALD11"]}
m = pd.DataFrame(monthly)
for k, s in monthly.items():
    print(f"{k:22s} {s.index.min():%Y-%m} .. {s.index.max():%Y-%m}  n={len(s)}")

# peaks and latest vs peak since 2021
for k in ["TRUCKD11", "FRGSHPUSM649NCIS", "IPMAN", "TSIFRGHT"]:
    s = monthly[k]["2021":]
    pk = s.idxmax()
    print(f"{k:18s} peak {pk:%Y-%m}={s.max():.3f}  latest {s.index[-1]:%Y-%m}={s.iloc[-1]:.3f}  "
          f"vs peak {100 * (s.iloc[-1] / s.max() - 1):+.1f}%  min since peak {s[pk:].min():.3f} ({s[pk:].idxmin():%Y-%m})")

# Cass is NSA: compare YoY by month to avoid seasonality
cass = monthly["FRGSHPUSM649NCIS"]
cass_yoy = 100 * cass.pct_change(12)
neg = cass_yoy["2022":]
print(f"Cass shipments YoY: negative in {(neg < 0).sum()} of {neg.notna().sum()} months since 2022-01; "
      f"latest {cass_yoy.index[-1]:%Y-%m} {cass_yoy.iloc[-1]:+.1f}%")
print("Cass shipments annual mean:", cass.groupby(cass.index.year).mean().round(3).to_dict())

ppi_ltl, ppi_tl = monthly["PCU484122484122"], monthly["PCU484121484121"]
for lbl, d in [("2019-12", "2019-12-01"), ("2022-06", "2022-06-01"), ("latest", ppi_ltl.index[-1])]:
    print(f"PPI {lbl}: LTL={ppi_ltl[d]:.1f}  TL={ppi_tl[d]:.1f}")
print(f"PPI change 2022-06 -> latest: LTL {100 * (ppi_ltl.iloc[-1] / ppi_ltl['2022-06-01'] - 1):+.1f}%  "
      f"TL {100 * (ppi_tl.iloc[-1] / ppi_tl['2022-06-01'] - 1):+.1f}%")

diesel = fred("GASDESW").resample("MS").mean()
print("Diesel $/gal monthly avg: " + ", ".join(f"{d:%Y-%m}={v:.2f}" for d, v in diesel["2025-09":].items()))
print(f"PPI YoY latest: LTL {100 * ppi_ltl.pct_change(12).iloc[-1]:+.1f}%  TL {100 * ppi_tl.pct_change(12).iloc[-1]:+.1f}%")

fig, axes = plt.subplots(2, 2, figsize=(13, 8))
idx = lambda s, base="2019": 100 * s / s[base].mean()
ax = axes[0, 0]
for k, lab in [("TRUCKD11", "ATA truck tonnage (SA)"), ("IPMAN", "Industrial production: mfg (SA)"),
               ("TSIFRGHT", "BTS freight TSI (SA)")]:
    ax.plot(idx(monthly[k]["2015":]), label=lab)
ax.plot(idx(cass.rolling(12).mean()["2016":]), label="Cass shipments (NSA, 12-mo avg)")
shade(ax); ax.set_title("Freight volume vs manufacturing (2019 avg = 100)"); ax.legend(fontsize=8)
ax = axes[0, 1]
ax.plot(cass_yoy["2017":], color="C3"); ax.axhline(0, color="k", lw=0.8); shade(ax)
ax.set_title("Cass shipments, YoY % (NSA)")
ax = axes[1, 0]
ax.plot(idx(ppi_ltl["2015":]), label="PPI long-distance LTL"); ax.plot(idx(ppi_tl["2015":]), label="PPI long-distance TL")
shade(ax); ax.set_title("PPI: long-distance LTL vs TL trucking (2019 avg = 100)"); ax.legend(fontsize=8)
ax = axes[1, 1]
ax.plot(monthly["CES4348400001"]["2015":], color="C4"); shade(ax); ax.set_title("Truck transportation employment (000s, SA)")
fig.suptitle("US freight cycle; shaded = 2022-06 onward (post-peak downturn)")
fig.tight_layout(); fig.savefig(FIG / "01_freight_cycle.png", dpi=120); plt.close(fig)

# ---------------------------------------------------------------- 2. seasonality (Cass NSA)
section("2. Seasonality")
c = cass["2016":"2019"]  # pre-COVID, pre-downturn window for a clean seasonal profile
prof = (c / c.rolling(12, center=True).mean()).groupby(c.index.month).mean()
print("Cass shipments seasonal index 2016-2019 (ratio to centered 12-mo MA):", prof.round(3).to_dict())
stl = STL(np.log(cass), period=12, robust=True).fit()
seas_amp = (np.exp(stl.seasonal) - 1) * 100
print(f"STL on log Cass shipments: seasonal swing {seas_amp.min():.1f}% to {seas_amp.max():.1f}%")
trend = np.exp(stl.trend)
print(f"STL trend: {trend.idxmax():%Y-%m} peak {trend.max():.3f}; latest {trend.iloc[-1]:.3f} "
      f"({100 * (trend.iloc[-1] / trend.max() - 1):+.1f}% from peak)")
fig, axes = plt.subplots(1, 2, figsize=(13, 4))
axes[0].bar(prof.index, prof.values - 1); axes[0].set_xticks(range(1, 13)); axes[0].axhline(0, color="k", lw=0.8)
axes[0].set_title("Cass shipments seasonal factor by month (2016-2019)")
axes[1].plot(cass, alpha=0.4, label="Cass shipments (NSA)"); axes[1].plot(trend, label="STL trend"); shade(axes[1])
axes[1].legend(fontsize=8); axes[1].set_title("Cass shipments: raw vs STL trend")
fig.tight_layout(); fig.savefig(FIG / "02_seasonality.png", dpi=120); plt.close(fig)

# ---------------------------------------------------------------- 3. FedEx Freight KPIs
section("3. FedEx Freight segment (FedEx Corp releases, fiscal quarters)")
k = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"]).set_index("period_end")
k["ads_yoy"] = 100 * k["avg_daily_shipments_k"].pct_change(4)
k["rps_yoy"] = 100 * k["revenue_per_shipment_usd"].pct_change(4)
cols = ["fiscal_period", "revenue_musd", "operating_margin_pct", "avg_daily_shipments_k", "ads_yoy",
        "weight_per_shipment_lbs", "revenue_per_shipment_usd", "revenue_per_cwt_usd"]
print(k[cols].round(1).to_string())
pk = k["avg_daily_shipments_k"].idxmax()
print(f"ADS peak {k.loc[pk, 'fiscal_period']} {k['avg_daily_shipments_k'].max()}k; latest "
      f"{k['fiscal_period'].iloc[-1]} {k['avg_daily_shipments_k'].iloc[-1]}k "
      f"({100 * (k['avg_daily_shipments_k'].iloc[-1] / k['avg_daily_shipments_k'].max() - 1):+.1f}%)")
fy = k.groupby("fiscal_year").apply(lambda g: pd.Series({
    "n_q": len(g),
    "ads_k": (g["avg_daily_shipments_k"] * g["operating_days"]).sum() / g["operating_days"].sum(),
    "revenue_musd": g["revenue_musd"].sum(), "op_income_musd": g["operating_income_musd"].sum()}))
fy["op_margin_pct"] = 100 * fy["op_income_musd"] / fy["revenue_musd"]
print("Fiscal-year roll-up (days-weighted ADS):"); print(fy.round(1).to_string())
# FY2023 Q4 vs FY2022 Q4 etc: count consecutive negative ADS YoY quarters
neg = (k["ads_yoy"] < 0).astype(int)
run = neg.groupby((neg != neg.shift()).cumsum()).cumsum()
print(f"ADS YoY negative in {int(neg[k['ads_yoy'].notna()].sum())} of {int(k['ads_yoy'].notna().sum())} quarters; "
      f"current streak {int(run.iloc[-1])} quarters")

# quarterly macro aligned to FedEx fiscal quarters (period_end month = last month of quarter)
q = m.resample("QE-FEB").mean()  # quarters ending Feb/May/Aug/Nov = FedEx fiscal quarters
q.index = q.index.to_period("M").to_timestamp("M")
kk = k.copy(); kk.index = kk.index.to_period("M").to_timestamp("M")
j = kk.join(q, how="left")
j["ipman_yoy"] = 100 * j["IPMAN"].pct_change(4)
j["tonnage_yoy"] = 100 * j["TRUCKD11"].pct_change(4)
j["cass_yoy"] = 100 * j["FRGSHPUSM649NCIS"].pct_change(4)
print("Correlation of FedEx Freight ADS YoY with macro YoY (same quarter, and macro leading 1-2 quarters):")
for c_ in ["ipman_yoy", "tonnage_yoy", "cass_yoy"]:
    r = {lag: j["ads_yoy"].corr(j[c_].shift(lag)) for lag in (0, 1, 2)}
    n = j[["ads_yoy", c_]].dropna().shape[0]
    print(f"  {c_:12s} n={n}  " + "  ".join(f"lead{l}={v:+.2f}" for l, v in r.items()))
print("  (n is small and COVID base effects dominate - treat as descriptive only)")
ex = j[(j.index < "2020-03-01") | (j.index > "2021-11-30")]
print("Same, excluding FY2020Q3-FY2022Q2 (COVID base effects), same quarter:")
for c_ in ["ipman_yoy", "tonnage_yoy", "cass_yoy"]:
    d = ex[["ads_yoy", c_]].dropna()
    print(f"  {c_:12s} n={len(d)}  r={d.corr().iloc[0, 1]:+.2f}")
print("Downturn quarters: FedEx Freight ADS YoY vs macro YoY (%):")
print(j.loc["2022-05-31":, ["fiscal_period", "ads_yoy", "ipman_yoy", "tonnage_yoy", "cass_yoy"]].round(1).to_string())

fig, axes = plt.subplots(2, 2, figsize=(13, 8))
x = k.index
axes[0, 0].plot(x, k["avg_daily_shipments_k"], marker="o", ms=3); shade(axes[0, 0])
axes[0, 0].set_title("Average daily shipments (000s)")
axes[0, 1].plot(x, k["weight_per_shipment_lbs"], marker="o", ms=3, color="C1"); shade(axes[0, 1])
axes[0, 1].set_title("Weight per shipment (lbs)")
axes[1, 0].plot(x, k["revenue_per_shipment_usd"], marker="o", ms=3, label="Revenue/shipment ($)", color="C2")
ax2 = axes[1, 0].twinx(); ax2.plot(x, k["revenue_per_cwt_usd"], marker="o", ms=3, color="C3", label="Revenue/cwt ($, right)")
axes[1, 0].set_title("Yield: revenue per shipment & per hundredweight"); shade(axes[1, 0])
axes[1, 0].legend(loc="upper left", fontsize=8); ax2.legend(loc="lower right", fontsize=8)
axes[1, 1].bar(x, k["operating_margin_pct"], width=60, color="C4"); shade(axes[1, 1])
axes[1, 1].set_title("Operating margin % (segment, incl. spin-off costs from FY26)")
fig.suptitle("FedEx Freight segment, fiscal quarters FY2017Q4-FY2026Q4 (source: FedEx Corp 8-K earnings releases)")
fig.tight_layout(); fig.savefig(FIG / "03_fedex_freight_kpis.png", dpi=120); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(j.index, j["ads_yoy"], marker="o", ms=3, label="FedEx Freight ADS YoY %")
ax.plot(j.index, j["ipman_yoy"], label="Industrial production: mfg YoY %")
ax.plot(j.index, j["tonnage_yoy"], label="ATA truck tonnage YoY %")
ax.axhline(0, color="k", lw=0.8); shade(ax); ax.legend(fontsize=8)
ax.set_title("FedEx Freight volume vs macro, fiscal-quarter aligned")
fig.tight_layout(); fig.savefig(FIG / "04_fedex_vs_macro_yoy.png", dpi=120); plt.close(fig)

# ---------------------------------------------------------------- 4. FAF5 regional/commodity
section("4. FAF5 (annual, truck mode)")
faf = pd.read_parquet(PROC / "faf5_7_1.parquet",
                      columns=["dms_orig", "dms_dest", "dms_mode", "sctg2", "trade_type", "dist_band"]
                      + [f"tons_{y}" for y in range(2017, 2025)] + [f"value_{y}" for y in range(2017, 2025)])
meta = pd.ExcelFile(RAW / "faf5/FAF5_metadata.xlsx")
sctg = pd.read_excel(meta, "Commodity (SCTG2)").set_index("Numeric Label")["Description"]
zones = pd.read_excel(meta, "FAF Zone (Domestic)").set_index("Numeric Label")["Short Description"]
truck = faf[faf["dms_mode"] == "1"]
yrs = [f"tons_{y}" for y in range(2017, 2025)]
tot = truck[yrs].sum() / 1e3
print("Truck tons (million) by year:", tot.round(0).to_dict())
print(f"Truck share of all tons 2024: {100 * truck['tons_2024'].sum() / faf['tons_2024'].sum():.1f}%")
by_c = truck.groupby("sctg2", observed=True)[["tons_2022", "tons_2024", "value_2022", "value_2024"]].sum()
by_c.index = by_c.index.astype(int).map(sctg)
by_c["tons_chg_pct"] = 100 * (by_c["tons_2024"] / by_c["tons_2022"] - 1)
by_c["value_per_ton_2024"] = 1e3 * by_c["value_2024"] / by_c["tons_2024"]  # $M / kt -> $/ton
print("Truck tons by commodity, 2022 -> 2024 (top 15 by 2024 value):")
print(by_c.sort_values("value_2024", ascending=False).head(15)[["tons_2024", "tons_chg_pct", "value_per_ton_2024"]].round(1).to_string())
by_o = truck.groupby("dms_orig", observed=True)[["tons_2022", "tons_2024"]].sum()
by_o.index = by_o.index.astype(int).map(zones)
by_o["chg_pct"] = 100 * (by_o["tons_2024"] / by_o["tons_2022"] - 1)
big = by_o[by_o["tons_2024"] > by_o["tons_2024"].quantile(0.5)]
print("Largest origin-zone declines 2022->2024 (zones above median size):")
print(big.sort_values("chg_pct").head(8).round(1).to_string())
print("Largest origin-zone gains:"); print(big.sort_values("chg_pct").tail(5).round(1).to_string())
memphis = by_o.loc[[z for z in by_o.index if "Memphis" in str(z)]]
print("Memphis zone:"); print(memphis.round(1).to_string())
# distance bands: LTL linehaul economics are mid/long haul
bd = truck.groupby("dist_band", observed=True)[["tons_2024", "value_2024"]].sum()
print("Truck 2024 tons/value share by distance band (%):")
print((100 * bd / bd.sum()).round(1).to_string())

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
top = by_c.sort_values("value_2024", ascending=False).head(15).sort_values("tons_chg_pct")
axes[0].barh(top.index, top["tons_chg_pct"], color=np.where(top["tons_chg_pct"] < 0, "C3", "C2"))
axes[0].axvline(0, color="k", lw=0.8); axes[0].set_title("Truck tons % change 2022->2024\n(top 15 commodities by 2024 value)")
axes[1].plot(range(2017, 2025), tot.values, marker="o"); axes[1].set_title("Total truck tons (million), FAF5.7.1")
axes[1].set_xticks(range(2017, 2025))
fig.tight_layout(); fig.savefig(FIG / "05_faf5_truck_commodities.png", dpi=120); plt.close(fig)
print("\nfigures written to", FIG)
