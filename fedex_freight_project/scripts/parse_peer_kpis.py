"""Parse public LTL peers' quarterly operating statistics and monthly operating updates from EDGAR 8-Ks.

Inputs: data/raw/sec_edgar/peers/<TICKER>/<filing date>_<document>.htm (from fetch_peer_filings.py).
Outputs (data/processed/):
  peer_ltl_quarterly_kpis.csv        tidy: ticker, period, period_end, metric, value, unit, prior_year_value,
                                     source_file, basis
  peer_ltl_quarterly_kpis_wide.csv   one row per ticker x quarter
  peer_ltl_monthly_kpis.csv          tidy monthly year-over-year % changes from mid-quarter updates

Documents are recognised by content, not by 8-K item number: an earnings release is any document with the
carrier's LTL operating-statistics rows; a monthly update is any document that reports YoY % changes for a
named month. Every cell is read from the HTML table itself (no colspan duplication), so for each statistics row
the first number is the current quarter and the second the same quarter a year earlier.

Usage: python scripts/parse_peer_kpis.py data/raw/sec_edgar/peers data/processed
"""
import html as htmlmod
import pathlib
import re
import sys
import warnings

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
SRC = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}

# ---------------------------------------------------------------- quarterly label maps
# (regex on the row label, canonical metric, unit, scale applied to the value)
# Regexes are anchored on the start of the label; the first matching row in the release wins.
QUARTERLY = {
    "ODFL": [
        (r"^work days", "workdays", "days", 1),
        (r"^operating ratio", "operating_ratio_pct", "pct", 1),
        (r"^ltl tonnage per day", "tons_per_day", "tons", 1),
        (r"^ltl shipments per day", "shipments_per_day", "shipments", 1),
        (r"^ltl tons$", "tons_total", "tons", 1000),  # thousands; pre-2021 releases have no per-day rows
        (r"^ltl shipments$", "shipments_total", "shipments", 1000),
        (r"^ltl weight per shipment", "weight_per_shipment_lbs", "lbs", 1),
        (r"^ltl revenue per hundredweight, excluding fuel", "revenue_per_cwt_ex_fuel_usd", "usd", 1),
        (r"^ltl revenue per hundredweight$", "revenue_per_cwt_usd", "usd", 1),
        (r"^ltl revenue per shipment, excluding fuel", "revenue_per_shipment_ex_fuel_usd", "usd", 1),
        (r"^ltl revenue per shipment$", "revenue_per_shipment_usd", "usd", 1),
        (r"^(total revenue|revenue from operations|revenue)$", "revenue_musd", "usd_m", 1e-3),
        (r"^operating income$", "operating_income_musd", "usd_m", 1e-3),
        (r"^average length of haul", "length_of_haul_miles", "miles", 1),
    ],
    "SAIA": [
        (r"^workdays", "workdays", "days", 1),
        (r"^operating ratio", "operating_ratio_pct", "pct", 1),
        (r"^ltl revenue/cwt\.?, excluding fuel", "revenue_per_cwt_ex_fuel_usd", "usd", 1),
        (r"^ltl revenue/cwt\.?$", "revenue_per_cwt_usd", "usd", 1),
        (r"^ltl revenue/shipment, excluding fuel", "revenue_per_shipment_ex_fuel_usd", "usd", 1),
        (r"^ltl revenue/shipment$", "revenue_per_shipment_usd", "usd", 1),
        (r"^ltl pounds/shipment", "weight_per_shipment_lbs", "lbs", 1),
        (r"^ltl average length of haul", "length_of_haul_miles", "miles", 1),
        (r"^operating revenue$", "revenue_musd", "usd_m", 1e-3),
        (r"^operating income$", "operating_income_musd", "usd_m", 1e-3),
        # tonnage and shipments rows carry quarter totals then per-workday values; handled specially
    ],
    "XPO": [
        (r"^number of working days", "workdays", "days", 1),
        (r"^(pounds|lbs\.) per day", "tons_per_day", "tons", 1000 / 2000),  # thousands of lbs -> tons
        (r"^shipments per day", "shipments_per_day", "shipments", 1),
        (r"^(average|avg\.) weight per shipment", "weight_per_shipment_lbs", "lbs", 1),
        (r"^revenue per shipment \(excluding fuel", "revenue_per_shipment_ex_fuel_usd", "usd", 1),
        (r"^revenue per shipment \(including fuel", "revenue_per_shipment_usd", "usd", 1),
        (r"^(gross )?revenue per hundredweight \(excluding fuel", "revenue_per_cwt_ex_fuel_usd", "usd", 1),
        (r"^(gross )?revenue per hundredweight \(including fuel", "revenue_per_cwt_usd", "usd", 1),
        (r"^average length of haul", "length_of_haul_miles", "miles", 1),
        (r"^adjusted operating ratio", "adjusted_operating_ratio_pct", "pct", 1),
        (r"^operating ratio", "operating_ratio_pct", "pct", 1),
    ],
    "ARCB": [
        (r"^workdays", "workdays", "days", 1),
        (r"^tonnage ?/ ?day", "tons_per_day", "tons", 1),
        (r"^shipments ?/ ?day", "shipments_per_day", "shipments", 1),
        (r"^(weight|pounds) ?/ ?shipment", "weight_per_shipment_lbs", "lbs", 1),
        (r"^tonnage \(tons\)", "tons_total", "tons", 1),
        (r"^shipments$", "shipments_total", "shipments", 1),
        (r"^billed revenue.*/ ?cwt", "revenue_per_cwt_usd", "usd", 1),
        (r"^billed revenue.*/ ?shipment", "revenue_per_shipment_usd", "usd", 1),
    ],
}
# A release must contain at least these to count as having an LTL operating-statistics table
REQUIRED = {"ODFL": "weight_per_shipment_lbs", "SAIA": "weight_per_shipment_lbs", "XPO": "shipments_per_day",
            "ARCB": "shipments_per_day"}

