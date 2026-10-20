"""Drop jobs that would be a second application, checked against the Notion tracker.

The local ledger (auto_apply/ledger.py) lives in git-ignored runs/, so a fresh cloud session
starts with it empty. The tracker is the record that survives, and it also holds Sai's
manual rows and the applications found in the Tsenta inbox. Each found job is checked
against every tracker row (any Status) and against the jobs before it in the same batch:

    same posting   normalized Apply/Source URL matches (tracking parameters stripped)
    same req id    same company and the same requisition id parsed from the URL
    repost         same company and a similar title (another board, or re-listed)
    cooldown       any row at the same company dated within `cooldown_days`
                   (several roles at one company in a short time reads as spam)

Input (JSON the agent fetched):
- jobs:    [{"title", "company", "location", "url", "req_id"?}...]
- tracker: [{"Job", "Company", "Status", "Apply URL", "Source URL", "date:Date:start"}...]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from auto_apply.ledger import normalize_url
from auto_apply.v2.outcomes import company_match, title_score

TITLE_SAME = 0.85
# Requisition ids in common ATS links: Greenhouse /jobs/123456, Workday ..._R12345 or
# _JR-0042, Lever/Ashby UUIDs, and req=/jobId= query parameters.
_REQ_PATTERNS = [
    re.compile(r"/jobs?/(\d{5,})"),
    re.compile(r"_((?:J?R|REQ)-?\d{3,})(?:[/?-]|$)", re.I),
    re.compile(r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I),
    re.compile(r"[?&](?:req|reqid|jobid|job_id|gh_jid)=([\w-]{4,})", re.I),
]


def req_id(url: str | None) -> str:
    for rx in _REQ_PATTERNS:
        m = rx.search(url or "")
        if m:
            return m.group(1).upper()
    return ""


def _row_title(row: dict) -> str:
    """Tracker titles are "<Company> - <Title>"; strip the company part."""
    job, company = row.get("Job") or "", row.get("Company") or ""
    if company and job.lower().startswith(company.lower()):
        return job[len(company):].lstrip(" -–—:|")
    head, sep, tail = job.partition(" - ")
    return tail if sep and (not company or company_match(head, company)) else job


def _row_company(row: dict) -> str:
    return row.get("Company") or (row.get("Job") or "").partition(" - ")[0]


def _row_date(row: dict) -> date | None:
    raw = (row.get("date:Date:start") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


@dataclass
class Record:
    """One earlier application or posting to compare against."""
    company: str
    title: str
    urls: tuple[str, ...]
    req: str
    day: date | None
    status: str
    label: str


def _from_row(row: dict) -> Record:
    urls = tuple(u for u in (row.get("Apply URL"), row.get("Source URL")) if u)
    return Record(_row_company(row), _row_title(row), urls,
                  next((r for r in map(req_id, urls) if r), ""), _row_date(row),
                  row.get("Status") or "", f"tracker: {row.get('Job') or '?'} ({row.get('Status') or 'no status'})")


def _from_job(job: dict) -> Record:
    url = job.get("url") or ""
    return Record(job.get("company") or "", job.get("title") or "", (url,) if url else (),
                  (job.get("req_id") or req_id(url)).upper(), None, "",
                  f"earlier in this batch: {job.get('company')} - {job.get('title')}")


@dataclass
class Verdict:
    keep: bool
    reason: str
    match: str = ""


def check(job: dict, seen: list[Record], *, today: date, cooldown_days: int) -> Verdict:
    mine = _from_job(job)
    keys = {normalize_url(u) for u in mine.urls}
    for rec in seen:
        if keys & {normalize_url(u) for u in rec.urls}:
            return Verdict(False, "same posting", rec.label)
    for rec in seen:
        if not company_match(mine.company, rec.company):
            continue
        if mine.req and mine.req == rec.req:
            return Verdict(False, f"same requisition id {mine.req}", rec.label)
        if title_score(mine.title, rec.title) >= TITLE_SAME:
            return Verdict(False, "same company and title (repost or another board)", rec.label)
    if cooldown_days > 0:
        since = today - timedelta(days=cooldown_days)
        for rec in seen:
            if rec.day and rec.day >= since and rec.status != "Skipped" and company_match(mine.company, rec.company):
                return Verdict(False, f"company cooldown: row dated {rec.day} (< {cooldown_days} days)", rec.label)
    return Verdict(True, "new")


def dedupe(jobs: list[dict], tracker: list[dict], *, today: date,
           cooldown_days: int = 60) -> list[tuple[dict, Verdict]]:
    seen = [_from_row(r) for r in tracker]
    out = []
    for job in jobs:
        v = check(job, seen, today=today, cooldown_days=cooldown_days)
        out.append((job, v))
        if v.keep:
            rec = _from_job(job)
            rec.day = today  # a kept job counts as today's touch on that company
            seen.append(rec)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.dedupe")
    p.add_argument("jobs", help="JSON list of found jobs")
    p.add_argument("--tracker", required=True, help="JSON list of tracker rows (all statuses)")
    p.add_argument("--cooldown-days", type=int, default=60)
    p.add_argument("--today", help="YYYY-MM-DD (default: today)")
    p.add_argument("--out")
    a = p.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else date.today()
    result = dedupe(json.load(open(a.jobs)), json.load(open(a.tracker)), today=today,
                    cooldown_days=a.cooldown_days)
    for job, v in result:
        mark = "KEEP" if v.keep else "drop"
        extra = f"  [{v.match}]" if v.match else ""
        print(f"{mark}  {(job.get('company') or '')[:22]:22} {(job.get('title') or '')[:40]:40} {v.reason}{extra}")
    kept = sum(v.keep for _, v in result)
    print(f"{kept} kept, {len(result) - kept} dropped")
    if a.out:
        json.dump([{**j, "dedupe": asdict(v)} for j, v in result], open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
