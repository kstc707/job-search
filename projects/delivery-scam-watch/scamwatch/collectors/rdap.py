"""RDAP enrichment: when was a domain registered, and by which registrar.

rdap.org redirects each query to the registry that runs the domain's ending (.com, .top ...).
Only brand-keyword domains that are not allowlisted are looked up, each registered domain
once, at most `limit` per run, with a polite gap between requests.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import psycopg

from ..http import Fetcher
from ..runlog import CollectorRun

RDAP_URL = "https://rdap.org/domain/{domain}"


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
    with CollectorRun(conn, "rdap") as run:
        for domain in only or pending_domains(conn, limit):
            run.seen += 1
            try:
                resp = fetcher.get(RDAP_URL.format(domain=domain))
                created, registrar = parse_rdap(resp.json())
                status = "ok"
            except RuntimeError as exc:
                if "429" in str(exc):  # rdap.org asked us to slow down: stop now, resume next cycle
                    run.partial("rate limited by rdap.org; stopped early")
                    break
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