NUM = re.compile(r"^\(?-?\$?\s*\(?[\d,]*\.?\d+\)?%?\)?$")


def cell_text(td) -> str:
    t = td.get_text(" ", strip=True)
    t = htmlmod.unescape(t).replace("​", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def num(s: str):
    s = s.strip()
    if s in {"—", "–", "-", "— %", "—%"}:
        return 0.0
    c = s.replace("$", "").replace(",", "").replace("%", "").replace(" ", "").lstrip("+")
    neg = "(" in c or c.startswith("-")
    c = c.replace("(", "").replace(")", "").lstrip("-")
    if not re.fullmatch(r"\d*\.?\d+", c):
        return None
    v = float(c)
    return -v if neg else v


def rows_of(path: pathlib.Path):
    """Yield (table_index, cells) for every table row; cells are the non-empty texts in document order."""
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for ti, table in enumerate(soup.find_all("table")):
        for tr in table.find_all("tr"):
            cells = [cell_text(td) for td in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c and c not in {"$", "%", ")%", ")", "(", "% )"}]
            if cells:
                yield ti, cells


def numbers(cells):
    """Numeric tokens after the label, merging split cells like '(4.8' + ')%'."""
    out = []
    for c in cells[1:]:
        v = num(c)
        if v is not None:
            out.append(v)
    return out


def label_of(cells):
    lab = re.sub(r"\(\d\)|\d$", "", cells[0]).strip().lower()  # footnote markers
    return re.sub(r"\s+", " ", lab)


def parse_quarterly(ticker: str, path: pathlib.Path):
    rules = QUARTERLY[ticker]
    found = {}
    section = ""
    xpo_ltl_table = None
    ratio_candidates = []
    for ti, cells in rows_of(path):
        lab = label_of(cells)
        nums = numbers(cells)
        if not nums:
            if ticker == "ARCB" and re.match(r"^(asset-based|asset-light|arcbest|fleetnet|panther)", lab):
                section = lab
            continue
        if ticker == "ARCB" and lab == "asset-based":
            # segment tables list Asset-Based revenue first, then Asset-Based operating income ($ thousands)
            key = "revenue_musd" if "revenue_musd" not in found else "operating_income_musd"
            found.setdefault(key, (nums[0] / 1000, nums[1] / 1000 if len(nums) > 1 else None, "usd_m", ti, cells))
            continue
        if ticker == "ARCB" and lab == "total asset-based" and len(nums) >= 2:
            found.setdefault("operating_ratio_pct", (nums[1], nums[3] if len(nums) > 3 else None, "pct", ti, cells))
            continue
        if ticker == "ARCB" and not section.startswith("asset-based"):
            continue  # ArcBest: only the Asset-Based (ABF Freight) LTL segment
        if ticker == "XPO" and lab.startswith("revenue (excluding fuel surcharge"):
            xpo_ltl_table = ti  # the North American LTL segment income statement
        if ticker == "XPO" and ti == xpo_ltl_table and lab in ("revenue", "operating income"):
            key = "revenue_musd" if lab == "revenue" else "operating_income_musd"
            found.setdefault(key, (nums[0], nums[1] if len(nums) > 1 else None, "usd_m", ti, cells))
            continue
        if ticker == "SAIA" and re.match(r"^ltl (tonnage|shipments)", lab) and len(nums) >= 5:
            key = "tons_per_day" if "tonnage" in lab else "shipments_per_day"
            # quarter total (thousands), prior, %chg, per-workday (thousands), prior per-workday
            for k, v, pv in [(key, nums[3] * 1000, nums[4] * 1000),
                             (key.replace("_per_day", "_total"), nums[0] * 1000, nums[1] * 1000)]:
                found.setdefault(k, (v, pv, "tons" if "ton" in k else "shipments", ti, cells))
            continue
        for rx, key, unit, scale in rules:
            if re.search(rx, lab):
                v = nums[0] * scale
                pv = nums[1] * scale if len(nums) > 1 else None
                if key == "operating_ratio_pct":
                    ratio_candidates.append((v, pv, unit, ti, cells))
                found.setdefault(key, (v, pv, unit, ti, cells))
                break
    # Q4 releases can open with a full-year reconciliation; take the operating ratio from the operating
    # statistics table (the one holding weight per shipment) when it has one.
    stats_table = found.get("weight_per_shipment_lbs", (None,) * 4)[3]
    same = [c for c in ratio_candidates if c[3] == stats_table]
    if same:
        found["operating_ratio_pct"] = same[0]
    return found


# ---------------------------------------------------------------- monthly updates
MONTHLY_METRICS = [
    (r"(ltl )?ton(s|nage)? ?(/|per) ?(work)?day", "tons_per_day_yoy_pct"),
    (r"(ltl )?shipments per (work)?day|shipments ?/ ?day", "shipments_per_day_yoy_pct"),
    (r"(ltl )?weight per shipment|weight ?/ ?shipment|pounds per shipment", "weight_per_shipment_yoy_pct"),
    (r"revenue per day|billed revenue.*/ ?day", "revenue_per_day_yoy_pct"),
    (r"revenue per hundredweight, excluding fuel|revenue per hundredweight excluding fuel", "revenue_per_cwt_ex_fuel_yoy_pct"),
    (r"revenue per hundredweight|billed revenue.*/ ?cwt", "revenue_per_cwt_yoy_pct"),
]
UP = r"(?:increase[sd]?|rose|grew|growth|up|improve(?:d|ment)?)"
DOWN = r"(?:decrease[sd]?|decline[sd]?|fell|down|drop(?:ped)?|lower)"
PCT = r"(\d+(?:\.\d+)?)\s?(?:%|percent)"


def doc_text(path: pathlib.Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    t = soup.get_text(" ")
    t = htmlmod.unescape(t).replace("​", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", t)


def sign(word: str) -> int:
    return -1 if re.fullmatch(DOWN, word, re.I) else 1


def parse_monthly_text(text: str):
    """ODFL/XPO style prose: 'for August 2026 ... a 2.4% decrease in LTL shipments per day ...'."""
    out = []
    # split into per-month segments on "<Month> <Year>" mentions that are the subject of a sentence
    for m in re.finditer(r"(?:metrics|data|results) for (?:the month of )?(" + "|".join(MONTHS) + r"),? (20\d\d)",
                         text, re.I):
        month = pd.Period(f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}", "M")
        seg = text[m.end(): m.end() + 900]
        seg = re.split(r"(?:quarter-to-date|quarter to date|for the quarter)", seg, flags=re.I)[0]
        for rx, key in MONTHLY_METRICS:
            v = None
            # "<metric> increased 3.7%"   or   "<metric> was down 2%"
            a = re.search(r"(?:" + rx + r")[^.%]{0,40}?\b(" + UP + "|" + DOWN + r")\b[^.%\d]{0,20}" + PCT, seg, re.I)
            # "a 2.4% decrease in <metric>"  or  "increase of 5.7% in <metric>"
            b = re.search(PCT + r"\s(" + UP + "|" + DOWN + r")\s(?:in|of)\s(?:its\s|our\s)?(?:" + rx + ")", seg, re.I)
            c = re.search(r"\b(" + UP + "|" + DOWN + r") of " + PCT + r" in (?:" + rx + ")", seg, re.I)
            hits = []
            for h, (wi, pi) in [(a, (-2, -1)), (b, (-1, 0)), (c, (0, 1))]:
                if h:
                    g = [x for x in h.groups() if x is not None]
                    word = next(x for x in g if re.fullmatch(UP + "|" + DOWN, x, re.I))
                    pct = next(x for x in g if re.fullmatch(r"\d+(?:\.\d+)?", x))
                    hits.append((h.start(), sign(word) * float(pct)))
            if hits:
                v = min(hits)[1]  # earliest mention in the segment
            elif re.search(r"(?:" + rx + r")[^.]{0,30}\b(?:flat|unchanged)\b", seg, re.I):
                v = 0.0
            if v is not None:
                out.append((month, key, v))
    return out


def parse_monthly_tables(path: pathlib.Path):
    """SAIA/ARCB style tables with month columns ('July 2026') and YoY % rows."""
    out = []
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [cell_text(td) for td in tr.find_all(["td", "th"])]
            rows.append([c for c in cells if c and c not in {"%", ")%", ")"}])
        header, months = None, []
        for r in rows:
            ms = [re.search(r"(" + "|".join(MONTHS) + r")\s*(20\d\d)", c, re.I) for c in r]
            if sum(1 for m in ms if m) >= 1 and not any(num(c) is not None for c in r):
                header = r
                months = []
                for c in r:
                    mm = re.search(r"(" + "|".join(MONTHS) + r")\s*(20\d\d)", c, re.I)
                    if re.search(r"quarter|qtd|to date|versus q", c, re.I) and not mm:
                        months.append(None)
                    elif mm and not re.search(r"quarter|qtd|to date", c, re.I):
                        months.append(pd.Period(f"{mm.group(2)}-{MONTHS[mm.group(1).lower()]:02d}", "M"))
                    elif mm:
                        months.append(None)
                continue
            if not header or not r:
                continue
            lab = r[0].lower()
            if re.search(r"asset-light|purchased transportation|\(year-over-year\)", lab):
                continue  # ArcBest Asset-Light rows (labelled '(Year-over-Year)')
            key = next((k for rx, k in MONTHLY_METRICS if re.search(rx, lab)), None)
            if key is None:
                continue
            if "excluding fuel" in lab and key == "revenue_per_cwt_yoy_pct":
                key = "revenue_per_cwt_ex_fuel_yoy_pct"
            vals = []
            for c in r[1:]:
                if re.fullmatch(r"flat|unchanged", c, re.I):
                    vals.append(0.0)
                else:
                    v = num(c)
                    if v is not None:
                        vals.append(v)
            for mo, v in zip(months, vals):
                if mo is not None:
                    out.append((mo, key, v))
    return out


# ---------------------------------------------------------------- main
q_rows, m_rows = [], []
for tdir in sorted(p for p in SRC.iterdir() if p.is_dir()):
    ticker = tdir.name
    for f in sorted(tdir.glob("*.htm")):
        filed = pd.Timestamp(f.name[:10])
        # quarterly statistics
        found = parse_quarterly(ticker, f)
        if REQUIRED[ticker] in found and ("weight_per_shipment_lbs" in found or "tons_total" in found
                                          or "tons_per_day" in found):
            qend = filed - pd.Timedelta(days=15)
            period = (qend.to_period("Q") - 1) if qend.to_period("Q").end_time.normalize() > qend else qend.to_period("Q")
            for key, (v, pv, unit, ti, cells) in found.items():
                q_rows.append(dict(ticker=ticker, period=str(period), period_end=period.end_time.normalize().date(),
                                   metric=key, value=v, unit=unit, prior_year_value=pv, source_file=f.name,
                                   filed=filed.date(), basis="as_reported", source_row=" | ".join(cells)[:200]))
        # monthly updates
        months = parse_monthly_tables(f)
        if ticker in ("ODFL", "XPO", "SAIA", "ARCB"):
            months += parse_monthly_text(doc_text(f))
        for mo, key, v in months:
            m_rows.append(dict(ticker=ticker, month=str(mo), metric=key, value=v, unit="yoy_pct",
                               source_file=f.name, filed=filed.date()))

q = pd.DataFrame(q_rows)
# a quarter can appear in several documents (release + exhibit copies); keep the earliest-filed document
q = q.sort_values(["ticker", "period", "metric", "filed", "source_file"]).drop_duplicates(
    ["ticker", "period", "metric"], keep="first")

# Restatement check and back-fill from the prior-year column of the following year's release.
# Saia redefined "LTL" in 2018 (2017 releases split LTL and TL); its 2018 releases restate 2017 on the
# new basis, so for 2017 the prior-year column is the only consistent source.
py = q[q["prior_year_value"].notna()].copy()
py["period"] = py["period"].map(lambda p: str(pd.Period(p, "Q") - 4))
py = py[py["period"] >= "2017Q1"]
chk = py.merge(q[["ticker", "period", "metric", "value"]], on=["ticker", "period", "metric"], how="left",
               suffixes=("", "_as_reported"))
chk = chk[chk["value_as_reported"].notna()].assign(
    restated_value=lambda d: d["prior_year_value"],
    diff_pct=lambda d: 100 * (d["prior_year_value"] / d["value_as_reported"] - 1))
chk[["ticker", "period", "metric", "value_as_reported", "restated_value", "diff_pct", "source_file"]].to_csv(
    OUT / "_peer_restatement_check.csv", index=False)
fill = py.merge(q[["ticker", "period", "metric"]], on=["ticker", "period", "metric"], how="left", indicator=True)
fill = fill[fill["_merge"] == "left_only"].drop(columns="_merge")
fill = fill.assign(value=fill["prior_year_value"], prior_year_value=None,
                   period_end=fill["period"].map(lambda p: pd.Period(p, "Q").end_time.normalize().date()),
                   basis="restated: prior-year column of the following year's release")
fill = fill.sort_values("filed").drop_duplicates(["ticker", "period", "metric"])
q = pd.concat([q, fill], ignore_index=True)

# derived per-day volumes where a release reports only quarter totals (flagged in `basis`)
wide = q.pivot_table(index=["ticker", "period"], columns="metric", values="value").reset_index()
extra = []
for _, r in wide.iterrows():
    for per_day, total, unit in [("shipments_per_day", "shipments_total", "shipments"), ("tons_per_day", "tons_total", "tons")]:
        if pd.isna(r.get(per_day)) and pd.notna(r.get(total)) and pd.notna(r.get("workdays")) and r["workdays"] > 0:
            extra.append(dict(ticker=r["ticker"], period=r["period"], metric=per_day, value=r[total] / r["workdays"],
                              unit=unit, basis=f"derived: {total} / workdays"))
    if pd.isna(r.get("weight_per_shipment_lbs")) and pd.notna(r.get("tons_total")) and pd.notna(r.get("shipments_total")):
        extra.append(dict(ticker=r["ticker"], period=r["period"], metric="weight_per_shipment_lbs",
                          value=2000 * r["tons_total"] / r["shipments_total"], unit="lbs",
                          basis="derived: 2000 x tons_total / shipments_total"))
if extra:
    ex = pd.DataFrame(extra)
    ex["period_end"] = ex["period"].map(lambda p: pd.Period(p, "Q").end_time.normalize().date())
    q = pd.concat([q, ex], ignore_index=True)

q = q.sort_values(["ticker", "period", "metric"])
OUT.mkdir(parents=True, exist_ok=True)
q.drop(columns=["source_row"]).to_csv(OUT / "peer_ltl_quarterly_kpis.csv", index=False)
q.to_csv(OUT / "_peer_ltl_quarterly_rows_audit.csv", index=False)
wide = q.pivot_table(index=["ticker", "period"], columns="metric", values="value").reset_index()
wide.to_csv(OUT / "peer_ltl_quarterly_kpis_wide.csv", index=False)

m = pd.DataFrame(m_rows)
if len(m):
    # keep the first report of each month (mid-quarter update), later documents may repeat it
    m = m.sort_values(["ticker", "month", "metric", "filed"]).drop_duplicates(["ticker", "month", "metric"], keep="first")
    m.to_csv(OUT / "peer_ltl_monthly_kpis.csv", index=False)
print(q.groupby("ticker")["period"].agg(["min", "max", "nunique"]).to_string())
big = chk[chk["diff_pct"].abs() > 1]
print(f"restatement check: {len(chk)} comparisons, {len(big)} differ by >1%")
print(big.groupby(["ticker", "metric"]).size().to_string() if len(big) else "")
if len(m):
    print(m.groupby(["ticker", "metric"])["month"].agg(["min", "max", "nunique"]).to_string())
