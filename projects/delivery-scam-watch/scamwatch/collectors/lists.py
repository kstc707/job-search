"""List-based sources: community blocklists, the OpenPhish feed, the Tranco popular-sites list
and WhoisDS daily newly registered domains.

Each list is downloaded whole, filtered to entries containing a brand keyword, and stored.
Re-running a collector stores nothing twice; the first time an entry is seen is kept, which is
what lets us measure when a domain first appeared on a blocklist.
"""

from __future__ import annotations

import base64
import csv
import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import psycopg

from ..config import load_brands
from ..http import Fetcher
from ..runlog import CollectorRun, log
from ..store import add_observation, upsert_domain, upsert_url
from . import keyword_pattern

URLS = {
    "phishingdb": "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/master/phishing-domains-ACTIVE.txt",
    "phishingarmy": "https://phishing.army/download/phishing_army_blocklist.txt",
    "openphish": "https://openphish.com/feed.txt",
    "tranco": "https://tranco-list.eu/top-1m.csv.zip",
}
WHOISDS_URL = "https://www.whoisds.com//whois-database/newly-registered-domains/{token}/nrd"


# ---------------------------------------------------------------- parsing (pure) ----
def parse_domain_list(text: str) -> list[str]:
    """One domain per line; skips comments and blank lines; lower-cases."""
    out = []
    for line in text.splitlines():
        line = line.strip().lower()
        if line and not line.startswith(("#", "!", "//")):
            out.append(line.split()[0])
    return out


def parse_url_list(text: str) -> list[str]:
    return [u.strip() for u in text.splitlines() if u.strip().startswith(("http://", "https://"))]


def parse_tranco(zip_bytes: bytes) -> list[tuple[int, str]]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        rows = csv.reader(io.StringIO(z.read(z.namelist()[0]).decode()))
        return [(int(rank), dom.lower()) for rank, dom in rows]


def parse_whoisds(zip_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        return parse_domain_list(z.read(z.namelist()[0]).decode())


def whoisds_token(day: date) -> str:
    return base64.b64encode(f"{day.isoformat()}.zip".encode()).decode()


# ---------------------------------------------------------------- collecting ------
def _store_domains(conn, run: CollectorRun, domains: list[str], source_time=None, raw_of=None) -> None:
    brands, kw = load_brands(), keyword_pattern()
    for d in domains:
        if not kw.search(d):
            continue
        run.seen += 1
        dom_id = upsert_domain(conn, d, brands, source_time)
        raw = raw_of(d) if raw_of else None
        if add_observation(
            conn,
            source_id=run.source_id,
            run_id=run.id,
            source_ref=d,
            domain_id=dom_id,
            source_time=source_time,
            raw=raw,
        ):
            run.new += 1


def collect_blocklist(conn: psycopg.Connection, source: str, fetcher: Fetcher) -> None:
    with CollectorRun(conn, source) as run:
        domains = parse_domain_list(fetcher.get(URLS[source]).text)
        log("downloaded", source=source, entries=len(domains))
        _store_domains(conn, run, domains)


def collect_openphish(conn: psycopg.Connection, fetcher: Fetcher) -> None:
    brands, kw = load_brands(), keyword_pattern()
    with CollectorRun(conn, "openphish") as run:
        urls = parse_url_list(fetcher.get(URLS["openphish"]).text)
        log("downloaded", source="openphish", entries=len(urls))
        for u in urls:
            host = (urlsplit(u).hostname or "").lower()
            if not host or not kw.search(u.lower()):
                continue
            run.seen += 1
            url_id, dom_id = upsert_url(conn, u, brands)
            if add_observation(
                conn, source_id=run.source_id, run_id=run.id, source_ref=u, domain_id=dom_id, url_id=url_id
            ):
                run.new += 1


def collect_tranco(conn: psycopg.Connection, fetcher: Fetcher) -> None:
    with CollectorRun(conn, "tranco") as run:
        ranked = parse_tranco(fetcher.get(URLS["tranco"]).content)
        rank_of = {d: r for r, d in ranked}
        log("downloaded", source="tranco", entries=len(ranked))
        _store_domains(conn, run, [d for _, d in ranked], raw_of=lambda d: {"rank": rank_of[d]})


def collect_whoisds(conn: psycopg.Connection, fetcher: Fetcher, days: int = 7) -> None:
    """The free list covers recent days only; missing days are noted, not fatal."""
    today = datetime.now(UTC).date()
    with CollectorRun(conn, "whoisds") as run:
        for back in range(days, 0, -1):  # oldest day first, so a repeat keeps its earliest date
            day = today - timedelta(days=back)
            try:
                resp = fetcher.get(WHOISDS_URL.format(token=whoisds_token(day)))
                domains = parse_whoisds(resp.content)
            except Exception as exc:  # noqa: BLE001  one missing day should not sink the run
                run.partial(f"{day}: {type(exc).__name__}")
                continue
            log("downloaded", source="whoisds", day=str(day), entries=len(domains))
            when = datetime(day.year, day.month, day.day, tzinfo=UTC)
            _store_domains(conn, run, domains, source_time=when, raw_of=lambda d, day=day: {"day": str(day)})
            conn.commit()
