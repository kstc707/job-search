"""Parse the FedEx Freight segment table out of FedEx Corp quarterly earnings releases.

Each release has a "FEDEX FREIGHT SEGMENT FINANCIAL AND OPERATING HIGHLIGHTS" table whose first
column block is the current fiscal quarter and second block the same quarter a year earlier.
Writes one row per (release, metric) with both values so as-reported and restated figures can be
compared.
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

MONTHS = {"feb": 2, "may": 5, "aug": 8, "nov": 11}
FQ = {8: 1, 11: 2, 2: 3, 5: 4}


def num(cell):
    if not isinstance(cell, str):
        return float(cell) if pd.notna(cell) else None
    c = cell.replace("$", "").replace(",", "").replace("%", "").strip()
    if c in {"—", "-", "–"}:
        return 0.0
    neg = c.startswith("(")
    c = c.strip("()").strip()
    try:
        v = float(c)
    except ValueError:
        return None
    return -v if neg else v


def segment_table(tables):
    for t in tables:
        s = t.to_string().lower()
        if "composite weight per shipment" in s and "revenue" in s and "operating income" in s:
            return t
    return None


rows = []
for f in sorted(SRC.glob("*.htm")):
    filed = f.name[:10]
    t = segment_table(pd.read_html(io.StringIO(f.read_text(errors="replace"))))
    if t is None:
        print("no segment table:", f.name)
        continue
    t = t.astype(object)
    # header: find the period-end month/year for each column
    col_period = {}
    # header rows are those above the first row with a text label in column 0
    first_label = next((i for i, v in enumerate(t.iloc[:, 0]) if isinstance(v, str) and v.strip()), 5)
    for r in range(first_label):
        for c, v in t.iloc[r].items():
            if isinstance(v, str):
                m = re.search(r"\b(feb|may|aug|nov)[a-z]*\.?\s+\d", v, re.I)
                y = re.search(r"\b(20[0-3]\d)\b", v)
                if m:
                    col_period.setdefault(c, {})["month"] = MONTHS[m.group(1).lower()]
                if y:
                    col_period.setdefault(c, {})["year"] = int(y.group(1))
    years = [(c, p["year"]) for c, p in col_period.items() if "year" in p]
    if not years:
        print("no header years:", f.name)
        continue
    # contiguous column groups by year, left to right; first = current quarter, second = prior year
    groups = []
    for c, y in sorted(years, key=lambda x: list(t.columns).index(x[0])):
        if groups and groups[-1][0] == y:
            groups[-1][1].append(c)
        else:
            groups.append((y, [c]))
    (cy, ccols), (py, pcols) = groups[0], groups[1]
    month = next((p["month"] for p in col_period.values() if "month" in p), None)
    if month is None:
        print("no header month:", f.name)
        continue
    # a group spans from its first year-labelled column up to the next group's start
    allcols = list(t.columns)
    cur_span = allcols[allcols.index(ccols[0]) - 1: allcols.index(pcols[0])]
    nxt = allcols.index(groups[2][1][0]) if len(groups) > 2 else len(allcols)
    pri_span = allcols[allcols.index(pcols[0]) - 1: nxt]
    section = ""
    for _, row in t.iterrows():
        label = next((v for v in row.values if isinstance(v, str) and v.strip()), None)
        if label is None:
            continue
        label = re.sub(r"\s+", " ", label).strip()
        label = re.sub(r"(?<=[A-Za-z])\d+$", "", label)  # footnote markers, e.g. "Operating Income1"
        cur = next((num(row[c]) for c in cur_span if num(row[c]) is not None), None)
        pri = next((num(row[c]) for c in pri_span if num(row[c]) is not None), None)
        if cur is None and pri is None:
            if label.endswith(":") or label.isupper():
                section = label.rstrip(":")
            continue
        fy = cy + 1 if month >= 6 else cy
        rows.append(dict(source_file=f.name, filed=filed, period_end_month=month, period_end_year=cy,
                         fiscal_year=fy, fiscal_quarter=FQ[month], section=section, label=label,
                         value=cur, prior_year_value=pri))

df = pd.DataFrame(rows)
df.to_csv(OUT, index=False)
print(df.groupby(["filed"]).size().to_string())


# ---- canonical wide table -------------------------------------------------------------------
def canon(label: str) -> str | None:
    l = label.lower()
    if l in {"revenue", "revenues"}:
        return "revenue_musd"
    if l == "operating income" or l == "operating income (loss)":
        return "operating_income_musd"
    if l == "operating margin":
        return "operating_margin_pct"
    if l in {"operating weekdays", "operating days"}:
        return "operating_days"
    if "average daily shipments" in l:
        return "avg_daily_shipments_k"
    if "weight per shipment" in l:
        return "weight_per_shipment_lbs"
    if "revenue per shipment" in l or "revenue/shipment" in l:
        return "revenue_per_shipment_usd"
    if "hundredweight" in l or "revenue/cwt" in l:
        return "revenue_per_cwt_usd"
    return None


recs = []
for (src, filed), g in df.groupby(["source_file", "filed"], sort=False):
    labels = list(g["label"])
    for i, (_, r) in enumerate(g.iterrows()):
        lab = r["label"]
        if lab.lower() in {"priority", "economy"}:
            # the matching composite/total row follows the Priority/Economy pair
            nxt = next((canon(x) for x in labels[i + 1:] if canon(x) in
                        {"avg_daily_shipments_k", "weight_per_shipment_lbs", "revenue_per_shipment_usd",
                         "revenue_per_cwt_usd"}), None)
            key = f"{nxt}_{lab.lower()}" if nxt else None
        else:
            key = canon(lab)
        if key:
            recs.append(dict(filed=filed, source_file=src, fiscal_year=r["fiscal_year"],
                             fiscal_quarter=r["fiscal_quarter"], period_end_year=r["period_end_year"],
                             period_end_month=r["period_end_month"], metric=key, value=r["value"],
                             prior_year_value=r["prior_year_value"]))
long = pd.DataFrame(recs).drop_duplicates(["filed", "metric"])
long.to_csv(OUT.with_name(OUT.stem + "_long.csv"), index=False)

# ---- final quarterly KPI table ----------------------------------------------------------------
# As-reported current-quarter values; quarters only seen in a prior-year column (FY2018 Q1-Q3) are
# back-filled from the FY2019 releases and marked as such.
PERIOD_END_DAY = {2: 28, 5: 31, 8: 31, 11: 30}
wide = long.pivot_table(index=["fiscal_year", "fiscal_quarter"], columns="metric", values="value")
srcs = long.groupby(["fiscal_year", "fiscal_quarter"])["source_file"].first()
wide["value_basis"] = "as_reported"
wide["source_file"] = srcs
prior = long.pivot_table(index=["fiscal_year", "fiscal_quarter"], columns="metric", values="prior_year_value")
prior.index = pd.MultiIndex.from_tuples([(y - 1, q) for y, q in prior.index], names=wide.index.names)
psrc = long.groupby(["fiscal_year", "fiscal_quarter"])["source_file"].first()
psrc.index = pd.MultiIndex.from_tuples([(y - 1, q) for y, q in psrc.index], names=wide.index.names)
missing = prior.index.difference(wide.index)
back = prior.loc[missing].copy()
back["value_basis"] = "prior_year_column_of_next_year_release"
back["source_file"] = psrc.loc[missing]
wide = pd.concat([wide, back]).sort_index().reset_index()
m = wide["fiscal_quarter"].map({1: 8, 2: 11, 3: 2, 4: 5})
y = wide["fiscal_year"] - (m >= 6).astype(int)
wide["period_end"] = pd.to_datetime(dict(year=y, month=m, day=m.map(PERIOD_END_DAY)))
wide.loc[(wide["period_end"].dt.month == 2) & (wide["period_end"].dt.is_leap_year), "period_end"] += pd.Timedelta(days=1)
wide["fiscal_period"] = "FY" + wide["fiscal_year"].astype(str) + "Q" + wide["fiscal_quarter"].astype(str)
lead = ["fiscal_period", "fiscal_year", "fiscal_quarter", "period_end", "revenue_musd", "operating_income_musd",
        "operating_margin_pct", "operating_days", "avg_daily_shipments_k", "weight_per_shipment_lbs",
        "revenue_per_shipment_usd", "revenue_per_cwt_usd"]
rest = [c for c in wide.columns if c not in lead and c not in ("value_basis", "source_file")]
wide = wide[lead + rest + ["value_basis", "source_file"]]
wide.to_csv(OUT.with_name("fedex_freight_segment_quarterly_kpis.csv"), index=False)
print(wide[lead].to_string())
