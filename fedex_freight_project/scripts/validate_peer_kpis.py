"""Validation checks for the peer LTL KPI tables built by parse_peer_kpis.py.

Checks (each prints PASS/FLAG lines; the full report goes to data/processed/_peer_validation_report.txt):
  1. totals / workdays  == reported per-day values         (shipments, tonnage)
  2. tons/day x 2000 / shipments/day == weight per shipment (identity, <1.5%)
  3. 100 x (1 - operating income / revenue) == operating ratio (<0.25 pp)
  4. sum of four quarters == full-year column of the Q4 release (revenue, operating income)
  5. prior-year column of each release vs the value originally reported (restatements)
  6. mean of monthly YoY % (mid-quarter updates) vs quarterly YoY % from quarterly per-day values

Usage: python scripts/validate_peer_kpis.py data/processed
"""
import io
import pathlib
import sys
from contextlib import redirect_stdout

import pandas as pd

P = pathlib.Path(sys.argv[1])
pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 200)


def run():
    q = pd.read_csv(P / "peer_ltl_quarterly_kpis.csv")
    audit = pd.read_csv(P / "_peer_ltl_quarterly_rows_audit.csv")
    m = pd.read_csv(P / "peer_ltl_monthly_kpis.csv")
    rep = q[q["basis"] == "as_reported"].pivot_table(index=["ticker", "period"], columns="metric", values="value")
    w = q.pivot_table(index=["ticker", "period"], columns="metric", values="value")

    print("1. totals / workdays vs reported per-day values")
    for tot, per in [("shipments_total", "shipments_per_day"), ("tons_total", "tons_per_day")]:
        x = rep[[tot, per, "workdays"]].dropna()
        d = 100 * (x[tot] / x["workdays"] / x[per] - 1)
        flag = "PASS" if d.abs().max() < 0.1 else "FLAG"
        print(f"   {flag} {tot}: n={len(x)} max |diff| = {d.abs().max():.3f}%  "
              f"tickers={sorted(x.index.get_level_values(0).unique())}")

    print("2. weight identity: tons/day x 2000 / shipments/day vs weight per shipment")
    x = w[["tons_per_day", "shipments_per_day", "weight_per_shipment_lbs"]].dropna()
    d = 100 * (x["tons_per_day"] * 2000 / x["shipments_per_day"] / x["weight_per_shipment_lbs"] - 1)
    print(f"   {'PASS' if d.abs().max() < 1.5 else 'FLAG'} n={len(x)} max |diff| = {d.abs().max():.2f}%")

    print("3. operating ratio vs 1 - operating income / revenue")
    x = w[["revenue_musd", "operating_income_musd", "operating_ratio_pct"]].dropna()
    d = 100 * (1 - x["operating_income_musd"] / x["revenue_musd"]) - x["operating_ratio_pct"]
    bad = d[d.abs() > 0.25]
    print(f"   {'PASS' if bad.empty else 'FLAG'} n={len(x)} max |diff| = {d.abs().max():.2f} pp; >0.25pp: {len(bad)}")
    if len(bad):
        print(bad.round(2).to_string())

    print("4. sum of quarters vs full-year column of the Q4 release")
    rows = []
    a = audit[audit["basis"] == "as_reported"]
    for met in ["revenue_musd", "operating_income_musd"]:
        for _, r in a[(a["metric"] == met) & a["period"].str.endswith("Q4")].iterrows():
            nums = []
            for c in str(r["source_row"]).split(" | ")[1:]:
                c2 = c.replace("$", "").replace(",", "").replace("(", "-").replace(")", "").strip()
                try:
                    nums.append(float(c2))
                except ValueError:
                    pass
            if not nums or not nums[0]:
                continue
            scale = r["value"] / nums[0]
            ann = [n * scale for n in nums[2:] if abs(n * scale) > 2.5 * abs(r["value"])]
            qs = a[(a["ticker"] == r["ticker"]) & (a["metric"] == met) & (a["period"].str[:4] == r["period"][:4])]
            if ann and len(qs) == 4:
                rows.append(dict(ticker=r["ticker"], year=r["period"][:4], metric=met, sum_quarters=qs["value"].sum(),
                                 full_year=ann[0]))
    t = pd.DataFrame(rows)
    t["diff"] = t["sum_quarters"] - t["full_year"]
    bad = t[t["diff"].abs() > 5]  # XPO reports whole $M per quarter, so a few $M is rounding
    print(f"   {'PASS' if bad.empty else 'FLAG'} n={len(t)} ticker-years; max |diff| = ${t['diff'].abs().max():.1f}M "
          f"(XPO rounds to whole $M: 2018 ±0.2, 2022 -4, 2024 +1)")
    if len(bad):
        print(bad.to_string())

    print("5. restatements (prior-year column vs originally reported value)")
    r = pd.read_csv(P / "_peer_restatement_check.csv")
    big = r[r["diff_pct"].abs() > 1]
    print(f"   {len(r)} comparisons; {len(big)} differ by >1%:")
    if len(big):
        print(big.groupby(["ticker", "metric"]).size().to_string())
    vol = big[big["metric"].isin(["shipments_per_day", "tons_per_day", "weight_per_shipment_lbs"])]
    print(f"   {'PASS' if vol.empty else 'FLAG'} volume metrics restated by >1%: {len(vol)}")

    print("6. monthly YoY (mean of reported months) vs quarterly YoY from per-day values")
    qq = q.pivot_table(index=["ticker", "period"], columns="metric", values="value").reset_index()
    qq["p"] = qq["period"].map(lambda s: pd.Period(s, "Q"))
    m["q"] = m["month"].map(lambda s: pd.Period(s, "M").asfreq("Q"))
    out = []
    for mq, mm in [("shipments_per_day", "shipments_per_day_yoy_pct"), ("tons_per_day", "tons_per_day_yoy_pct"),
                   ("weight_per_shipment_lbs", "weight_per_shipment_yoy_pct")]:
        g = qq.pivot_table(index="p", columns="ticker", values=mq)
        yoy = 100 * (g / g.shift(4) - 1)
        agg = m[m["metric"] == mm].groupby(["ticker", "q"])["value"].agg(["mean", "count"])
        for (tk, per), row in agg.iterrows():
            if per in yoy.index and tk in yoy and pd.notna(yoy.loc[per, tk]):
                out.append(dict(ticker=tk, quarter=str(per), metric=mq, n_months=row["count"],
                                monthly_mean=row["mean"], quarterly_yoy=yoy.loc[per, tk]))
    s = pd.DataFrame(out)
    s["diff_pp"] = s["monthly_mean"] - s["quarterly_yoy"]
    s.to_csv(P / "_peer_monthly_vs_quarterly_check.csv", index=False)
    print(f"   n={len(s)} quarter-metrics; median |diff| = {s['diff_pp'].abs().median():.2f} pp; "
          f">3pp: {(s['diff_pp'].abs() > 3).sum()} (single-month vs weather-hit quarter cases expected)")
    print(s.groupby("ticker")["diff_pp"].agg(lambda x: round(x.abs().median(), 2)).rename("median |diff| pp").to_string())
    print(s[s["diff_pp"].abs() > 3].round(1).to_string())


buf = io.StringIO()
with redirect_stdout(buf):
    run()
print(buf.getvalue())
(P / "_peer_validation_report.txt").write_text(buf.getvalue())
