"""Option C: where is LTL-addressable truck freight growing? (FAF5.7.1, annual, 2017-2024 + forecasts)

LTL carriers move packaged, higher-value manufactured goods, not bulk. FAF does not split LTL from
truckload, so this script builds an explicit, documented "LTL-addressable" proxy and then asks:
  1. Does the proxy track FedEx Freight's own tonnage better than all truck tons do?
  2. Shift-share 2019->2024 by origin state: national trend vs commodity mix vs regional effect.
  3. Which state-to-state lanes are forecast to add the most addressable freight by 2035?
  4. Directional imbalance (outbound vs inbound) by state - the headhaul/backhaul problem.
  5. Cluster FAF zones by growth and commodity profile.
Run from the project root: .venv/bin/python -I scripts/option_c_faf_lanes.py
"""
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data/raw", ROOT / "data/processed"
OUT = ROOT / "reports/option_c"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 220)

# Packaged / finished / mixed goods that move LTL. Bulk (grain, gravel, coal, fuels, logs, ores,
# fertilizer, base metals, newsprint rolls, scrap) is excluded: it moves truckload, rail or pipeline.
LTL_SCTG = [7, 8, 9, 21, 23, 24, 26, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38, 39, 40, 43]
HIST = list(range(2017, 2025))
FCST = [2030, 2035, 2040, 2045, 2050]

meta = RAW / "faf5/FAF5_metadata.xlsx"
sctg_name = pd.read_excel(meta, sheet_name="Commodity (SCTG2)").set_index("Numeric Label")["Description"]
zone_name = pd.read_excel(meta, sheet_name="FAF Zone (Domestic)").set_index("Numeric Label")["Short Description"]
state_name = pd.read_excel(meta, sheet_name="State").set_index("Numeric Label")["Description"]
ABBR = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
        "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Washington DC": "DC", "Florida": "FL", "Georgia": "GA",
        "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
        "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
        "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
        "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
        "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
        "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
        "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
        "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"}
st_abbr = state_name.map(ABBR)
results = {}


def section(t):
    print(f"\n=== {t} ===")


# ------------------------------------------------------------------ load + proxy definition
cols = ["dms_orig", "dms_dest", "dms_mode", "sctg2", "dist_band"] + [f"tons_{y}" for y in HIST + FCST] \
    + [f"value_{y}" for y in HIST + FCST] + [f"tmiles_{y}" for y in HIST + FCST]
faf = pd.read_parquet(PROC / "faf5_7_1.parquet", columns=cols)
truck = faf[faf["dms_mode"] == "1"].copy()
for c in ["dms_orig", "dms_dest", "sctg2", "dist_band"]:
    truck[c] = truck[c].astype(int)
truck["o_state"] = truck["dms_orig"] // 10
truck["d_state"] = truck["dms_dest"] // 10
truck["ltl"] = truck["sctg2"].isin(LTL_SCTG)
truck["linehaul"] = truck["dist_band"] >= 3  # 250+ miles: where LTL linehaul economics live

section("1. LTL-addressable proxy")
g = truck.groupby("ltl")[["tons_2024", "value_2024", "tmiles_2024"]].sum()
g["value_per_ton"] = 1e3 * g["value_2024"] / g["tons_2024"]
g["avg_miles"] = 1e3 * g["tmiles_2024"] / g["tons_2024"]  # Mton-miles / ktons -> miles
g["share_tons_pct"] = 100 * g["tons_2024"] / g["tons_2024"].sum()
g["share_value_pct"] = 100 * g["value_2024"] / g["value_2024"].sum()
print(g.round(1).to_string())
results["proxy"] = {"ltl_share_of_truck_tons_2024_pct": round(g.loc[True, "share_tons_pct"], 1),
                    "ltl_share_of_truck_value_2024_pct": round(g.loc[True, "share_value_pct"], 1),
                    "ltl_value_per_ton": round(g.loc[True, "value_per_ton"]),
                    "non_ltl_value_per_ton": round(g.loc[False, "value_per_ton"])}

# ------------------------------------------------------------------ 1. does the proxy track FedEx?
section("2. Proxy vs FedEx Freight tonnage")
yrs = [f"tons_{y}" for y in HIST]
series = pd.DataFrame({
    "all_truck": truck[yrs].sum().values,
    "ltl_proxy": truck.loc[truck["ltl"], yrs].sum().values,
    "ltl_proxy_250mi": truck.loc[truck["ltl"] & truck["linehaul"], yrs].sum().values,
    "bulk_truck": truck.loc[~truck["ltl"], yrs].sum().values}, index=HIST)
k = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"])
k["tons"] = k["avg_daily_shipments_k"] * 1e3 * k["weight_per_shipment_lbs"] * k["operating_days"] / 2000
# calendar-year FedEx tonnage: fiscal quarters ending Feb/May/Aug/Nov; assign each quarter to the calendar year
# holding most of its months (Dec-Feb quarter -> year of its Feb end), then require 4 quarters per year.
k["cal_year"] = k["period_end"].dt.year
cy = k.groupby("cal_year").agg(tons=("tons", "sum"), n=("tons", "size"))
series["fedex_freight"] = cy.loc[cy["n"] == 4, "tons"].reindex(HIST)
idx = 100 * series / series.loc[2019]
print("Index, 2019 = 100:"); print(idx.round(1).to_string())
chg = idx.diff()
corr = chg.corr()["fedex_freight"].drop("fedex_freight")
print("Correlation of annual index changes with FedEx Freight tonnage (n<=6 years - descriptive):")
print(corr.round(2).to_string())
results["proxy_vs_fedex"] = {"index_2019_100": idx.round(1).reset_index().to_dict(orient="list"),
                             "corr_annual_changes": corr.round(2).to_dict()}

# sensitivity: does the conclusion depend on which commodities count as LTL-addressable?
VARIANTS = {"strict (chem/plastics/metal goods/machinery/electronics/vehicles/instruments/furniture/misc/mixed)":
            [21, 23, 24, 33, 34, 35, 36, 37, 38, 39, 40, 43],
            "baseline": LTL_SCTG,
            "broad (+ bulk-ish packaged: milled grain, basic chem, newsprint, base metals)": LTL_SCTG + [6, 20, 27, 32]}
sens = {}
for name, codes in VARIANTS.items():
    s_ = truck.loc[truck["sctg2"].isin(codes), yrs].sum().values
    ix = pd.Series(100 * s_ / s_[HIST.index(2019)], index=HIST)
    c_ = ix.diff().corr(series["fedex_freight"].pipe(lambda x: 100 * x / x.loc[2019]).diff())
    sens[name] = {"index_2024": round(ix.loc[2024], 1), "corr_with_fedex": round(c_, 2)}
print("Proxy definition sensitivity (index 2024, 2019=100; corr of annual changes with FedEx):")
for n_, v_ in sens.items():
    print(f"  {v_['index_2024']:6.1f}  r={v_['corr_with_fedex']:+.2f}  {n_}")
results["proxy_sensitivity"] = sens

fig, ax = plt.subplots(figsize=(8, 4.5))
for c, lab in [("all_truck", "All truck tons (FAF)"), ("ltl_proxy", "LTL-addressable proxy (FAF)"),
               ("ltl_proxy_250mi", "LTL-addressable, 250+ mi (FAF)"), ("fedex_freight", "FedEx Freight tons (8-K)")]:
    ax.plot(idx.index, idx[c], marker="o", label=lab, lw=2.5 if c == "fedex_freight" else 1.5)
ax.axhline(100, color="0.6", lw=0.8)
ax.set_title("Freight tonnage index (2019 = 100): FAF proxies vs FedEx Freight")
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(FIG / "c1_proxy_vs_fedex.png", dpi=130); plt.close(fig)

# ------------------------------------------------------------------ 2. shift-share by origin state
section("3. Shift-share 2019 -> 2024, LTL-addressable tons by origin state")
base, end = "tons_2019", "tons_2024"
L = truck[truck["ltl"]]
sc = L.groupby(["o_state", "sctg2"])[[base, end]].sum()
nat_g = sc[end].sum() / sc[base].sum() - 1
ind_g = sc.groupby(level="sctg2")[end].sum() / sc.groupby(level="sctg2")[base].sum() - 1
sc = sc.join(ind_g.rename("ind_g"), on="sctg2")
sc["reg_g"] = sc[end] / sc[base].where(sc[base] > 0) - 1
sc["national"] = sc[base] * nat_g
sc["mix"] = sc[base] * (sc["ind_g"] - nat_g)
sc["regional"] = sc[base] * (sc["reg_g"].fillna(0) - sc["ind_g"])
ss = sc.groupby(level="o_state")[[base, end, "national", "mix", "regional"]].sum()
ss["actual_chg"] = ss[end] - ss[base]
ss["check"] = ss["national"] + ss["mix"] + ss["regional"] - ss["actual_chg"]
assert ss["check"].abs().max() < 1.0, "shift-share does not add up"
for c in ["actual_chg", "national", "mix", "regional"]:
    ss[c + "_pct"] = 100 * ss[c] / ss[base]
