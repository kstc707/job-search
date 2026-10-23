"""Option D: what is a point of volume (or price) worth? Operating leverage and valuation sensitivity.

YoY change in adjusted segment operating income (separation costs added back) is regressed on the YoY
revenue change split into a VOLUME part (shipments x days at last year's revenue/shipment) and a PRICE/MIX
part (the rest, including fuel). The two slopes are the incremental margins on volume and on price - the
numbers behind FedEx Freight's yield-vs-share trade-off. They are then turned into dollars of operating income
and an illustrative equity value per share at the market multiple found in public sources.
Run from the project root: .venv/bin/python -I scripts/option_d_value_sensitivity.py
"""
import json
import pathlib

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC = ROOT / "data/processed"
OUT = ROOT / "reports/option_d"
OUT.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 200)

k = pd.read_csv(PROC / "fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"]).set_index("fiscal_period")
rows = pd.read_csv(PROC / "_fedex_corp_segment_rows.csv")
sep = rows[rows["label"] == "Separation and other costs"].copy()
sep["fiscal_period"] = "FY" + sep["fiscal_year"].astype(str) + "Q" + sep["fiscal_quarter"].astype(str)
k["separation_musd"] = sep.set_index("fiscal_period")["value"].reindex(k.index).fillna(0)
k["adj_oi"] = k["operating_income_musd"] + k["separation_musd"]
fuel_exp = rows[rows["label"] == "Fuel"].copy()
fuel_exp["fiscal_period"] = "FY" + fuel_exp["fiscal_year"].astype(str) + "Q" + fuel_exp["fiscal_quarter"].astype(str)
k["fuel_expense_musd"] = fuel_exp.drop_duplicates("fiscal_period").set_index("fiscal_period")["value"].reindex(k.index)
print("FY2026 separation costs by quarter:", k.loc["FY2026Q1":, "separation_musd"].to_dict(),
      "sum", k.loc["FY2026Q1":, "separation_musd"].sum())

# ------------------------------------------------------------------ volume vs price split of YoY revenue change
vol = k["avg_daily_shipments_k"] * k["operating_days"]
rev_prior = k["revenue_musd"].shift(4)
d = pd.DataFrame({
    "d_oi": k["adj_oi"].diff(4),
    "d_rev_volume": rev_prior * np.log(vol / vol.shift(4)),
    "d_rev_price": rev_prior * np.log(k["revenue_per_shipment_usd"] / k["revenue_per_shipment_usd"].shift(4)),
    "d_rev": k["revenue_musd"].diff(4),
}).dropna()
covid = d.index.isin(["FY2020Q4", "FY2021Q1", "FY2021Q2", "FY2021Q3", "FY2021Q4", "FY2022Q1"])
X = sm.add_constant(d[["d_rev_volume", "d_rev_price"]])
res = {}
for label, mask in [("all", np.ones(len(d), bool)), ("ex_covid", ~covid)]:
    m = sm.OLS(d.loc[mask, "d_oi"], X[mask]).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    ci = m.conf_int()
    print(f"\n[{label}] n={int(m.nobs)} R2={m.rsquared:.2f}")
    print(f"  incremental margin on VOLUME revenue: {m.params['d_rev_volume']:.2f} "
          f"(95% CI {ci.loc['d_rev_volume', 0]:.2f} to {ci.loc['d_rev_volume', 1]:.2f})")
    print(f"  incremental margin on PRICE/MIX revenue: {m.params['d_rev_price']:.2f} "
          f"(95% CI {ci.loc['d_rev_price', 0]:.2f} to {ci.loc['d_rev_price', 1]:.2f})")
    print(f"  constant (cost drift per quarter, $M YoY): {m.params['const']:.1f}")
    res[label] = {"n": int(m.nobs), "r2": round(m.rsquared, 2),
                  "volume_margin": round(m.params["d_rev_volume"], 2),
                  "volume_ci": [round(ci.loc["d_rev_volume", 0], 2), round(ci.loc["d_rev_volume", 1], 2)],
                  "price_margin": round(m.params["d_rev_price"], 2),
                  "price_ci": [round(ci.loc["d_rev_price", 0], 2), round(ci.loc["d_rev_price", 1], 2)],
                  "const": round(m.params["const"], 1)}

