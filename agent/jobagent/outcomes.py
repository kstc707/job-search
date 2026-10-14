"""Outcome log and score calibration: does the fit score predict which applications get a reply?

One CSV row per sent application (`work/outcomes.csv`, personal, never committed). The agent
appends a row when it applies and fills `outcome` when Tsenta, the inbox or the person reports
one. Columns (see FIELDS): ids, the role family and source, the post-build score with its parts,
and the outcome.

Outcomes
- positive: recruiter_reply, screen, interview, offer
- negative: rejected, or no reply `window` days after applying (default 30: ghosted)
- pending:  no reply yet and still inside the window. Pending rows are left out of every rate,
            because counting them as failures would make the newest applications look worst.

The report answers four questions with plain statistics (no third-party packages):
1. What is the base rate of a positive outcome, with a 95% Wilson interval?
2. Does the rate rise with the score? (rate per score band)
3. How well does the score rank applications? (AUC: the chance a random positive outscored
   a random negative; 0.5 is a coin flip)
4. Is there enough data to trust any of that yet?
"""
import csv
import datetime as dt
import math

FIELDS = ["app_id", "applied", "company", "title", "family", "source", "score",
          "required", "keywords", "preferred", "level", "parse", "freshness", "signal",
          "decision", "outcome", "outcome_date"]
PARTS = ["required", "keywords", "preferred", "level", "parse", "freshness", "signal"]
POSITIVE = {"recruiter_reply", "screen", "interview", "offer"}
NEGATIVE = {"rejected"}
BANDS = [(0, 65), (65, 72), (72, 80), (80, 101)]
MIN_PER_CLASS = 10  # below this many positives or negatives, the AUC is noise


def load(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def row_from_score(app_id, applied, score_result, source="tsenta"):
    """A new log row from `jobagent score` output (the dict it prints as JSON)."""
    row = {"app_id": app_id, "applied": str(applied), "company": score_result.get("company") or "",
           "title": score_result.get("title") or "", "family": score_result.get("family") or "",
           "source": source, "score": score_result["score"],
           "decision": score_result.get("decision", ""), "outcome": "", "outcome_date": ""}
    row.update({p: score_result.get("parts", {}).get(p, "") for p in PARTS})
    return row


def label(row, today, window=30):
    """1 (positive), 0 (negative) or None (pending, or not a usable row)."""
    out = (row.get("outcome") or "").strip().lower()
    if out in POSITIVE:
        return 1
    if out in NEGATIVE or out == "no_response":
        return 0
    try:
        applied = dt.date.fromisoformat(row["applied"][:10])
    except (KeyError, ValueError):
        return None
    return 0 if (today - applied).days > window else None


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes in n trials. Better than p +/- 1.96*SE when
    n is small or p is near 0, which is exactly the job-search case."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def auc(scores, labels):
    """Area under the ROC curve via the Mann-Whitney U statistic (ties count half)."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def labelled(rows, today, window=30):
    """(row, label, score) for every row with a settled outcome and a numeric score."""
    out = []
    for r in rows:
        y = label(r, today, window)
        try:
            s = float(r["score"])
        except (KeyError, ValueError, TypeError):
            continue
        if y is not None:
            out.append((r, y, s))
    return out


def report(rows, today=None, window=30):
    today = today or dt.date.today()
    data = labelled(rows, today, window)
    n, k = len(data), sum(y for _, y, _ in data)
    res = {"applications": len(rows), "settled": n, "pending": len(rows) - n, "positives": k,
           "base_rate": round(k / n, 3) if n else None,
           "base_rate_ci": [round(x, 3) for x in wilson(k, n)], "bands": [], "groups": {}}
    for lo, hi in BANDS:
        ys = [y for _, y, s in data if lo <= s < hi]
        res["bands"].append({"band": f"{lo}-{min(hi, 100)}", "n": len(ys), "positives": sum(ys),
                             "rate_ci": [round(x, 3) for x in wilson(sum(ys), len(ys))]})
    for key in ("family", "source"):
        g = {}
        for r, y, _ in data:
            g.setdefault(r.get(key) or "?", []).append(y)
        res["groups"][key] = {name: {"n": len(ys), "positives": sum(ys)} for name, ys in g.items()}
    a = auc([s for _, _, s in data], [y for _, y, _ in data])
    res["auc"] = round(a, 3) if a is not None else None
    res["enough_data"] = min(k, n - k) >= MIN_PER_CLASS
    return res


def text(res):
    """The report as a few readable lines."""
    lo, hi = res["base_rate_ci"]
    lines = [f"{res['applications']} applications: {res['settled']} settled, "
             f"{res['pending']} pending, {res['positives']} positive"]
    if res["settled"]:
        lines.append(f"Base rate {res['base_rate']:.1%} (95% CI {lo:.1%} to {hi:.1%})")
    lines.append("Score band  n  pos  rate 95% CI")
    for b in res["bands"]:
        lo, hi = b["rate_ci"]
        ci = f"{lo:.0%} to {hi:.0%}" if b["n"] else "-"
        lines.append(f"{b['band']:>9} {b['n']:>3} {b['positives']:>4}  {ci}")
    lines.append(f"AUC {res['auc']}" if res["auc"] is not None else "AUC: needs a positive and a negative")
    if not res["enough_data"]:
        lines.append(f"Not enough data yet: wait for {MIN_PER_CLASS}+ positives and "
                     f"{MIN_PER_CLASS}+ negatives before changing thresholds.")
    return "\n".join(lines)
