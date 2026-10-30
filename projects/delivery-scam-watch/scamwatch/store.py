"""Saving what the collectors find, without duplicates.

- A domain or URL is stored once; later sightings only move its `last_seen` forward.
- Every sighting is one row in `observations`, unique per (source, source's own ID), so
  running a collector twice over the same items adds nothing new.
- Raw source records are kept 30 days, then cleared by `purge_raw`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import psycopg
import tldextract

from .config import Brand

# Offline public-suffix list (bundled with tldextract): no network call at import or run time.
_extract = tldextract.TLDExtract(suffix_list_urls=())


@dataclass(frozen=True)
class DomainParts:
    fqdn: str
    registered_domain: str
    tld: str


def split_domain(host: str) -> DomainParts:
    """'Track.FedEx-Help.co.uk.' -> fqdn 'track.fedex-help.co.uk', registered 'fedex-help.co.uk', tld 'co.uk'."""
    fqdn = host.strip().lower().rstrip(".")
    if fqdn.startswith("*."):  # wildcard certificate names
        fqdn = fqdn[2:]
    ext = _extract(fqdn)
    tld = ext.suffix or fqdn.rsplit(".", 1)[-1]
    registered = f"{ext.domain}.{ext.suffix}" if ext.domain and ext.suffix else fqdn
    return DomainParts(fqdn, registered, tld)


def brand_match(fqdn: str, brands: list[Brand]) -> tuple[str | None, bool]:
    """(brand whose keyword appears in the name, whether the domain is allowlisted)."""
    for b in brands:
        if any(fqdn == a or fqdn.endswith("." + a) for a in b.allowlist):
            return b.name, True
    for b in brands:
        if any(k in fqdn for k in b.keywords):
            return b.name, False
    return None, False


def upsert_domain(conn: psycopg.Connection, host: str, brands: list[Brand], seen: datetime | None = None) -> int:
    parts = split_domain(host)
    brand, allowlisted = brand_match(parts.fqdn, brands)
    row = conn.execute(
        """INSERT INTO domains (fqdn, registered_domain, tld, brand_guess, allowlisted, first_seen, last_seen)
           VALUES (%s, %s, %s, %s, %s, COALESCE(%s, now()), COALESCE(%s, now()))
           ON CONFLICT (fqdn) DO UPDATE SET last_seen = GREATEST(domains.last_seen, EXCLUDED.last_seen)
           RETURNING id""",
        (parts.fqdn, parts.registered_domain, parts.tld, brand, allowlisted, seen, seen),
    ).fetchone()
    return row[0]


def upsert_url(
    conn: psycopg.Connection, url: str, brands: list[Brand], seen: datetime | None = None
) -> tuple[int, int]:
    """Returns (url_id, domain_id)."""
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"URL has no host: {url!r}")
    domain_id = upsert_domain(conn, host, brands, seen)
    row = conn.execute(
        """INSERT INTO urls (url, domain_id, first_seen, last_seen)
           VALUES (%s, %s, COALESCE(%s, now()), COALESCE(%s, now()))
           ON CONFLICT (url) DO UPDATE SET last_seen = GREATEST(urls.last_seen, EXCLUDED.last_seen)
           RETURNING id""",
        (url, domain_id, seen, seen),
    ).fetchone()
    return row[0], domain_id


def add_observation(
    conn: psycopg.Connection,
    *,
    source_id: int,
    run_id: int,
    source_ref: str,
    domain_id: int | None = None,
    url_id: int | None = None,
    source_time: datetime | None = None,
    raw: dict | None = None,
) -> bool:
    """Record one sighting. Returns True if it was new, False if this source already reported it."""
    row = conn.execute(
        """INSERT INTO observations (source_id, run_id, source_ref, domain_id, url_id, source_time, raw)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (source_id, source_ref) DO NOTHING
           RETURNING id""",
        (source_id, run_id, source_ref, domain_id, url_id, source_time, json.dumps(raw) if raw is not None else None),
    ).fetchone()
    return row is not None


def purge_raw(conn: psycopg.Connection, days: int = 30) -> int:
    """Clear raw source records older than `days`; extracted fields stay forever."""
    cur = conn.execute(
        """UPDATE observations SET raw = NULL, raw_purged_at = now()
           WHERE raw IS NOT NULL AND observed_at < now() - make_interval(days => %s)""",
        (days,),
    )
    return cur.rowcount


def source_id(conn: psycopg.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM sources WHERE name = %s", (name,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown source {name!r}; add it in a migration first.")
    return row[0]
