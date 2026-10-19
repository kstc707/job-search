"""Which jobs are worth an application, and in what order (v2 targeting).

Sai's data (228 applications, Apr–Oct 2026): engineer, data scientist and senior roles got
no human callback, and most applications went to other states. v2 keeps entry-level
analyst roles, ranks them by his location preference, and prefers fresh postings.

    keep    = analyst-type title, not senior/engineer/scientist, posted within max_age_hours
    rank by = location tier (Memphis > Remote > Atlanta > Alabama > rest of US), then score,
              then newest first
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

OFF_TARGET = re.compile(
    r"\b(engineer|engineering|scientist|developer|architect|senior|sr|lead|manager|principal|staff|"
    r"director|head|vp|intern|internship|co-?op|ii|iii|iv|phd|postdoc)\b", re.I)
ON_TARGET = re.compile(
    r"\b(analyst|analytics|reporting|business intelligence|bi|insights?|data quality)\b", re.I)

LOCATION_TIERS = [  # Sai, 2026-10-19
    ("Memphis", re.compile(r"memphis|collierville|germantown|bartlett|cordova|lakeland|arlington,?\s*tn|"
                           r"millington|southaven|olive branch|west memphis", re.I)),
    ("Remote", re.compile(r"\bremote\b", re.I)),
    ("Atlanta", re.compile(r"atlanta|alpharetta|marietta|sandy springs|duluth,?\s*ga|norcross|peachtree|"
                           r"roswell|kennesaw|smyrna,?\s*ga|dunwoody|decatur,?\s*ga|johns creek", re.I)),
    ("Alabama", re.compile(r"alabama|,\s*al\b|birmingham|huntsville|montgomery|mobile,?\s*al|tuscaloosa|"
                           r"auburn,?\s*al|hoover", re.I)),
]
REST_OF_US = "Rest of US"


def title_target(title: str) -> str:
    """'in' (entry-level analyst), 'off' (engineer/scientist/senior…), or 'other'."""
    if OFF_TARGET.search(title or ""):
        return "off"
    if ON_TARGET.search(title or ""):
        return "in"
    return "other"


def location_tier(location: str) -> tuple[int, str]:
    for i, (name, rx) in enumerate(LOCATION_TIERS):
        if rx.search(location or ""):
            return i, name
    return len(LOCATION_TIERS), REST_OF_US


def age_hours(posted: str | None, now: datetime) -> float | None:
    if not posted:
        return None
    try:
        dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(posted, "%B %d, %Y")  # Indeed: "October 16, 2026"
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 3600


@dataclass
class Verdict:
    keep: bool
    reason: str
    title_class: str
    tier: int
    tier_name: str
    age_hours: float | None


def judge(job: dict, *, now: datetime, max_age_hours: float = 72) -> Verdict:
    tc = title_target(job.get("title", ""))
    tier, tier_name = location_tier(job.get("location", ""))
    age = age_hours(job.get("posted"), now)
    if tc == "off":
        return Verdict(False, "off-target title (engineer/scientist/senior/intern)", tc, tier, tier_name, age)
    if tc == "other":
        return Verdict(False, "not an analyst-type title", tc, tier, tier_name, age)
    if age is not None and age > max_age_hours:
        return Verdict(False, f"posted {age / 24:.0f} days ago (limit {max_age_hours / 24:.0f})", tc, tier, tier_name, age)
    return Verdict(True, "in target", tc, tier, tier_name, age)


def rank(jobs: list[dict], *, now: datetime, max_age_hours: float = 72) -> list[tuple[dict, Verdict]]:
    """Kept jobs first in preference order, then the rejects with their reasons."""
    judged = [(j, judge(j, now=now, max_age_hours=max_age_hours)) for j in jobs]
    kept = [x for x in judged if x[1].keep]
    kept.sort(key=lambda x: (x[1].tier, -(x[0].get("score") or 0),
                             x[1].age_hours if x[1].age_hours is not None else 1e9))
    return kept + [x for x in judged if not x[1].keep]


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.target")
    p.add_argument("jobs", help='JSON list of {"title","company","location","posted","score"?}')
    p.add_argument("--max-age-hours", type=float, default=72)
    p.add_argument("--out")
    a = p.parse_args(argv)
    ranked = rank(json.load(open(a.jobs)), now=datetime.now(timezone.utc), max_age_hours=a.max_age_hours)
    for job, v in ranked:
        mark = "KEEP" if v.keep else "skip"
        print(f"{mark}  {v.tier_name:10} {(job.get('company') or '')[:22]:22} {(job.get('title') or '')[:44]:44} {v.reason}")
    if a.out:
        json.dump([{**j, "verdict": asdict(v)} for j, v in ranked], open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