ss.index = ss.index.map(st_abbr)
print(f"National LTL-addressable growth 2019->2024: {100 * nat_g:+.1f}%")
print("Commodity growth 2019->2024 (%):")
print((100 * ind_g).rename(index=sctg_name).sort_values().round(1).to_string())
show = ss.sort_values("regional_pct")[["tons_2024", "actual_chg_pct", "national_pct", "mix_pct", "regional_pct"]]
print("Weakest regional effects:"); print(show.head(8).round(1).to_string())
print("Strongest regional effects:"); print(show.tail(8).round(1).to_string())
ss.to_csv(OUT / "shift_share_by_state.csv")
results["shift_share"] = {"national_growth_pct": round(100 * nat_g, 1),
                          "weakest": show.head(5)["regional_pct"].round(1).to_dict(),
                          "strongest": show.tail(5)["regional_pct"].round(1).to_dict()}

# tile-grid map of the regional (competitive) effect
TILE = {"AK": (0, 0), "ME": (0, 11), "VT": (1, 10), "NH": (1, 11), "WA": (2, 1), "ID": (2, 2), "MT": (2, 3),
        "ND": (2, 4), "MN": (2, 5), "IL": (2, 6), "WI": (2, 7), "MI": (2, 8), "NY": (2, 9), "MA": (2, 10),
        "OR": (3, 1), "NV": (3, 2), "WY": (3, 3), "SD": (3, 4), "IA": (3, 5), "IN": (3, 6), "OH": (3, 7),
        "PA": (3, 8), "NJ": (3, 9), "CT": (3, 10), "RI": (3, 11), "CA": (4, 1), "UT": (4, 2), "CO": (4, 3),
        "NE": (4, 4), "MO": (4, 5), "KY": (4, 6), "WV": (4, 7), "VA": (4, 8), "MD": (4, 9), "DE": (4, 10),
        "AZ": (5, 2), "NM": (5, 3), "KS": (5, 4), "AR": (5, 5), "TN": (5, 6), "NC": (5, 7), "SC": (5, 8),
        "DC": (5, 9), "OK": (6, 4), "LA": (6, 5), "MS": (6, 6), "AL": (6, 7), "GA": (6, 8), "HI": (7, 0),
        "TX": (7, 4), "FL": (7, 8)}


def tile_map(values, title, fname, cmap="RdBu", fmt="{:+.0f}"):
    fig, ax = plt.subplots(figsize=(10, 6.5))
    v = values.dropna()
    lim = np.nanpercentile(np.abs(v), 95)
    norm = matplotlib.colors.TwoSlopeNorm(vmin=-lim, vcenter=0, vmax=lim)
    cm = plt.get_cmap(cmap)
    for st, (r, c) in TILE.items():
        val = values.get(st, np.nan)
        color = "0.9" if pd.isna(val) else cm(norm(np.clip(val, -lim, lim)))
        ax.add_patch(plt.Rectangle((c, -r), 0.95, 0.95, color=color))
        ax.text(c + 0.47, -r + 0.6, st, ha="center", va="center", fontsize=9, weight="bold")
        if not pd.isna(val):
            ax.text(c + 0.47, -r + 0.28, fmt.format(val), ha="center", va="center", fontsize=7.5)
    ax.set_xlim(-0.2, 12.2); ax.set_ylim(-7.2, 1.2); ax.axis("off"); ax.set_title(title)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cm); fig.colorbar(sm, ax=ax, shrink=0.6)
    fig.tight_layout(); fig.savefig(FIG / fname, dpi=130); plt.close(fig)


tile_map(ss["regional_pct"], "Shift-share regional effect, LTL-addressable truck tons by origin, 2019->2024\n"
         "(% of 2019 tons; growth not explained by the national trend or commodity mix)", "c2_shift_share_map.png")

