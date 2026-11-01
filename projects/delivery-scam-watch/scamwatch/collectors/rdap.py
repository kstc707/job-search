"""RDAP enrichment: when was a domain registered, and by which registrar.

Each query goes straight to the registry that runs the domain's ending (.com -> Verisign,
.top -> ZDNS ...), found through IANA's official RDAP directory. Going direct spreads requests
across many registries; a registry that rate-limits us is skipped for the rest of the run.
Only brand-keyword domains that are not allowlisted are looked up, each registered domain
once, at most `limit` per run, with a polite gap between requests.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import psycopg

from ..http import Fetcher
from ..runlog import CollectorRun

IANA_BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
FALLBACK_URL = "https://rdap.org/domain/{domain}"


def parse_bootstrap(doc: dict) -> dict[str, str]:
    """IANA dns.json -> {ending: registry base URL}."""
    out = {}
    for endings, urls in doc.get("services", []):
        https = [u for u in urls if u.startswith("https://")] or urls
        for e in endings:
            out[e.lower()] = https[0] if https[0].endswith("/") else https[0] + "/"
    return out


def rdap_url(domain: str, servers: dict[str, str]) -> str:
    base = servers.get(domain.rsplit(".", 1)[-1])
    return f"{base}domain/{domain}" if base else FALLBACK_URL.format(domain=domain)


def parse_rdap(doc: dict) -> tuple[datetime | None, str | None]:
    created = None
    for ev in doc.get("events", []):
        if ev.get("eventAction") == "registration" and ev.get("eventDate"):
            created = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
            break
    registrar = None
    for ent in doc.get("entities", []):
        if "registrar" in ent.get("roles", []):
            for item in (ent.get("vcardArray") or [None, []])[1]:
                if item and item[0] == "fn":
                    registrar = item[3]
            break
    return created, registrar


def pending_domains(conn: psycopg.Connection, limit: int) -> list[str]:
    """Registered domains still to look up, most useful first: those on a blocklist or newly
    surfaced by the certificate log / registration list, and that mention a brand as a word.
    Domains on a free hosting platform are skipped: the registration date would be the platform's."""
    from ..analysis.features import HOSTING, brand_token

    rows = conn.execute(
        """SELECT d.registered_domain, min(d.fqdn),
                  bool_or(s.name IN ('openphish', 'whoisds', 'ctlog')) AS fresh
           FROM domains d JOIN observations o ON o.domain_id = d.id JOIN sources s ON s.id = o.source_id
           LEFT JOIN registrations r ON r.registered_domain = d.registered_domain
           WHERE d.brand_guess IS NOT NULL AND NOT d.allowlisted AND r.registered_domain IS NULL
             AND s.name IN ('openphish', 'phishingdb', 'phishingarmy', 'whoisds', 'ctlog')
           GROUP BY d.registered_domain ORDER BY fresh DESC, max(d.first_seen) DESC"""
    ).fetchall()
    keep = [rd for rd, fqdn, _ in rows if brand_token(fqdn) and rd not in HOSTING]
    return keep[:limit]


def collect_rdap(conn: psycopg.Connection, fetcher: Fetcher, limit: int = 200, only: list[str] | None = None) -> None:
    from urllib.parse import urlsplit

    with CollectorRun(conn, "rdap") as run:
        servers = parse_bootstrap(fetcher.get(IANA_BOOTSTRAP).json())
        blocked: set[str] = set()
        for domain in only or pending_domains(conn, limit):
            url = rdap_url(domain, servers)
            host = urlsplit(url).hostname
            if host in blocked:
                continue
            run.seen += 1
            try:
                resp = fetcher.get(url)
                created, registrar = parse_rdap(resp.json())
                status = "ok"
            except RuntimeError as exc:
                if "429" in str(exc):  # this registry asked us to slow down: skip it until next run
                    blocked.add(host)
                    run.partial(f"rate limited by {host}; skipped for this run")
                    continue
                created = registrar = None
                status = "error"
            except httpx.HTTPStatusError as exc:
                created = registrar = None
                status = "not_found" if exc.response.status_code == 404 else "unsupported"
            except ValueError:
                created = registrar = None
                status = "error"
            conn.execute(
                """INSERT INTO registrations (registered_domain, created_at, registrar, status)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (registered_domain) DO UPDATE SET created_at = EXCLUDED.created_at,
                     registrar = EXCLUDED.registrar, status = EXCLUDED.status, checked_at = now()""",
                (domain, created, registrar, status),
            )
            if status == "ok":
                run.new += 1
            conn.commit()
