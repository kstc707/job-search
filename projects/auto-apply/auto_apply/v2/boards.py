"""Open jobs straight from company career boards (replaces Tsenta recommendations).

Greenhouse, Lever and Ashby each publish a public, login-free JSON feed of a company's open
jobs. Given a watchlist of companies and their board ids, this module reads those feeds,
turns every posting into the jobs.json shape the rest of v2 uses, keeps the ones whose title
and location match the keywords you pass, and writes them to runs/v2/boards.json.

Watchlist (JSON list): [{"name": "Acme", "ats": "greenhouse" | "lever" | "ashby", "board": "acme",
"industry": "fintech" | "healthcare" | "ai" | "tech" (optional; fit.py gives fintech and healthcare priority)}]
The board id is the part of the company's job-board URL after the ATS host:
  boards.greenhouse.io/<board>, jobs.lever.co/<board>, jobs.ashbyhq.com/<board>.

Output rows: {id, title, company, location, posted, url, source: "board", ats, description}
`posted` is ISO-8601 UTC; Greenhouse gives first_published (or updated_at), Lever createdAt
(milliseconds), Ashby publishedAt.

One company's board failing (404, timeout, bad JSON) is reported and skipped; the run goes on.

    python -m auto_apply.v2.boards prompts/watchlist.example.json \\
        --title analyst --title "business intelligence" --exclude-title senior \\
        --location "united states" --location remote --location TN --out runs/v2/boards.json
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

API = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{board}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true",
}
USER_AGENT = "auto-apply-boards/1.0 (+public job board reader)"
MAX_DESCRIPTION = 20000

Fetch = Callable[[str], object]  # url -> parsed JSON; raises on HTTP or network errors


def http_json(url: str, timeout: float = 30) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------------------------------------------------------------- normalising

def html_to_text(s: str | None) -> str:
    """Greenhouse sends HTML escaped once more ("&lt;p&gt;"), so unescape, strip tags, unescape."""
    s = html.unescape(s or "")
    s = re.sub(r"(?i)<\s*(br|/p|/li|/div|/h\d|/tr)\s*/?>", "\n", s)
    s = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    lines = [" ".join(line.split()) for line in s.splitlines()]
    return "\n".join(line for line in lines if line).strip()[:MAX_DESCRIPTION]


def iso(value) -> str:
    """ISO string with any offset, or epoch milliseconds -> 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            dt = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OverflowError, OSError):
        return ""


def _job(company: dict, jid, title, location, posted, url, description) -> dict:
    return {"id": f"{company['ats']}:{company['board']}:{jid}", "title": " ".join((title or "").split()),
            "company": company["name"], "location": location or "", "posted": iso(posted), "url": url or "",
            "source": "board", "ats": company["ats"], "industry": company.get("industry", ""),
            "description": description}


def from_greenhouse(company: dict, payload: dict) -> list[dict]:
    out = []
    for j in payload.get("jobs") or []:
        loc = (j.get("location") or {}).get("name") or ""
        out.append(_job(company, j.get("id"), j.get("title"), loc, j.get("first_published") or j.get("updated_at"),
                        j.get("absolute_url"), html_to_text(j.get("content"))))
    return out


def from_lever(company: dict, payload: list) -> list[dict]:
    out = []
    for j in payload or []:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or ([cat["location"]] if cat.get("location") else [])
        loc = "; ".join(locs)
        if j.get("workplaceType") == "remote" and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip()
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description"))]
        for lst in j.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content'))}")
        parts.append(j.get("additionalPlain") or "")
        desc = "\n\n".join(p.strip() for p in parts if p and p.strip())[:MAX_DESCRIPTION]
        out.append(_job(company, j.get("id"), j.get("text"), loc, j.get("createdAt"), j.get("hostedUrl"), desc))
    return out