# ------------------------------------------------------------------ 3. lane growth forecasts
section("4. Forecast lane growth 2024 -> 2035 (FAF mid-range), LTL-addressable, 250+ mi, state pairs")
lanes = L[L["linehaul"]].groupby(["o_state", "d_state"])[["tons_2024", "tons_2035", "tmiles_2024", "tmiles_2035"]].sum()
lanes = lanes[lanes.index.get_level_values(0) != lanes.index.get_level_values(1)]
lanes["add_ktons"] = lanes["tons_2035"] - lanes["tons_2024"]
lanes["cagr_pct"] = 100 * ((lanes["tons_2035"] / lanes["tons_2024"]) ** (1 / 11) - 1)
lanes.index = [f"{st_abbr[o]}->{st_abbr[d]}" for o, d in lanes.index]
top = lanes.sort_values("add_ktons", ascending=False).head(15)
print(top[["tons_2024", "tons_2035", "add_ktons", "cagr_pct"]].round(1).to_string())
tot_cagr = 100 * ((lanes["tons_2035"].sum() / lanes["tons_2024"].sum()) ** (1 / 11) - 1)
print(f"All interstate 250+ mi LTL-addressable lanes: CAGR 2024->2035 = {tot_cagr:.2f}%/yr")
lanes.to_csv(OUT / "lane_forecast_state_pairs.csv")
results["lanes"] = {"cagr_2024_2035_pct": round(tot_cagr, 2),
                    "top10_add_ktons": top.head(10)["add_ktons"].round(0).to_dict()}
fig, ax = plt.subplots(figsize=(8, 5.5))
t = top.sort_values("add_ktons")
ax.barh(t.index, t["add_ktons"] / 1e3, color="C0")
for i, (a, cg) in enumerate(zip(t["add_ktons"], t["cagr_pct"])):
    ax.text(a / 1e3, i, f"  {cg:.1f}%/yr", va="center", fontsize=8)
ax.set_xlabel("Added tons 2024->2035 (millions)")
ax.set_title("Top 15 interstate lanes by forecast growth\nLTL-addressable truck freight, 250+ miles (FAF5 mid-range)")
fig.tight_layout(); fig.savefig(FIG / "c3_top_lanes_2035.png", dpi=130); plt.close(fig)

# ------------------------------------------------------------------ 4. directional imbalance
section("5. Directional imbalance 2024 (LTL-addressable, interstate 250+ mi)")
inter = L[L["linehaul"] & (L["o_state"] != L["d_state"])]
outb = inter.groupby("o_state")["tons_2024"].sum()
inb = inter.groupby("d_state")["tons_2024"].sum()
imb = pd.DataFrame({"outbound": outb, "inbound": inb}).fillna(0)
imb["out_in_ratio"] = imb["outbound"] / imb["inbound"]
imb["net_pct"] = 100 * (imb["outbound"] - imb["inbound"]) / (imb["outbound"] + imb["inbound"])
imb.index = imb.index.map(st_abbr)
print("Most outbound-heavy (headhaul origins):"); print(imb.sort_values("net_pct").tail(6).round(2).to_string())
print("Most inbound-heavy (empty-backhaul risk):"); print(imb.sort_values("net_pct").head(6).round(2).to_string())
print("Tennessee:"); print(imb.loc[["TN"]].round(2).to_string())
imb.to_csv(OUT / "directional_imbalance_by_state.csv")
results["imbalance"] = {"TN": imb.loc["TN", ["out_in_ratio", "net_pct"]].round(2).to_dict(),
                        "most_inbound": imb.sort_values("net_pct").head(5)["net_pct"].round(1).to_dict(),
                        "most_outbound": imb.sort_values("net_pct").tail(5)["net_pct"].round(1).to_dict()}
tile_map(imb["net_pct"], "Directional balance 2024, interstate LTL-addressable truck freight (250+ mi)\n"
         "(outbound - inbound) / total, %: blue = net shipper (headhaul), red = net receiver (backhaul)",
         "c4_imbalance_map.png")

# ------------------------------------------------------------------ 5. cluster FAF zones
section("6. Clustering FAF zones")
Z = L.groupby("dms_orig")[[f"tons_{y}" for y in (2019, 2024, 2035)] + ["value_2024", "tmiles_2024"]].sum()
groups = {"food_bev": [7, 8, 9], "chem_plastic_pharma": [21, 23, 24], "wood_paper_print": [26, 28, 29],
          "metal_machinery": [31, 33, 34], "electronics_instruments": [35, 38], "vehicles_transport": [36, 37],
          "furniture_misc": [30, 39, 40], "mixed_freight": [43]}
mix = L.groupby(["dms_orig", "sctg2"])["tons_2024"].sum().unstack(fill_value=0)
for gname, codes in groups.items():
    Z["share_" + gname] = mix[[c for c in codes if c in mix.columns]].sum(axis=1) / mix.sum(axis=1)
