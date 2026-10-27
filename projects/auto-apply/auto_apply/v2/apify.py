"""Jobright jobs through Apify (v2 find).

Jobright has no API, and its personalised feed needs a login, so the search runs through the
Apify actor `jobscrawler/jobright-scraper` (pay per result, about $0.004 a job). The token
comes from the APIFY_TOKEN environment variable and never leaves this module.

Jobright's links point at jobright.ai, not at the employer, so each job is written with
`ats: "jobright"`; the screen step finds the employer's own posting (boards.find, or the
company's careers page) before it can be routed to the filler.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .boards import ats_of, parse_posted

ACTOR = "jobscrawler~jobright-scraper"
PRICE_PER_ITEM = 0.00399  # USD, from the actor's pricing (2026-10-27)


def run_actor(actor_input: dict, token: str, *, actor: str = ACTOR, timeout: int = 300) -> list[dict]:
    """Run the actor and return its dataset items (one synchronous call)."""
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?" + urllib.parse.urlencode(
        {"timeout": timeout, "format": "json", "clean": "true"})
    req = urllib.request.Request(url, data=json.dumps(actor_input).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout + 30) as r:
        return json.loads(r.read().decode())


def normalize(item: dict, now: datetime) -> dict:
    url = item.get("applyUrl") or item.get("url") or ""
    return {
        "title": (item.get("jobTitle") or "").strip(),
        "company": (item.get("companyName") or "").strip(),
        "location": (item.get("location") or "").strip(),
        "posted": parse_posted(item.get("postedDate"), now),
        "url": url,
        "source": "jobright",
        "ats": ats_of(url),
        "salary": item.get("salary"),
        "experience": item.get("experienceLevel"),
        "description": item.get("description"),
    }


def search_inputs(searches: list[str], *, max_items: int, date_posted: str) -> list[dict]:
    """'data analyst@Memphis, TN' -> actor input; '@remote' means remoteOnly."""
    out = []
    for s in searches:
        keyword, _, where = s.partition("@")
        remote = where.strip().lower() == "remote"
        out.append({"keyword": keyword.strip(), "location": "" if remote else where.strip(), "country": "US",
                    "maxItems": max_items, "sortBy": "date", "datePosted": date_posted,
                    "experienceLevel": "entry", "jobType": "full-time", "remoteOnly": remote,
                    "includeCompanyDetails": False, "includeSalary": True})
    return out


def dedupe(jobs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for j in jobs:
        key = j["url"] or (j["company"].lower(), j["title"].lower(), j["location"].lower())
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.apify")
    p.add_argument("--search", action="append", required=True,
                   help='"keyword@location" (repeatable); "@remote" for remote-only')
    p.add_argument("--max-per-search", type=int, default=25)
    p.add_argument("--date-posted", default="3d", choices=["24h", "3d", "7d", "14d", "30d"])
    p.add_argument("--budget-usd", type=float, default=1.00, help="refuse to start above this estimate")
    p.add_argument("--out", default="runs/v2/jobs-jobright.json")
    a = p.parse_args(argv)

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("APIFY_TOKEN is not set: add it in the environment settings (see the auto-apply README).")
        return 2
    inputs = search_inputs(a.search, max_items=a.max_per_search, date_posted=a.date_posted)
    estimate = len(inputs) * a.max_per_search * PRICE_PER_ITEM
    if estimate > a.budget_usd:
        print(f"estimated ${estimate:.2f} is over --budget-usd {a.budget_usd:.2f}; lower --max-per-search")
        return 2
    now, jobs, failed = datetime.now(timezone.utc), [], []
    for inp in inputs:
        try:
            jobs += [normalize(i, now) for i in run_actor(inp, token)]
        except Exception as e:  # one failed search shouldn't lose the others
            failed.append(f"{inp['keyword']}@{inp['location'] or 'remote'}: {type(e).__name__}: {e}")
    jobs = dedupe(jobs)
    json.dump(jobs, open(a.out, "w"), indent=1)
    for f in failed:
        print("FAILED", f)
    print(f"{len(jobs)} Jobright jobs from {len(inputs)} searches (max cost ${estimate:.2f}) -> {a.out}")
    return 1 if failed and not jobs else 0


if __name__ == "__main__":
    sys.exit(main())
