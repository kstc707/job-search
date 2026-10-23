"""Parse FedEx Freight Holding Co.'s recast calendar-quarter results (8-K filed 2026-08-06, Ex. 99.1).

Writes one row per calendar quarter (CY2024 Q1 - CY2025 Q4) with revenue, operating income and
LTL operating statistics, on the post-spin-off presentation basis.
"""
import io
import pathlib
import re
import sys
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
SRC = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
QEND = {"march": 1, "june": 2, "september": 3, "december": 4}


def num(cell):
    if not isinstance(cell, str):
        return float(cell) if pd.notna(cell) else None
    c = cell.replace("$", "").replace(",", "").strip()
    if c in {"—", "-", "–"}:
        return 0.0
    neg = c.startswith("(")
    try:
        v = float(c.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


METRICS = {
    "revenue": "revenue_musd",
    "operating income": "operating_income_musd",
    "separation and other": "separation_and_other_musd",
    "operating days": "operating_days",
    "total shipments": "total_shipments",
    "total tonnage": "total_tonnage",
    "tonnage per day": "tonnage_per_day",
    "total average daily shipments": "avg_daily_shipments",
    "composite weight per shipment": "weight_per_shipment_lbs",
    "composite average length of haul": "avg_length_of_haul_miles",
    "composite revenue per shipment": "revenue_per_shipment_usd",
    "composite revenue per shipment (excluding fuel surcharges)": "revenue_per_shipment_ex_fuel_usd",
    "composite revenue per hundredweight": "revenue_per_cwt_usd",
    "composite revenue per hundredweight (excluding fuel surcharges)": "revenue_per_cwt_ex_fuel_usd",
}

recs = {}
for t in pd.read_html(io.StringIO(SRC.read_text(errors="replace"))):
    t = t.astype(object)
    if "Three Months Ended" not in t.to_string():
        continue
    hdr = {}
    for r in range(3):
        for c, v in t.iloc[r].items():
            if isinstance(v, str):
                m = re.search(r"(March|June|September|December)\s*\d+,\s*(20\d\d)", v)
                if m:
                    hdr[c] = (int(m.group(2)), QEND[m.group(1).lower()])
    if not hdr:
        continue
    for _, row in t.iterrows():
        label = row.iloc[0]
        if not isinstance(label, str):
            continue
        key = METRICS.get(re.sub(r"\s+", " ", label).strip().lower())
        if not key:
            continue
        for c, (y, q) in hdr.items():
            v = num(row[c])
            if v is not None:
                recs.setdefault((y, q), {}).setdefault(key, v)

df = pd.DataFrame.from_dict(recs, orient="index").sort_index()
df.index = pd.MultiIndex.from_tuples(df.index, names=["calendar_year", "calendar_quarter"])
df = df.reset_index()
df.insert(0, "period", df["calendar_year"].astype(str) + "Q" + df["calendar_quarter"].astype(str))
df["avg_daily_shipments_k"] = df.pop("avg_daily_shipments") / 1000
df["operating_margin_pct"] = (100 * df["operating_income_musd"] / df["revenue_musd"]).round(1)
df["source_file"] = SRC.name
df.to_csv(OUT, index=False)
print(df.to_string())