Z["hist_growth"] = Z["tons_2024"] / Z["tons_2019"] - 1
Z["fcst_cagr"] = (Z["tons_2035"] / Z["tons_2024"]) ** (1 / 11) - 1
Z["value_per_ton"] = Z["value_2024"] / Z["tons_2024"]
Z["avg_miles"] = Z["tmiles_2024"] / Z["tons_2024"]
Z["log_size"] = np.log(Z["tons_2024"])
feats = ["hist_growth", "fcst_cagr", "value_per_ton", "avg_miles", "log_size"] + [c for c in Z if c.startswith("share_")]
X = StandardScaler().fit_transform(Z[feats])
scores = {}
for kk in range(3, 9):
    lab = KMeans(n_clusters=kk, n_init=20, random_state=0).fit_predict(X)
    scores[kk] = silhouette_score(X, lab)
print("Silhouette by k:", {kk: round(v, 3) for kk, v in scores.items()})
best_k = max(scores, key=scores.get)
km = KMeans(n_clusters=best_k, n_init=20, random_state=0).fit(X)
Z["cluster"] = km.labels_
Z["zone"] = Z.index.astype(int).map(zone_name)
# stability: re-run with different seeds and measure label agreement (adjusted Rand)
from sklearn.metrics import adjusted_rand_score
ari = [adjusted_rand_score(km.labels_, KMeans(n_clusters=best_k, n_init=20, random_state=s).fit_predict(X))
       for s in range(1, 6)]
print(f"best k={best_k}; seed stability ARI mean={np.mean(ari):.2f}")
print("Verdict: silhouette < 0.25 means weak cluster structure - zones form a continuum, so clusters are used\n"
      "only as a descriptive segmentation; the growth quadrant chart (history vs forecast) carries the message.")
prof = Z.groupby("cluster")[feats].mean()
prof["n_zones"] = Z.groupby("cluster").size()
prof["tons_2024_m"] = Z.groupby("cluster")["tons_2024"].sum() / 1e3
print(prof.round(3).to_string())
for c_ in sorted(Z["cluster"].unique()):
    ex = Z[Z["cluster"] == c_].sort_values("tons_2024", ascending=False)["zone"].head(6).tolist()
    print(f"cluster {c_}: {ex}")
Z.to_csv(OUT / "zone_clusters.csv")
results["clusters"] = {"best_k": best_k, "silhouette": round(scores[best_k], 3), "ari_seed_stability": round(float(np.mean(ari)), 2)}

fig, ax = plt.subplots(figsize=(8, 5.5))
sc_ = ax.scatter(100 * Z["hist_growth"], 100 * Z["fcst_cagr"], s=Z["tons_2024"] / 400, c=Z["cluster"], cmap="tab10", alpha=0.7)
for _, r in Z.sort_values("tons_2024", ascending=False).head(12).iterrows():
    ax.annotate(r["zone"], (100 * r["hist_growth"], 100 * r["fcst_cagr"]), fontsize=7)
mem = Z[Z["zone"].str.contains("Memphis")]
for _, r in mem.iterrows():
    ax.annotate(r["zone"], (100 * r["hist_growth"], 100 * r["fcst_cagr"]), fontsize=8, color="red", weight="bold")
ax.axvline(100 * nat_g, color="0.6", lw=0.8); ax.axhline(100 * Z["fcst_cagr"].median(), color="0.6", lw=0.8)
ax.set_xlabel("Actual growth 2019->2024 (%)"); ax.set_ylabel("FAF forecast CAGR 2024->2035 (%/yr)")
ax.set_title(f"FAF zones: LTL-addressable outbound tons (bubble = 2024 size, color = cluster, k={best_k})")
fig.tight_layout(); fig.savefig(FIG / "c5_zone_clusters.png", dpi=130); plt.close(fig)

# ------------------------------------------------------------------ 6. Memphis
section("7. Memphis zone")
mz = [z for z, n in zone_name.items() if "Memphis" in str(n)]
for z in mz:
    o = L[L["dms_orig"] == z]; d = L[L["dms_dest"] == z]
    oc = o.groupby("sctg2")["tons_2024"].sum().sort_values(ascending=False).head(5)
    print(f"{zone_name[z]}: outbound {o['tons_2024'].sum():,.0f} kt, inbound {d['tons_2024'].sum():,.0f} kt, "
          f"2019->2024 outbound {100 * (o['tons_2024'].sum() / o['tons_2019'].sum() - 1):+.1f}%, "
          f"2024->2035 outbound CAGR {100 * ((o['tons_2035'].sum() / o['tons_2024'].sum()) ** (1 / 11) - 1):.2f}%")
    print("  top outbound commodities:", {sctg_name[c]: round(v) for c, v in oc.items()})
    print("  cluster:", Z.loc[Z.index.astype(int) == z, "cluster"].tolist())

(OUT / "results.json").write_text(json.dumps(results, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print("\nwritten:", OUT)