def from_ashby(company: dict, payload: dict) -> list[dict]:
    out = []
    for j in payload.get("jobs") or []:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
        loc = "; ".join(x for x in locs if x)
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip()
        desc = (j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")))[:MAX_DESCRIPTION]
        comp = (j.get("compensation") or {}).get("compensationTierSummary")
        if comp:
            desc = f"Compensation: {comp}\n\n{desc}"
        out.append(_job(company, j.get("id"), j.get("title"), loc, j.get("publishedAt"), j.get("jobUrl"), desc))
    return out


PARSERS = {"greenhouse": from_greenhouse, "lever": from_lever, "ashby": from_ashby}


# ---------------------------------------------------------------- filtering

def _any(words: list[str], text: str) -> bool:
    return any(re.search(r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])", text.lower()) for w in words)


def keep(job: dict, titles: list[str], exclude: list[str], locations: list[str]) -> bool:
    """Title has any `titles` word (or none given), no `exclude` word, and location has any `locations` word."""
    t = job.get("title") or ""
    if titles and not _any(titles, t):
        return False
    if exclude and _any(exclude, t):
        return False
    if locations and not _any(locations, job.get("location") or ""):
        return False
    return True


# ---------------------------------------------------------------- run

@dataclass
class BoardResult:
    company: str
    ats: str
    board: str
    fetched: int = 0
    kept: int = 0
    error: str = ""
    jobs: list[dict] = field(default_factory=list)


def fetch_company(company: dict, fetch: Fetch | None = None) -> BoardResult:
    ats = (company.get("ats") or "").lower()
    res = BoardResult(company.get("name", "?"), ats, company.get("board", ""))
    if ats not in API or not res.board:
        res.error = f"unknown ats {ats!r} or missing board"
        return res
    url = API[ats].format(board=res.board)
    try:
        payload = (fetch or http_json)(url)
        res.jobs = PARSERS[ats]({**company, "ats": ats}, payload)
    except urllib.error.HTTPError as e:
        res.error = f"HTTP {e.code} from {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        res.error = f"network error from {url}: {getattr(e, 'reason', e)}"
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        res.error = f"unexpected payload from {url}: {type(e).__name__}: {e}"
    res.fetched = len(res.jobs)
    return res


def run(watchlist: list[dict], *, titles=(), exclude=(), locations=(), fetch: Fetch | None = None,
        workers: int = 8) -> tuple[list[dict], list[BoardResult]]:
    """Fetch every board (in parallel), filter, dedupe by URL. Returns (jobs, per-company results)."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(lambda c: fetch_company(c, fetch), watchlist))
    jobs, seen = [], set()
    for r in results:
        for j in r.jobs:
            if not keep(j, list(titles), list(exclude), list(locations)) or j["url"] in seen:
                continue
            seen.add(j["url"])
            r.kept += 1
            jobs.append(j)
    jobs.sort(key=lambda j: j["posted"], reverse=True)
    return jobs, results


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.boards", description="Read open jobs from company career boards")
    p.add_argument("watchlist", help='JSON list of {"name", "ats", "board"}')
    p.add_argument("--title", action="append", default=[], help="keep titles containing this word/phrase (repeatable)")
    p.add_argument("--exclude-title", action="append", default=[], help="drop titles containing this (repeatable)")
    p.add_argument("--location", action="append", default=[], help="keep locations containing this (repeatable)")
    p.add_argument("--out", default="runs/v2/boards.json")
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args(argv)
    with open(a.watchlist) as f:
        watchlist = json.load(f)
    jobs, results = run(watchlist, titles=a.title, exclude=a.exclude_title, locations=a.location, workers=a.workers)
    for r in results:
        status = f"ERROR {r.error}" if r.error else f"{r.fetched:4} open, {r.kept:3} kept"
        print(f"  {r.company[:28]:28} {r.ats:10} {status}")
    failed = sum(bool(r.error) for r in results)
    print(f"{len(jobs)} job(s) kept from {len(results) - failed}/{len(results)} board(s) -> {a.out}")
    with open(a.out, "w") as f:
        json.dump(jobs, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