# ------------------------------------------------------------------ dollars and illustrative value
best = res["ex_covid"]
annual_rev = k.loc["FY2026Q1":"FY2026Q4", "revenue_musd"].sum()
adj_oi_fy26 = k.loc["FY2026Q1":"FY2026Q4", "adj_oi"].sum()
one_pt_rev = annual_rev / 100
oi_per_vol_pt = best["volume_margin"] * one_pt_rev
oi_per_price_pt = best["price_margin"] * one_pt_rev
# market inputs from reports/external_benchmarks.md (StockAnalysis 2026-10-22, gross debt at spin $4.3B)
price, shares, debt = 111.02, 149.52, 4300.0
ev = price * shares + debt
multiple = ev / adj_oi_fy26
value_per_vol_pt = oi_per_vol_pt * multiple / shares
breakeven = best["price_margin"] / best["volume_margin"]
print(f"\nFY2026 revenue ${annual_rev:,.0f}M, adjusted op. income ${adj_oi_fy26:,.0f}M "
      f"(Investor Day baseline ~$1.1B)")
print(f"1 pt of shipments ~ ${one_pt_rev:.0f}M revenue -> ~${oi_per_vol_pt:.0f}M op. income/yr")
print(f"1 pt of price      ~ ${one_pt_rev:.0f}M revenue -> ~${oi_per_price_pt:.0f}M op. income/yr")
print(f"break-even: 1 pt of price offsets ~{breakeven:.1f} pts of lost shipments")
print(f"illustrative EV ${ev:,.0f}M = {multiple:.1f}x FY26 adj. op. income -> 1 pt of shipments ~ ${value_per_vol_pt:.2f}/share")
res["dollars"] = {"fy26_revenue": annual_rev, "fy26_adj_oi": adj_oi_fy26, "oi_per_volume_pt": round(oi_per_vol_pt),
                  "oi_per_price_pt": round(oi_per_price_pt), "price_pts_to_offset_1pt_volume": round(1 / breakeven, 2),
                  "volume_pts_offset_by_1pt_price": round(breakeven, 1), "ev_musd": round(ev),
                  "ev_to_adj_oi": round(multiple, 1), "value_per_volume_pt_per_share": round(value_per_vol_pt, 2),
                  "market_inputs": {"price": price, "shares_m": shares, "gross_debt_musd": debt,
                                    "source": "StockAnalysis 2026-10-22; debt at spin per Investor Day (see external_benchmarks.md)"}}

# ------------------------------------------------------------------ did yield-first pay? FY2023-FY2026 scorecard
sc = d.loc["FY2023Q1":, ["d_rev_volume", "d_rev_price", "d_oi"]].copy()
sc["oi_from_volume"] = best["volume_margin"] * sc["d_rev_volume"]
sc["oi_from_price"] = best["price_margin"] * sc["d_rev_price"]
yr = sc.groupby(lambda p: p[:6]).sum()
print("\nYoY adjusted op. income attributed to volume vs price/mix ($M, by fiscal year):")
print(yr[["d_rev_volume", "d_rev_price", "oi_from_volume", "oi_from_price", "d_oi"]].round(0).to_string())
res["scorecard_by_fy"] = yr.round(0).to_dict(orient="index")

# ------------------------------------------------------------------ fuel: surcharge revenue vs fuel expense
ob = json.loads((ROOT / "reports/option_b/results.json").read_text())
rho = ob["fuel_model"]["rho_mean"]
print(f"\n(fuel model rho = {rho}; see option_b) - fuel expense line, $M:", k.loc["FY2025Q1":, "fuel_expense_musd"].to_dict())
(OUT / "results.json").write_text(json.dumps(res, indent=2, default=float))
d.to_csv(OUT / "volume_price_oi_yoy.csv")
