"""Career-page watcher: new analyst postings straight from employers' job boards (v2 find).

Most employers post through an ATS that publishes the board as public JSON, so no page
scraping is needed and every job comes with the employer's own apply URL (which the filler
can open directly):

    greenhouse       GET  boards-api.greenhouse.io/v1/boards/{board}/jobs
    lever            GET  api.lever.co/v0/postings/{company}?mode=json
    ashby            GET  api.ashbyhq.com/posting-api/job-board/{company}
    smartrecruiters  GET  api.smartrecruiters.com/v1/companies/{company}/postings
    workday          POST {tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs

`scan` reads the watchlist, keeps analyst-type titles (target.title_target) and writes the
jobs not seen before in the jobs.json shape the rest of v2 uses. `find` looks a company up
on the four boards whose URLs can be guessed from its name, to turn a job found elsewhere
(Jobright, Indeed) into the employer's apply URL.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable

from .target import title_target

Http = Callable[[str, str, dict | None], object]  # (method, url, json body) -> parsed JSON

WORKDAY_PAGE = 20          # the cxs endpoint returns at most 20 per request
WORKDAY_MAX_PAGES = 10     # 200 matches per search term is plenty for one company


def http_json(method: str, url: str, body: dict | None = None, timeout: int = 90) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (job-search boards watcher)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---- URLs ------------------------------------------------------------------------------------

def parse_board_url(url: str) -> dict:
    """{'ats': ..., plus the ids that ATS's API needs}. ValueError if unsupported."""
    u = url.strip()
    if m := re.match(r"https?://(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)", u):
        return {"ats": "greenhouse", "board": m[1]}
    if m := re.match(r"https?://jobs\.(?:eu\.)?lever\.co/([\w.-]+)", u):
        return {"ats": "lever", "company": m[1]}
    if m := re.match(r"https?://jobs\.ashbyhq\.com/([\w.%-]+)", u):
        return {"ats": "ashby", "company": m[1]}
    if m := re.match(r"https?://(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)", u):
        return {"ats": "smartrecruiters", "company": m[1]}
    if m := re.match(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", u):
        return {"ats": "workday", "tenant": m[1], "host": f"{m[1]}.{m[2]}.myworkdayjobs.com", "site": m[3]}
    raise ValueError(f"unsupported job board URL: {url}")


def ats_of(url: str) -> str:
    """The ATS behind an apply URL ('other' when unknown)."""
    try:
        return parse_board_url(url)["ats"]
    except ValueError:
        pass
    for name, rx in [("icims", r"\.icims\.com"), ("oraclecloud", r"oraclecloud\.com"),
                     ("successfactors", r"successfactors|ns2cloud"), ("taleo", r"taleo\.net"),
                     ("adp", r"adp\.com"), ("paylocity", r"paylocity\.com"), ("ukg", r"ultipro|ukg"),
                     ("jobvite", r"jobvite\.com"), ("dayforce", r"dayforcehcm"), ("jobright", r"jobright\.ai")]:
        if re.search(rx, url or "", re.I):
            return name
    return "other"


# ---- dates -----------------------------------------------------------------------------------

_UNITS = {"minute": 1 / 60, "hour": 1, "day": 24, "week": 24 * 7, "month": 24 * 30}


def parse_posted(text: str | None, now: datetime) -> str | None:
    """ISO time from an ISO string, epoch ms, or 'Posted 3 Days Ago' / '21 minutes ago'.
    '30+ Days Ago' becomes 31 days: old enough for target.py to drop it."""
    if text is None or text == "":
        return None
    if isinstance(text, (int, float)):
        return datetime.fromtimestamp(text / 1000, timezone.utc).isoformat()
    s = str(text).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s
    low = s.lower()
    if "today" in low or "just" in low:
        return now.isoformat()
    if "yesterday" in low:
        return (now - timedelta(days=1)).isoformat()
    if m := re.search(r"\b(\d+|an?)\+?\s*(minute|hour|day|week|month)s?\b", low):
        n = 1 if m[1] in ("a", "an") else int(m[1])
        if "+" in m[0]:
            n += 1
        return (now - timedelta(hours=n * _UNITS[m[2]])).isoformat()
    return None


# ---- fetchers (one per ATS) ------------------------------------------------------------------

def _job(company, title, location, posted, url, ats):
    return {"title": (title or "").strip(), "company": company, "location": (location or "").strip(),
            "posted": posted, "url": url, "source": "boards", "ats": ats}


def fetch_board(entry: dict, *, http: Http = http_json, now: datetime,
                queries: tuple[str, ...] = ("analyst",)) -> list[dict]:
    b = parse_board_url(entry["url"])
    company = entry["company"]
    if b["ats"] == "greenhouse":
        d = http("GET", f"https://boards-api.greenhouse.io/v1/boards/{b['board']}/jobs", None)
        return [_job(company, j.get("title"), (j.get("location") or {}).get("name"),
                     parse_posted(j.get("first_published") or j.get("updated_at"), now),
                     j.get("absolute_url"), "greenhouse") for j in d.get("jobs", [])]
    if b["ats"] == "lever":
        d = http("GET", f"https://api.lever.co/v0/postings/{b['company']}?mode=json", None)
        return [_job(company, j.get("text"), (j.get("categories") or {}).get("location"),
                     parse_posted(j.get("createdAt"), now), j.get("hostedUrl"), "lever") for j in d]
    if b["ats"] == "ashby":
        d = http("GET", f"https://api.ashbyhq.com/posting-api/job-board/{b['company']}", None)
        return [_job(company, j.get("title"),
                     "Remote" if j.get("isRemote") and not j.get("location") else j.get("location"),
                     parse_posted(j.get("publishedAt"), now), j.get("jobUrl"), "ashby")
                for j in d.get("jobs", []) if j.get("isListed", True)]
    if b["ats"] == "smartrecruiters":
        out, offset = [], 0
        while True:
            d = http("GET", f"https://api.smartrecruiters.com/v1/companies/{b['company']}/postings"
                            f"?limit=100&offset={offset}", None)
            for j in d.get("content", []):
                loc = j.get("location") or {}
                where = "Remote" if loc.get("remote") else ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
                out.append(_job(company, j.get("name"), where, parse_posted(j.get("releasedDate"), now),
                                f"https://jobs.smartrecruiters.com/{b['company']}/{j.get('id')}", "smartrecruiters"))
            offset += 100
            if offset >= d.get("totalFound", 0) or not d.get("content"):
                return out
    if b["ats"] == "workday":
        api = f"https://{b['host']}/wday/cxs/{b['tenant']}/{b['site']}/jobs"
        out, seen = [], set()
        for q in queries:
            total = 0
            for page in range(WORKDAY_MAX_PAGES):
                d = http("POST", api, {"appliedFacets": {}, "limit": WORKDAY_PAGE,
                                       "offset": page * WORKDAY_PAGE, "searchText": q})
                total = total or d.get("total") or 0  # Workday sends the total on the first page only
                posts = d.get("jobPostings") or []
                for j in posts:
                    path = j.get("externalPath") or ""
                    if path in seen:
                        continue
                    seen.add(path)
                    out.append(_job(company, j.get("title"), j.get("locationsText"),
                                    parse_posted(j.get("postedOn"), now),
                                    f"https://{b['host']}/{b['site']}{path}", "workday"))
                if len(posts) < WORKDAY_PAGE or (page + 1) * WORKDAY_PAGE >= total:
                    break
        return out
    raise ValueError(b["ats"])


# ---- scan ------------------------------------------------------------------------------------

def scan(watchlist: list[dict], seen: dict, *, http: Http = http_json, now: datetime,
         include_seen: bool = False) -> tuple[list[dict], list[dict]]:
    """(new analyst-title jobs, per-board report). `seen` (url -> first seen) is updated."""
    jobs, report = [], []
    for entry in watchlist:
        try:
            found = fetch_board(entry, http=http, now=now)
        except (urllib.error.URLError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            report.append({"company": entry.get("company"), "error": f"{type(e).__name__}: {e}"})
            continue
        fit = [j for j in found if j["url"] and title_target(j["title"]) == "in"]
        new = [j for j in fit if include_seen or j["url"] not in seen]
        for j in fit:
            seen.setdefault(j["url"], now.isoformat())
        jobs += [{**j, "board_tier": entry.get("tier")} for j in new]
        report.append({"company": entry.get("company"), "postings": len(found), "analyst": len(fit), "new": len(new)})
    return jobs, report


def _slugs(company: str) -> list[str]:
    base = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|the|group|holdings)\b\.?", "", company, flags=re.I)
    words = re.findall(r"[a-z0-9]+", base.lower())
    return list(dict.fromkeys(["".join(words), "-".join(words), words[0] if words else ""]))


def find(company: str, title: str | None = None, *, http: Http = http_json, now: datetime) -> list[dict]:
    """Jobs at `company` on guessable boards (Greenhouse/Lever/Ashby/SmartRecruiters).
    With `title`, only postings whose title contains it (case-insensitive)."""
    hits = []
    for slug in filter(None, _slugs(company)):
        for url in (f"https://boards.greenhouse.io/{slug}", f"https://jobs.lever.co/{slug}",
                    f"https://jobs.ashbyhq.com/{slug}", f"https://jobs.smartrecruiters.com/{slug}"):
            try:
                found = fetch_board({"company": company, "url": url}, http=http, now=now)
            except (urllib.error.URLError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            hits += [j for j in found if not title or title.lower() in j["title"].lower()]
    return list({j["url"]: j for j in hits}.values())


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.boards")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="new analyst postings on the watchlist's boards")
    s.add_argument("--watchlist", default="watchlist.json")
    s.add_argument("--seen", default="runs/v2/boards_seen.json")
    s.add_argument("--out", default="runs/v2/jobs-boards.json")
    s.add_argument("--all", action="store_true", help="include postings seen on earlier scans")
    a_ = sub.add_parser("add", help="check a careers URL and add it to the watchlist")
    a_.add_argument("url")
    a_.add_argument("--company", required=True)
    a_.add_argument("--tier", default="Rest of US")
    a_.add_argument("--watchlist", default="watchlist.json")
    f = sub.add_parser("find", help="find a company's postings on guessable boards")
    f.add_argument("--company", required=True)
    f.add_argument("--title")
    a = p.parse_args(argv)
    now = datetime.now(timezone.utc)

    if a.cmd == "scan":
        wl = json.load(open(a.watchlist))["boards"]
        try:
            seen = json.load(open(a.seen))
        except FileNotFoundError:
            seen = {}
        jobs, report = scan(wl, seen, now=now, include_seen=a.all)
        for r in report:
            print(f"{r['company'][:28]:28} " + (f"ERROR {r['error']}" if "error" in r else
                  f"{r['postings']:5} postings {r['analyst']:4} analyst {r['new']:4} new"))
        json.dump(jobs, open(a.out, "w"), indent=1)
        json.dump(seen, open(a.seen, "w"), indent=0)
        print(f"{len(jobs)} new analyst postings -> {a.out}")
        return 0
    if a.cmd == "add":
        b = parse_board_url(a.url)
        found = fetch_board({"company": a.company, "url": a.url}, now=now)
        wl = json.load(open(a.watchlist))
        if any(parse_board_url(e["url"]) == b for e in wl["boards"]):
            print("already on the watchlist")
            return 0
        wl["boards"].append({"company": a.company, "url": a.url, "ats": b["ats"], "tier": a.tier,
                             "verified": now.date().isoformat()})
        json.dump(wl, open(a.watchlist, "w"), indent=1)
        print(f"added {a.company} ({b['ats']}, {len(found)} postings)")
        return 0
    hits = find(a.company, a.title, now=now)
    print(json.dumps(hits, indent=1))
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())
